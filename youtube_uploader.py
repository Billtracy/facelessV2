"""
Direct YouTube upload via the YouTube Data API v3.

Implemented with plain `requests` + stdlib (no Google SDK) to keep the
PyInstaller bundle small:
- OAuth 2.0 installed-app flow with a loopback redirect and PKCE (RFC 8252)
- Token cache with silent refresh, stored in the per-user data folder
- Resumable chunked upload with progress reporting

The customer supplies their own OAuth client (client_secret.json from Google
Cloud Console with "YouTube Data API v3" enabled and a Desktop-app OAuth
credential) -- the same bring-your-own-key model as the LLM/Pexels keys.

NOTE: Google locks uploads from unverified API projects to Private until the
project passes verification. The GUI surfaces this so users aren't surprised.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from paths import user_data_root

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=resumable&part=snippet,status")
SCOPE = "https://www.googleapis.com/auth/youtube.upload"

TOKEN_FILE = os.path.join(user_data_root(), "youtube_token.json")
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # multiple of 256KB as the API requires


class YouTubeAuthError(Exception):
    """Sign-in / token problems the user can fix by reconnecting."""
    pass


def is_connected():
    """True when a refresh token is cached (account linked at least once)."""
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("refresh_token"))
    except Exception:
        return False


def disconnect():
    """Forget the cached Google tokens."""
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass


class _CodeHandler(BaseHTTPRequestHandler):
    """Catches Google's loopback redirect carrying ?code= (or ?error=)."""

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        if code:
            self.server.auth_code = code
        if error:
            self.server.auth_error = error
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
            b"<h2>Authorization received.</h2>"
            b"<p>You can close this tab and return to the app.</p></body></html>"
        )

    def log_message(self, *args):
        pass  # keep the console quiet


class YouTubeUploader:
    def __init__(self, client_secret_path, logger=None):
        self.client_secret_path = client_secret_path
        self.logger = logger
        self.client_id, self.client_secret = self._load_client()

    def log(self, msg):
        if self.logger:
            self.logger.info(msg)

    def _load_client(self):
        try:
            with open(self.client_secret_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise YouTubeAuthError(f"Could not read client_secret.json: {e}")
        block = data.get("installed") or data.get("web") or {}
        client_id = block.get("client_id")
        client_secret = block.get("client_secret")
        if not client_id or not client_secret:
            raise YouTubeAuthError(
                "client_secret.json is missing client_id/client_secret. "
                "Download the OAuth 'Desktop app' credential from Google Cloud Console."
            )
        return client_id, client_secret

    # --- TOKENS ---

    def _save_token(self, tok):
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tok, f)

    def _load_token(self):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def is_connected(self):
        return is_connected()

    def connect(self, timeout=180):
        """
        Run the browser sign-in flow (blocking -- call from a worker thread).
        Opens the default browser and waits for Google's loopback redirect.
        """
        server = HTTPServer(("127.0.0.1", 0), _CodeHandler)
        server.timeout = 2  # so the wait loop can check the deadline
        server.auth_code = None
        server.auth_error = None
        redirect_uri = f"http://127.0.0.1:{server.server_port}"

        # PKCE keeps the flow honest even though a desktop client_secret is public
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",  # forces a refresh_token on re-consent
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)
        self.log("Opening browser for Google sign-in...")
        webbrowser.open(auth_url)

        deadline = time.time() + timeout
        try:
            while time.time() < deadline and not server.auth_code and not server.auth_error:
                server.handle_request()  # also serves stray hits like /favicon.ico
        finally:
            server.server_close()

        if server.auth_error:
            raise YouTubeAuthError(f"Google sign-in was denied: {server.auth_error}")
        if not server.auth_code:
            raise YouTubeAuthError("Timed out waiting for Google sign-in in the browser.")

        r = requests.post(TOKEN_URL, data={
            "code": server.auth_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }, timeout=30)
        if r.status_code != 200:
            raise YouTubeAuthError(f"Token exchange failed: {r.text[:300]}")
        data = r.json()
        tok = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": time.time() + data.get("expires_in", 3600) - 60,
        }
        if not tok["refresh_token"]:
            raise YouTubeAuthError("Google did not return a refresh token. Try connecting again.")
        self._save_token(tok)
        self.log("YouTube account connected.")

    def _get_access_token(self):
        tok = self._load_token()
        if not tok or not tok.get("refresh_token"):
            raise YouTubeAuthError("Not connected to YouTube yet.")
        if time.time() < tok.get("expires_at", 0) and tok.get("access_token"):
            return tok["access_token"]

        r = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        }, timeout=30)
        if r.status_code != 200:
            disconnect()  # stale/revoked grant: force a fresh sign-in next time
            raise YouTubeAuthError(
                "Google session expired or was revoked. Please connect again.")
        data = r.json()
        tok["access_token"] = data["access_token"]
        tok["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
        self._save_token(tok)
        return tok["access_token"]

    # --- UPLOAD ---

    def upload(self, video_path, title, description="", tags=None,
               privacy="private", progress_callback=None):
        """
        Resumable upload. Returns the YouTube video ID.
        progress_callback(percent) is called as chunks land (0-100).
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")
        size = os.path.getsize(video_path)

        # YouTube rejects angle brackets in title/description
        title = re.sub(r"[<>]", "", (title or "Untitled")).strip()[:100] or "Untitled"
        description = re.sub(r"[<>]", "", description or "")[:5000]

        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        if tags:
            metadata["snippet"]["tags"] = list(tags)[:20]

        access_token = self._get_access_token()
        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        }
        r = requests.post(UPLOAD_URL, headers=init_headers, json=metadata, timeout=60)
        if r.status_code == 401:
            # One silent refresh, then retry the session init
            access_token = self._get_access_token()
            init_headers["Authorization"] = f"Bearer {access_token}"
            r = requests.post(UPLOAD_URL, headers=init_headers, json=metadata, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Could not start upload ({r.status_code}): {r.text[:300]}")
        session_uri = r.headers.get("Location")
        if not session_uri:
            raise RuntimeError("Upload session URI missing from YouTube response.")

        self.log(f"Uploading {os.path.basename(video_path)} ({size / 1e6:.1f} MB)...")
        offset = 0
        retries = 0
        with open(video_path, "rb") as f:
            while offset < size:
                f.seek(offset)
                chunk = f.read(UPLOAD_CHUNK_SIZE)
                end = offset + len(chunk) - 1
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                }
                try:
                    r = requests.put(session_uri, headers=headers, data=chunk, timeout=300)
                except requests.RequestException as e:
                    if retries >= 5:
                        raise RuntimeError(f"Upload failed after retries: {e}")
                    retries += 1
                    time.sleep(2 ** retries)
                    offset = self._query_offset(session_uri, access_token, size, offset)
                    continue

                if r.status_code in (200, 201):
                    if progress_callback:
                        progress_callback(100)
                    video_id = r.json().get("id")
                    self.log(f"Upload complete: https://youtu.be/{video_id}")
                    return video_id
                if r.status_code == 308:  # resume incomplete: server acked part
                    rng = r.headers.get("Range")  # e.g. "bytes=0-8388607"
                    offset = int(rng.rsplit("-", 1)[1]) + 1 if rng else end + 1
                    retries = 0
                    if progress_callback:
                        progress_callback(int(offset * 100 / size))
                    continue
                if r.status_code in (500, 502, 503, 504) and retries < 5:
                    retries += 1
                    time.sleep(2 ** retries)
                    offset = self._query_offset(session_uri, access_token, size, offset)
                    continue
                raise RuntimeError(f"Upload failed ({r.status_code}): {r.text[:300]}")

        raise RuntimeError("Upload ended without a completion response from YouTube.")

    def _query_offset(self, session_uri, access_token, size, fallback):
        """Ask the session how many bytes it has after an interrupted chunk."""
        try:
            r = requests.put(session_uri, headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Length": "0",
                "Content-Range": f"bytes */{size}",
            }, timeout=30)
            if r.status_code == 308:
                rng = r.headers.get("Range")
                return int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
        except requests.RequestException:
            pass
        return fallback
