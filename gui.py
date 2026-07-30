import customtkinter as ctk
import threading
import os
import re
import time
from config_manager import ConfigManager
from logic import ViralSafeBot
from license_validator import LicenseValidator
from logger import AppLogger
from version import CURRENT_VERSION, APP_NAME
from updater import UpdateChecker
from paths import resource_path
import sound_preview
import voice_catalog
import youtube_uploader
import webbrowser

# One-click YouTube upload is feature-complete but held back pending Google API
# project verification. Flip this to True to re-enable the Settings connect
# fields and the upload button on the success screen.
YOUTUBE_UPLOAD_ENABLED = False

class FacelessApp(ctk.CTk):
    def __init__(self, config_manager):
        super().__init__()
        
        # Initialize logger first
        self.logger = AppLogger()
        self.logger.info("Faceless Generator App Starting...")
        
        self.config_manager = config_manager
        self.config = self.config_manager.config
        self.license_validator = LicenseValidator()
        self.update_checker = UpdateChecker()
        
        # Window setup
        self.title(f"{APP_NAME} V{CURRENT_VERSION}")
        self.geometry("1100x750")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        self.current_frame = None
        
        # ROUTING LOGIC
        # Require an activated license before anything else. Once a key has been
        # validated by the server it is stored, so returning users skip straight
        # to credentials/dashboard.
        if not self.config.get("license_key", "").strip():
            self.show_license_page()
        elif not self._check_credits_exist():
            self.show_credentials_page()
        else:
            self.show_main_dashboard()

        # Start background update check after UI is ready
        self.update_checker.start_background_check(self)

    def _check_credits_exist(self):
        # At least one LLM key is required; visuals have built-in fallbacks
        # (Pollinations needs no key, Pexels key is optional)
        c = self.config
        return bool(c.get("groq_api_key") or c.get("gemini_api_key"))

    def clear_view(self):
        try:
            sound_preview.stop()  # don't let previews bleed into the next page
        except Exception:
            pass
        if self.current_frame:
            self.current_frame.pack_forget()
            self.current_frame.destroy()
        self.current_frame = None

    # --- HELPER ---
    def lucky_topic(self):
        self.input_topic.delete(0, "end")
        
    def browse_google_creds(self):
        f = ctk.filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if f:
            self.entry_google_creds.delete(0, "end")
            self.entry_google_creds.insert(0, f)

    def _scan_voice_folder(self):
        """Scans the voices/ folder for .wav files and returns a list of voice names."""
        voices_dir = resource_path("voices")
        if not os.path.isdir(voices_dir):
            return []
        wav_files = sorted([
            os.path.splitext(f)[0]
            for f in os.listdir(voices_dir)
            if f.lower().endswith(".wav")
        ])
        return wav_files

    def update_voice_options(self, *args):
        # TTS Provider dropdown was removed from the dashboard (Kokoro-only,
        # with an internal Edge TTS fallback already in logic.py), so this
        # no longer branches on a provider widget.
        self.frame_google_creds.pack_forget()
        # Friendly display names for the verified Kokoro voices (voice_catalog.py)
        self.opt_voice.configure(values=voice_catalog.display_names())

        # Auto-correct old saved voice "af_heart" -> "af"
        saved = self.config.get("last_voice_kokoro", "af")
        if saved == "af_heart": saved = "af"

        # Unknown IDs (custom typed) pass through and stay editable
        self.opt_voice.set(voice_catalog.to_display(saved))

    # --- SOUND PREVIEW & MUSIC SELECTION ---
    def on_music_change(self, choice):
        if choice == "Custom File...":
            f = ctk.filedialog.askopenfilename(filetypes=[
                ("Audio Files", "*.mp3 *.wav *.m4a *.ogg *.flac"),
                ("All Files", "*.*")
            ])
            if f:
                self.custom_music_path = f
            elif not self.custom_music_path:
                # Dialog cancelled and nothing previously chosen: revert
                self.var_music.set("Default (Bundled)")
        self._refresh_music_label()

    def _refresh_music_label(self):
        if self.var_music.get() == "Custom File..." and self.custom_music_path:
            self.lbl_music_file.configure(text=f"♪ {os.path.basename(self.custom_music_path)}")
        else:
            self.lbl_music_file.configure(text="")

    def _resolve_music_path(self):
        """Current music selection -> file path (None = music disabled)."""
        choice = self.var_music.get()
        if choice == "None (Silent)":
            return None
        if choice == "Custom File...":
            return self.custom_music_path or None
        return resource_path("assets", "audio", "bg-music.mp3")

    def _music_config_value(self):
        """Current music selection -> config value ('' = default, 'none' = off)."""
        choice = self.var_music.get()
        if choice == "None (Silent)":
            return "none"
        if choice == "Custom File...":
            return self.custom_music_path or ""
        return ""

    def preview_music(self):
        path = self._resolve_music_path()
        if not path:
            self._show_validation_error("No Music Selected", "Background music is set to None (Silent).")
            return
        if not os.path.exists(path):
            self._show_validation_error("File Missing", f"Music file not found:\n{path}")
            return
        self.logger.info(f"Previewing music: {path}")
        threading.Thread(target=self._music_preview_thread, args=(path,), daemon=True).start()

    def _music_preview_thread(self, path):
        try:
            sound_preview.play(path)
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Music preview failed: {error_message}")
            self.after(0, lambda: self._show_validation_error("Preview Failed", error_message))

    def preview_voice(self):
        voice_id = voice_catalog.to_voice_id(self.opt_voice.get().strip())
        if not voice_id:
            return
        self.btn_voice_preview.configure(state="disabled", text="…")
        self.logger.info(f"Previewing voice: {voice_id}")
        threading.Thread(target=self._voice_preview_thread, args=(voice_id,), daemon=True).start()

    def _voice_preview_thread(self, voice_id):
        try:
            sample = sound_preview.render_voice_sample(voice_id)
            sound_preview.play(sample)
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Voice preview failed: {error_message}")
            self.after(0, lambda: self._show_validation_error(
                "Voice Preview Failed", f"Could not preview '{voice_id}':\n{error_message}"))
        finally:
            self.after(0, self._reset_voice_preview_btn)

    def _reset_voice_preview_btn(self):
        try:
            self.btn_voice_preview.configure(state="normal", text="▶")
        except Exception:
            pass  # user navigated away; the button no longer exists

    # --- STEP 1: LICENSE PAGE ---
    def show_license_page(self):
        self.clear_view()
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        inner = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(inner, text="Welcome! Activation Required", font=("Arial", 24, "bold")).pack(pady=20)
        ctk.CTkLabel(inner, text="Please enter your License Key to proceed.").pack(pady=(0, 20))
        
        self.entry_lic = ctk.CTkEntry(inner, width=400, placeholder_text="XXXX-XXXX-XXXX-XXXX")
        self.entry_lic.pack(pady=10)
        self.entry_lic.insert(0, self.config.get("license_key", ""))
        
        self.lbl_lic_error = ctk.CTkLabel(inner, text="", text_color="red")
        self.lbl_lic_error.pack(pady=5)
        
        self.btn_activate = ctk.CTkButton(inner, text="Activate & Continue", command=self.validate_license, height=40)
        self.btn_activate.pack(pady=20)

        self.progress_lic = ctk.CTkProgressBar(inner, width=400, mode="indeterminate")
        # Hidden by default

    def validate_license(self):
        key = self.entry_lic.get().strip()
        if not key:
             self.lbl_lic_error.configure(text="Please enter a license key.")
             return

        # UI Loading State
        self.lbl_lic_error.configure(text="")
        self.btn_activate.configure(state="disabled", text="Verifying...")
        self.progress_lic.pack(pady=10)
        self.progress_lic.start()
        
        # Run in thread
        threading.Thread(target=self._run_validation_thread, args=(key,), daemon=True).start()

    def _run_validation_thread(self, key):
        """Background validation"""
        try:
             isValid, msg, customer_name = self.license_validator.verify_license(key)
             # Schedule UI update on main thread
             self.after(0, lambda: self._on_validation_complete(isValid, msg, customer_name, key))
        except Exception as e:
             self.after(0, lambda: self._on_validation_complete(False, f"Error: {e}", None, key))

    def _on_validation_complete(self, isValid, msg, customer_name, key):
        """Main thread callback"""
        # Stop Loader
        self.progress_lic.stop()
        self.progress_lic.pack_forget()
        self.btn_activate.configure(state="normal", text="Activate & Continue")
        
        if isValid:
             self.config_manager.set("license_key", key)
             if customer_name:
                 self.config_manager.set("customer_name", customer_name)
             self.logger.info(f"License validated for: {customer_name or 'Customer'}")
             if self._check_credits_exist():
                 self.show_main_dashboard()
             else:
                 self.show_credentials_page()
        else:
             self.lbl_lic_error.configure(text=msg)
             self.logger.warning(f"License validation failed: {msg}")

    # --- STEP 2: CREDENTIALS PAGE ---
    def show_credentials_page(self, back_to_main=False):
        self.clear_view()
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_text = "Configuration Setup" if not back_to_main else "Settings"
        
        # Header
        header = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        header.pack(fill="x", pady=20, padx=20)
        ctk.CTkLabel(header, text=title_text, font=("Arial", 24, "bold")).pack(side="left")
        
        if back_to_main:
             ctk.CTkButton(header, text="Back", fg_color="gray", width=80, command=self.show_main_dashboard).pack(side="right")
        
        # Next Button (Bottom)
        # Packed before form to ensure it always stays on screen
        btn_text = "Save & Continue" if not back_to_main else "Save Changes"
        ctk.CTkButton(self.current_frame, text=btn_text, command=lambda: self.save_credentials(back_to_main), height=50, font=("Arial", 16)).pack(side="bottom", pady=30)

        # Form Container
        form = ctk.CTkScrollableFrame(self.current_frame, width=800, height=500)
        form.pack(pady=10, padx=20, fill="both", expand=True)
        
        # LLM Provider Selection
        ctk.CTkLabel(form, text="AI Scriptwriter Provider:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        self.combo_llm = ctk.CTkOptionMenu(form, values=["Groq (Recommended for Speed)", "Gemini (Recommended for Quality)"], command=self.update_settings_visibility)
        self.combo_llm.pack(anchor="w", pady=(0, 5))
        
        saved_llm = self.config.get("llm_provider", "groq")
        if saved_llm == "gemini":
            self.combo_llm.set("Gemini (Recommended for Quality)")
        else:
            self.combo_llm.set("Groq (Recommended for Speed)")

        # CONTAINER for LLM Inputs (Keeps layout stable)
        self.container_llm = ctk.CTkFrame(form, fg_color="transparent")
        self.container_llm.pack(anchor="w", fill="x", pady=(0, 10))

        # Groq Input
        self.frame_groq = ctk.CTkFrame(self.container_llm, fg_color="transparent")
        ctk.CTkLabel(self.frame_groq, text="Groq API Key:", font=("Arial", 12)).pack(anchor="w")
        self.entry_groq_cred = ctk.CTkEntry(self.frame_groq, width=600, placeholder_text="gsk_...")
        self.entry_groq_cred.pack(anchor="w", pady=(0, 5))
        self.entry_groq_cred.insert(0, self.config.get("groq_api_key", ""))

        # Gemini Input
        self.frame_gemini = ctk.CTkFrame(self.container_llm, fg_color="transparent")
        ctk.CTkLabel(self.frame_gemini, text="Gemini API Key:", font=("Arial", 12)).pack(anchor="w")
        self.entry_gemini_cred = ctk.CTkEntry(self.frame_gemini, width=600, placeholder_text="AIza...")
        self.entry_gemini_cred.pack(anchor="w", pady=(0, 5))
        self.entry_gemini_cred.insert(0, self.config.get("gemini_api_key", ""))

        # Pollinations API Key Input (Image Generation)
        ctk.CTkLabel(form, text="Pollinations.ai API Key (Optional Image Generation):", font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        self.container_pollen = ctk.CTkFrame(form, fg_color="transparent")
        self.container_pollen.pack(anchor="w", fill="x", pady=(0, 10))
        
        self.frame_pollen = ctk.CTkFrame(self.container_pollen, fg_color="transparent")
        self.frame_pollen.pack(anchor="w", fill="x")
        ctk.CTkLabel(self.frame_pollen, text="Pollen API Key:", font=("Arial", 12)).pack(anchor="w")
        self.entry_pollen_cred = ctk.CTkEntry(self.frame_pollen, width=600, placeholder_text="...")
        self.entry_pollen_cred.pack(anchor="w", pady=(0, 5))
        self.entry_pollen_cred.insert(0, self.config.get("pollen_api_key", ""))

        # Pexels API Key (Optional - stock video fallback when image gen fails)
        ctk.CTkLabel(form, text="Pexels API Key (Optional Stock Video Fallback):", font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        ctk.CTkLabel(form, text="Get a free key at pexels.com/api - used when AI image generation is unavailable.", text_color="gray", font=("Arial", 11)).pack(anchor="w")
        self.entry_pexels_cred = ctk.CTkEntry(form, width=600, placeholder_text="...")
        self.entry_pexels_cred.pack(anchor="w", pady=(0, 10))
        self.entry_pexels_cred.insert(0, self.config.get("pexels_api_key", ""))

        # YouTube Upload (optional)
        ctk.CTkLabel(form, text="YouTube Upload (Optional):", font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        if YOUTUBE_UPLOAD_ENABLED:
            ctk.CTkLabel(form,
                         text="To enable one-click uploads: Google Cloud Console → enable 'YouTube Data API v3' → "
                              "create OAuth credentials (type: Desktop app) → download client_secret.json and select it here.",
                         text_color="gray", font=("Arial", 11), wraplength=760, justify="left").pack(anchor="w")

            row_yt = ctk.CTkFrame(form, fg_color="transparent")
            row_yt.pack(fill="x", anchor="w", pady=(5, 0))
            self.entry_yt_secret = ctk.CTkEntry(row_yt, width=450, placeholder_text="Path to client_secret.json")
            self.entry_yt_secret.pack(side="left", padx=(0, 10))
            self.entry_yt_secret.insert(0, self.config.get("yt_client_secret_path", ""))
            ctk.CTkButton(row_yt, text="Browse", width=100, command=self.browse_yt_secret).pack(side="left")

            row_yt2 = ctk.CTkFrame(form, fg_color="transparent")
            row_yt2.pack(fill="x", anchor="w", pady=(5, 10))
            self.lbl_yt_status = ctk.CTkLabel(row_yt2, text="", font=("Arial", 12))
            self.lbl_yt_status.pack(side="left", padx=(0, 15))
            self.btn_yt_connect = ctk.CTkButton(row_yt2, text="Connect YouTube Account", width=200,
                                                fg_color="#CC0000", hover_color="#990000",
                                                command=self.connect_youtube)
            self.btn_yt_connect.pack(side="left", padx=(0, 10))
            ctk.CTkButton(row_yt2, text="Disconnect", width=100, fg_color="gray",
                          command=self.disconnect_youtube).pack(side="left")
            self._refresh_yt_status()
        else:
            ctk.CTkLabel(form,
                         text="🔜 One-click YouTube upload is coming soon. For now, export your "
                              "video and upload it through YouTube Studio.",
                         text_color="gray", font=("Arial", 11), wraplength=760, justify="left").pack(anchor="w", pady=(0, 10))

        # Initial Visibility Update
        self.update_settings_visibility()

        # Output Folder
        ctk.CTkLabel(form, text="Export Folder:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 5))
        
        row_out = ctk.CTkFrame(form, fg_color="transparent")
        row_out.pack(fill="x", anchor="w")
        self.entry_out_cred = ctk.CTkEntry(row_out, width=450)
        self.entry_out_cred.pack(side="left", padx=(0, 10))
        self.entry_out_cred.insert(0, self.config.get("output_folder", "output"))
        ctk.CTkButton(row_out, text="Browse", width=100, command=self.browse_folder_cred).pack(side="left")

    def on_blueprint_change(self, choice):
        """Shows or hides custom topic inputs based on blueprint"""
        if choice == "Custom Topic":
            self.frame_topic_input.pack(fill="x")
            self.frame_custom_prompt.pack(fill="x")
        else:
            self.frame_topic_input.pack_forget()
            self.frame_custom_prompt.pack_forget()

    def update_settings_visibility(self, *args):
        """Hides/Shows fields based on dropdown selection"""
        llm = self.combo_llm.get()
        if "Groq" in llm:
            self.frame_groq.pack(anchor="w", fill="x")
            self.frame_gemini.pack_forget()
        else:
            self.frame_groq.pack_forget()
            self.frame_gemini.pack(anchor="w", fill="x")

    def browse_folder_cred(self):
        f = ctk.filedialog.askdirectory()
        if f:
             self.entry_out_cred.delete(0, "end")
             self.entry_out_cred.insert(0, f)

    # --- YOUTUBE ACCOUNT LINKING ---
    def browse_yt_secret(self):
        f = ctk.filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if f:
            self.entry_yt_secret.delete(0, "end")
            self.entry_yt_secret.insert(0, f)

    def _refresh_yt_status(self):
        try:
            if youtube_uploader.is_connected():
                self.lbl_yt_status.configure(text="● Connected", text_color="green")
            else:
                self.lbl_yt_status.configure(text="● Not connected", text_color="gray")
        except Exception:
            pass  # settings page may have been closed

    def connect_youtube(self):
        secret_path = self.entry_yt_secret.get().strip()
        if not secret_path or not os.path.exists(secret_path):
            self._show_validation_error("Missing client_secret.json",
                                       "Select your client_secret.json file first.\n"
                                       "See the instructions above the field.")
            return
        # Persist the path so the uploader finds it later
        self.config_manager.set("yt_client_secret_path", secret_path)
        self.config = self.config_manager.config

        self.btn_yt_connect.configure(state="disabled", text="Waiting for browser sign-in...")
        self.lbl_yt_status.configure(text="● Sign in via the browser window...", text_color="orange")
        threading.Thread(target=self._yt_connect_thread, args=(secret_path,), daemon=True).start()

    def _yt_connect_thread(self, secret_path):
        try:
            uploader = youtube_uploader.YouTubeUploader(secret_path, logger=self.logger)
            uploader.connect()
            self.logger.info("YouTube account connected")
            self.after(0, lambda: self._yt_connect_done(None))
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"YouTube connect failed: {error_message}")
            self.after(0, lambda: self._yt_connect_done(error_message))

    def _yt_connect_done(self, error):
        try:
            self.btn_yt_connect.configure(state="normal", text="Connect YouTube Account")
            self._refresh_yt_status()
        except Exception:
            return  # user left the settings page mid-flow
        if error:
            self._show_validation_error("YouTube Connection Failed", error)

    def disconnect_youtube(self):
        youtube_uploader.disconnect()
        self.logger.info("YouTube account disconnected")
        self._refresh_yt_status()

    def save_credentials(self, go_to_main):
        new_conf = {
             "llm_provider": "gemini" if "Gemini" in self.combo_llm.get() else "groq",
             "groq_api_key": self.entry_groq_cred.get().strip(),
             "gemini_api_key": self.entry_gemini_cred.get().strip(),
             "pollen_api_key": self.entry_pollen_cred.get().strip(),
             "pexels_api_key": self.entry_pexels_cred.get().strip(),
             "yt_client_secret_path": (self.entry_yt_secret.get().strip()
                                       if getattr(self, "entry_yt_secret", None) is not None
                                       else self.config.get("yt_client_secret_path", "")),
             "output_folder": self.entry_out_cred.get().strip()
        }
        self.config_manager.save_config(new_conf)
        self.config = self.config_manager.config # Refresh
        self.show_main_dashboard()

    # --- STEP 3: MAIN DASHBOARD ---
    def show_main_dashboard(self):
        self.clear_view()
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True)

        # 1. Top Bar
        top_bar = ctk.CTkFrame(self.current_frame, height=60, corner_radius=0)
        top_bar.pack(fill="x", side="top")
        
        ctk.CTkLabel(top_bar, text="DASHBOARD", font=("Arial", 20, "bold")).pack(side="left", padx=20, pady=15)
        ctk.CTkButton(top_bar, text="🔄 Check Updates", width=130, fg_color="#444444", hover_color="#555555", command=lambda: self.update_checker.prompt_update_if_available(self)).pack(side="right", padx=(5, 20), pady=10)
        ctk.CTkButton(top_bar, text="⚙ Settings", width=100, fg_color="gray", command=lambda: self.show_credentials_page(True)).pack(side="right", padx=5, pady=10)

        # 3. Generate Button (Bottom)
        # Packed before workspace to ensure it always stays on screen
        self.btn_gen = ctk.CTkButton(self.current_frame, text="GENERATE VIDEO", font=("Arial", 18, "bold"), height=60, fg_color="green", hover_color="darkgreen", command=self.start_generation)
        self.btn_gen.pack(side="bottom", fill="x", padx=40, pady=20)

        # 2. Workspace (Split Content & Style)
        workspace = ctk.CTkScrollableFrame(self.current_frame, fg_color="transparent")
        workspace.pack(fill="both", expand=True, padx=20, pady=10)
        
        # CONTENT COLUMN (Left)
        left_col = ctk.CTkFrame(workspace)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(left_col, text="CONTENT", font=("Arial", 16, "bold"), text_color="cyan").pack(pady=(15, 10))
        
        # Video Format Selection
        ctk.CTkLabel(left_col, text="Video Format:", anchor="w").pack(fill="x", padx=15, pady=(5, 0))
        self.var_video_format = ctk.StringVar(value=self.config.get("video_format", "Shorts"))
        self.seg_format = ctk.CTkSegmentedButton(left_col, values=["Shorts", "Long Form"], variable=self.var_video_format)
        self.seg_format.pack(fill="x", padx=15, pady=5)
        
        # Toggle for Manual/Auto
        self.manual_mode = ctk.BooleanVar(value=False)
        self.switch_mode = ctk.CTkSwitch(left_col, text="Manual Script Mode", command=self.toggle_manual_mode, variable=self.manual_mode)
        self.switch_mode.pack(padx=15, pady=(0, 10), anchor="w")
        
        # AUTO MODE: Niche Blueprint Selection
        self.miniframe_auto = ctk.CTkFrame(left_col, fg_color="transparent")
        self.miniframe_auto.pack(fill="x")
        
        ctk.CTkLabel(self.miniframe_auto, text="Content Blueprint:", anchor="w").pack(fill="x", padx=15, pady=(5,0))
        self.var_blueprint = ctk.StringVar(value=self.config.get("last_blueprint", "Custom Topic"))
        self.opt_blueprint = ctk.CTkOptionMenu(self.miniframe_auto, values=["Custom Topic", "True Crime Stories", "Reddit Stories", "Motivation & Inspiration", "Historical Facts", "Historical Figures", "Mythology & Ancient Lore", "Stoicism & Daily Philosophy", '"What If?" & Cosmic Sci-Fi Scenarios', "Visual Lore & Design Mysteries", "Law", "Personal Finance & Wealth", "Top 10s & Listicles", "Hollywood Gossips and Lores", "Dark Psychology", "Historical Psychology"], variable=self.var_blueprint, command=self.on_blueprint_change)
        self.opt_blueprint.pack(fill="x", padx=15, pady=5)

        # AUTO MODE: Topic Input (Only show if Custom Topic is selected)
        self.frame_topic_input = ctk.CTkFrame(self.miniframe_auto, fg_color="transparent")
        # Packed dynamically
        
        ctk.CTkLabel(self.frame_topic_input, text="Custom Video Topic (Leave empty for 'I'm Feeling Lucky'):", anchor="w").pack(fill="x", padx=15, pady=(5,0))
        
        row_topic = ctk.CTkFrame(self.frame_topic_input, fg_color="transparent")
        row_topic.pack(fill="x", padx=15, pady=5)
        
        self.input_topic = ctk.CTkEntry(row_topic)
        self.input_topic.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.input_topic.insert(0, self.config.get("last_topic", ""))
        
        ctk.CTkButton(row_topic, text="🎲 Lucky", width=60, fg_color="purple", command=self.lucky_topic).pack(side="right")
        
        # AUTO MODE: Custom Prompt
        self.frame_custom_prompt = ctk.CTkFrame(self.miniframe_auto, fg_color="transparent")
        # Packed dynamically
        ctk.CTkLabel(self.frame_custom_prompt, text="Custom Prompt Template:", anchor="w").pack(fill="x", padx=15, pady=(20,0))
        ctk.CTkLabel(self.frame_custom_prompt, text="(Use {selected_topic} and {point_count})", text_color="gray", font=("Arial", 10)).pack(fill="x", padx=15)
        self.input_prompt = ctk.CTkTextbox(self.frame_custom_prompt, height=150)
        self.input_prompt.pack(fill="both", expand=True, padx=15, pady=10)
        p_template = self.config.get("prompt_template", "")
        if p_template: self.input_prompt.insert("1.0", p_template)

        # Initialize visibility
        self.on_blueprint_change(self.var_blueprint.get())

        # MANUAL MODE: Script Input (Hidden by default)
        self.miniframe_manual = ctk.CTkFrame(left_col, fg_color="transparent")
        
        ctk.CTkLabel(self.miniframe_manual, text="Manual Script (Line | Visual):", anchor="w").pack(fill="x", padx=15, pady=(5,0))
        ctk.CTkLabel(self.miniframe_manual, text="Format: 'Caption Text | Visual Search Keyword'", text_color="gray", font=("Arial", 10)).pack(fill="x", padx=15)
        self.input_script_manual = ctk.CTkTextbox(self.miniframe_manual, height=300)
        self.input_script_manual.pack(fill="both", expand=True, padx=15, pady=10)
        self.input_script_manual.insert("1.0", "Signs someone is lying | Nervous person eyes\nThey avoid eye contact | Eyes looking away close up\nDrop a FIRE emoji for more | Fire explosion")

        # STYLE COLUMN (Right)
        right_col = ctk.CTkFrame(workspace)
        right_col.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        ctk.CTkLabel(right_col, text="STYLE", font=("Arial", 16, "bold"), text_color="orange").pack(pady=(15, 10))
        
        
        # TTS Provider Removed (Always uses Kokoro + Fallback)
        
        # Google Creds (Removed - not needed for Gemini)
        self.frame_google_creds = ctk.CTkFrame(right_col, fg_color="transparent")
        # Keep frame helper to avoid errors but don't pack stuff inside

        
        # Voice (Editable Combobox for Custom Voice ID) + Preview button
        ctk.CTkLabel(right_col, text="Narrator Voice:", anchor="w").pack(fill="x", padx=15, pady=(15,0))
        row_voice = ctk.CTkFrame(right_col, fg_color="transparent")
        row_voice.pack(fill="x", padx=15, pady=5)
        self.opt_voice = ctk.CTkComboBox(row_voice, values=voice_catalog.display_names())
        self.opt_voice.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_voice_preview = ctk.CTkButton(row_voice, text="▶", width=36, command=self.preview_voice)
        self.btn_voice_preview.pack(side="right")

        # Init state
        self.update_voice_options() # Refresh UI state


        # Font
        ctk.CTkLabel(right_col, text="Caption Font:", anchor="w").pack(fill="x", padx=15, pady=(15,0))
        self.opt_font = ctk.CTkOptionMenu(right_col, values=["Anton-Regular", "Arial-Bold", "Impact", "Verdana-Bold", "Courier-Bold", "Times-Bold"])
        self.opt_font.pack(fill="x", padx=15, pady=5)
        self.opt_font.set(self.config.get("last_font", "Anton-Regular"))

        # Background Music (Default / None / user-supplied file) + Preview
        ctk.CTkLabel(right_col, text="Background Music:", anchor="w").pack(fill="x", padx=15, pady=(15, 0))
        row_music = ctk.CTkFrame(right_col, fg_color="transparent")
        row_music.pack(fill="x", padx=15, pady=5)

        self.custom_music_path = ""
        saved_music = (self.config.get("bg_music_path") or "").strip()
        if saved_music.lower() == "none":
            initial_music = "None (Silent)"
        elif saved_music:
            initial_music = "Custom File..."
            self.custom_music_path = saved_music
        else:
            initial_music = "Default (Bundled)"

        self.var_music = ctk.StringVar(value=initial_music)
        self.opt_music = ctk.CTkOptionMenu(
            row_music, values=["Default (Bundled)", "None (Silent)", "Custom File..."],
            variable=self.var_music, command=self.on_music_change
        )
        self.opt_music.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_music_preview = ctk.CTkButton(row_music, text="▶", width=36, command=self.preview_music)
        self.btn_music_preview.pack(side="left", padx=(0, 5))
        ctk.CTkButton(row_music, text="■", width=36, fg_color="gray", command=sound_preview.stop).pack(side="right")

        self.lbl_music_file = ctk.CTkLabel(right_col, text="", text_color="gray", font=("Arial", 10), anchor="w")
        self.lbl_music_file.pack(fill="x", padx=15)
        self._refresh_music_label()

        # Start background update check after dashboard is loaded
        self.update_checker.start_background_check(self)

    # --- TOGGLE MODES ---
    def toggle_manual_mode(self):
        if self.manual_mode.get():
            self.miniframe_auto.pack_forget()
            self.miniframe_manual.pack(fill="both", expand=True)
        else:
            self.miniframe_manual.pack_forget()
            self.miniframe_auto.pack(fill="both", expand=True)

    # --- STEP 3.5: SCRIPT PREVIEW / EDIT ---
    def start_script_generation(self):
        """Generate (or regenerate) the AI script, then show the preview page."""
        self.bot = None
        self.show_progress_page()
        self.update_progress_display(10, "Generating Viral Script with AI...")
        threading.Thread(target=self._run_script_generation_thread, daemon=True).start()

    def _run_script_generation_thread(self):
        """Background thread: script generation only (no download/render)."""
        try:
            bot = ViralSafeBot(self.config, status_callback=self.update_console,
                               progress_callback=self.update_progress_display, logger=self.logger)
            self.bot = bot  # exposed so the Cancel button can signal it

            script, error = bot.generate_script_and_topic()

            if bot.cancel_requested:
                self.after(0, lambda: self.show_result_page(False, "Generation cancelled by user."))
                return

            if script:
                self.logger.info(f"Script generated with {len(script.get('scenes', []))} scenes, awaiting review")
                self.after(0, lambda: self.show_script_preview_page(script))
            else:
                self.logger.error(f"Script generation failed: {error}")
                self.after(0, lambda: self.show_result_page(False, f"Failed to generate script: {error}"))
        except Exception as e:
            error_message = str(e)
            self.logger.exception("Critical error during script generation")
            self.after(0, lambda: self.show_result_page(False, error_message))

    def show_script_preview_page(self, script):
        """Review & edit the AI script before spending minutes on the render."""
        self.clear_view()
        self.preview_script = script
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(20, 5))
        ctk.CTkLabel(header, text="REVIEW SCRIPT", font=("Arial", 22, "bold"), text_color="cyan").pack(side="left")
        ctk.CTkLabel(header, text="Edit any scene below, then render.", text_color="gray").pack(side="left", padx=15)

        # Action buttons (packed bottom-first so they never scroll off screen)
        btn_row = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=30, pady=20)
        ctk.CTkButton(btn_row, text="Back", width=100, fg_color="gray",
                      command=self.show_main_dashboard).pack(side="left")
        ctk.CTkButton(btn_row, text="🔄 Regenerate Script", width=180, fg_color="#B8860B", hover_color="#8B6508",
                      command=self.start_script_generation).pack(side="left", padx=10)
        ctk.CTkButton(btn_row, text="▶ RENDER VIDEO", font=("Arial", 16, "bold"), height=50,
                      fg_color="green", hover_color="darkgreen",
                      command=self.start_render_from_preview).pack(side="right", fill="x", expand=True, padx=(10, 0))

        # Title
        title_row = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        title_row.pack(fill="x", padx=30, pady=5)
        ctk.CTkLabel(title_row, text="Title:", font=("Arial", 13, "bold"), width=50, anchor="w").pack(side="left")
        self.entry_preview_title = ctk.CTkEntry(title_row)
        self.entry_preview_title.pack(side="left", fill="x", expand=True)
        self.entry_preview_title.insert(0, script.get("title", "Untitled"))

        # Scenes
        scroll = ctk.CTkScrollableFrame(self.current_frame)
        scroll.pack(fill="both", expand=True, padx=30, pady=10)

        self.preview_scene_rows = []
        for i, scene in enumerate(script.get("scenes", [])):
            row = {}
            frame = ctk.CTkFrame(scroll)
            frame.pack(fill="x", pady=6)

            head = ctk.CTkFrame(frame, fg_color="transparent")
            head.pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(head, text=f"Scene {i + 1}", font=("Arial", 13, "bold"),
                         text_color="orange").pack(side="left")
            ctk.CTkButton(head, text="✕ Remove", width=80, height=24, fg_color="#8B1E1E", hover_color="#A52A2A",
                          command=lambda r=row: self._delete_preview_scene(r)).pack(side="right")

            ctk.CTkLabel(frame, text="Dialogue (spoken + captions):", font=("Arial", 11),
                         text_color="gray", anchor="w").pack(fill="x", padx=10)
            dlg = ctk.CTkTextbox(frame, height=60, wrap="word")
            dlg.pack(fill="x", padx=10, pady=(0, 5))
            dlg.insert("1.0", scene.get("dialogue_text", ""))

            ctk.CTkLabel(frame, text="Visual prompt (AI image):", font=("Arial", 11),
                         text_color="gray", anchor="w").pack(fill="x", padx=10)
            prompt = ctk.CTkEntry(frame)
            prompt.pack(fill="x", padx=10, pady=(0, 10))
            prompt.insert(0, scene.get("image_generation_prompt", ""))

            row.update({"frame": frame, "dialogue": dlg, "prompt": prompt, "deleted": False})
            self.preview_scene_rows.append(row)

    def _delete_preview_scene(self, row):
        remaining = [r for r in self.preview_scene_rows if not r["deleted"]]
        if len(remaining) <= 1:
            self._show_validation_error("Cannot Remove", "The script needs at least one scene.")
            return
        row["deleted"] = True
        row["frame"].destroy()

    def _collect_edited_script(self):
        """Build the final script dict from the (possibly edited) preview widgets."""
        scenes = []
        for row in self.preview_scene_rows:
            if row["deleted"]:
                continue
            text = row["dialogue"].get("1.0", "end-1c").strip()
            prompt = row["prompt"].get().strip()
            if not text:
                continue  # blank dialogue = scene removed by clearing it
            scenes.append({
                "scene_id": len(scenes) + 1,
                "dialogue_text": text,
                "image_generation_prompt": prompt or "dark abstract"
            })
        title = self.entry_preview_title.get().strip() or self.preview_script.get("title", "Untitled")
        return {
            "topic": self.preview_script.get("topic", title),
            "title": title,
            "scenes": scenes
        }

    def start_render_from_preview(self):
        script = self._collect_edited_script()
        if not script["scenes"]:
            self._show_validation_error("Empty Script", "At least one scene with dialogue is required.")
            return
        self.logger.info(f"Rendering approved script with {len(script['scenes'])} scenes")
        self.show_progress_page()
        threading.Thread(target=self.run_process, args=(script,), daemon=True).start()

    # --- STEP 4: PROGRESS OVERLAY ---
    def show_progress_page(self):
        self.clear_view()
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True)
        
        # Center Content
        wrapper = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        wrapper.place(relx=0.5, rely=0.5, anchor="center")
        
        # Custom Progress Logic
        self.progress_val = ctk.DoubleVar(value=0.0)
        
        # Upper Label: Status Text
        self.lbl_status_big = ctk.CTkLabel(wrapper, text="INITIALIZING...", font=("Arial", 24, "bold"), text_color="cyan")
        self.lbl_status_big.pack(pady=(20, 10))
        
        # Progress Bar: Determinate
        self.prog_bar = ctk.CTkProgressBar(wrapper, width=400, mode="determinate", variable=self.progress_val)
        self.prog_bar.pack(pady=10)
        self.prog_bar.set(0)
        
        # Lower Label: Percentage
        self.lbl_percent = ctk.CTkLabel(wrapper, text="0%", font=("Arial", 14), text_color="gray")
        self.lbl_percent.pack(pady=(0, 20))
        
        # Cancel button: signals the bot to stop at the next checkpoint
        self.btn_cancel = ctk.CTkButton(
            wrapper, text="Cancel", command=self.cancel_generation,
            height=32, width=160, fg_color="#8B1E1E", hover_color="#A52A2A"
        )
        self.btn_cancel.pack(pady=(15, 0))

        # Console Log (Initially Hidden)
        self.btn_toggle_log = ctk.CTkButton(wrapper, text="Show Logs", command=self.toggle_logs, height=30, fg_color="gray")
        self.btn_toggle_log.pack(pady=(20, 5))

        self.console_frame = ctk.CTkFrame(wrapper, fg_color="transparent")
        self.console_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(self.console_frame, text="Log Output:", anchor="w").pack(fill="x", pady=(5, 5))
        self.console_box = ctk.CTkTextbox(self.console_frame, width=600, height=300, font=("Consolas", 12))
        self.console_box.pack()
        
        # Default state: Hidden
        self.is_log_visible = True # Will be toggled to False immediately below
        self.toggle_logs() 

    def update_progress_display(self, percent, message):
        """Callback from bot to update UI"""
        # Schedule update on main thread
        self.after(0, lambda: self._safe_progress_update(percent, message))

    def _safe_progress_update(self, percent, message):
         self.progress_val.set(percent / 100.0)
         self.lbl_status_big.configure(text=message.upper())
         self.lbl_percent.configure(text=f"{percent}%")
         
         # Optional: Add log entry for major steps
         self._safe_console_update(f"[PROGRESS] {percent}% - {message}")

    def cancel_generation(self):
        """Signal the running bot to stop; disable the button so it can't be spammed."""
        bot = getattr(self, "bot", None)
        if bot is not None:
            bot.request_cancel()
        self.logger.info("User requested cancellation")
        try:
            self.btn_cancel.configure(text="Cancelling...", state="disabled")
        except Exception:
            pass

    def run_process(self, script=None):
        """Background thread for video generation.

        script=None runs the full pipeline (manual mode or legacy path);
        a script dict skips LLM generation and renders the approved script.
        """
        try:
            self.logger.info("Starting video generation process")
            # Pass progress callback
            bot = ViralSafeBot(self.config, status_callback=self.update_console, progress_callback=self.update_progress_display, logger=self.logger)
            self.bot = bot  # exposed so the Cancel button can signal it

            success, msg = bot.run_full_process(script)
            
            if success:
                self.logger.info("Video generation completed successfully")
            else:
                self.logger.error(f"Video generation failed: {msg}")
            
            # Artificial sleep so user can see final logs
            time.sleep(1)
            
            # Switch to Result
            self.after(0, lambda: self.show_result_page(success, msg))
            
        except Exception as e:
            error_message = str(e)
            self.logger.exception("Critical error during video generation")
            self.after(0, lambda: self.show_result_page(False, error_message)) 

    def toggle_logs(self):
        self.is_log_visible = not self.is_log_visible
        if self.is_log_visible:
            self.console_frame.pack(fill="both", expand=True)
            self.btn_toggle_log.configure(text="Hide Logs")
        else:
            self.console_frame.pack_forget()
            self.btn_toggle_log.configure(text="Show Logs")

    def update_console(self, msg):
        self.after(0, lambda: self._safe_console_update(msg))

    def _safe_console_update(self, msg):
        if hasattr(self, 'console_box'):
            self.console_box.configure(state="normal")
            self.console_box.insert("end", msg + "\n")
            self.console_box.see("end")
            self.console_box.configure(state="disabled")

    # --- STEP 5: SUCCESS PAGE ---
    def show_result_page(self, success, msg=""):
        self.clear_view()
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True)

        wrapper = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        if success:
            # Pull "(Time taken: ...)" out of the success message, if present
            time_match = re.search(r"\(Time taken: ([^)]+)\)", msg or "")
            time_taken = time_match.group(1) if time_match else None

            ctk.CTkLabel(wrapper, text="✅", font=("Arial", 60)).pack(pady=10)
            ctk.CTkLabel(wrapper, text="VIDEO GENERATED SUCCESSFULLY!", font=("Arial", 24, "bold"), text_color="green").pack(pady=10)
            ctk.CTkLabel(wrapper, text=f"Saved to: {self.config.get('output_folder')}", font=("Arial", 14), text_color="gray").pack(pady=5)
            if time_taken:
                ctk.CTkLabel(wrapper, text=f"Time taken: {time_taken}", font=("Arial", 14), text_color="gray").pack(pady=5)

            ctk.CTkButton(wrapper, text="GENERATE ANOTHER", font=("Arial", 16, "bold"), height=50, width=300, command=self.show_main_dashboard).pack(pady=30)
            ctk.CTkButton(wrapper, text="Open Folder", font=("Arial", 14), width=300, fg_color="gray", command=self.open_output_folder).pack(pady=5)

            # Direct YouTube upload (needs the rendered file remembered by the bot)
            video_path = getattr(getattr(self, "bot", None), "final_video_path", None)
            if video_path and os.path.exists(video_path):
                if YOUTUBE_UPLOAD_ENABLED:
                    ctk.CTkButton(wrapper, text="⬆ Upload to YouTube", font=("Arial", 14, "bold"), width=300,
                                  fg_color="#CC0000", hover_color="#990000",
                                  command=self.open_upload_dialog).pack(pady=5)
                else:
                    ctk.CTkButton(wrapper, text="⬆ Upload to YouTube (Coming Soon)", font=("Arial", 14, "bold"),
                                  width=300, fg_color="gray", hover_color="gray",
                                  state="disabled").pack(pady=5)
        elif "cancel" in (msg or "").lower():
            # User-initiated cancellation: neutral state, not a failure
            ctk.CTkLabel(wrapper, text="🛑", font=("Arial", 60)).pack(pady=10)
            ctk.CTkLabel(wrapper, text="GENERATION CANCELLED", font=("Arial", 24, "bold"), text_color="orange").pack(pady=10)
            ctk.CTkLabel(wrapper, text="You stopped this run.", font=("Arial", 12), text_color="gray").pack(pady=10)

            ctk.CTkButton(wrapper, text="BACK TO DASHBOARD", font=("Arial", 16, "bold"), height=50, width=300, command=self.show_main_dashboard).pack(pady=30)
        else:
            ctk.CTkLabel(wrapper, text="❌", font=("Arial", 60)).pack(pady=10)
            ctk.CTkLabel(wrapper, text="GENERATION FAILED", font=("Arial", 24, "bold"), text_color="red").pack(pady=10)
            ctk.CTkLabel(wrapper, text=(msg or "")[:200] + "...", font=("Arial", 12), text_color="gray").pack(pady=10)

            ctk.CTkButton(wrapper, text="TRY AGAIN", font=("Arial", 16, "bold"), height=50, width=300, command=self.show_main_dashboard).pack(pady=30)

    # --- YOUTUBE UPLOAD DIALOG ---
    def open_upload_dialog(self):
        if not YOUTUBE_UPLOAD_ENABLED:
            self._show_validation_error("Coming Soon",
                                       "One-click YouTube upload is coming soon.\n"
                                       "For now, export your video and upload it through YouTube Studio.")
            return
        bot = getattr(self, "bot", None)
        video_path = getattr(bot, "final_video_path", None) if bot else None
        if not video_path or not os.path.exists(video_path):
            self._show_validation_error("No Video", "The rendered video file could not be found.")
            return

        secret_path = (self.config.get("yt_client_secret_path") or "").strip()
        if not secret_path or not os.path.exists(secret_path):
            self._show_validation_error("YouTube Not Configured",
                                       "Add your Google client_secret.json in Settings first.\n\n"
                                       "Google Cloud Console → enable 'YouTube Data API v3' → "
                                       "OAuth credentials (Desktop app) → download the JSON.")
            return

        script = getattr(bot, "final_script", None) or {}
        default_title = script.get("title") or os.path.splitext(os.path.basename(video_path))[0]

        # Prefill description from the ready-to-paste caption file
        default_desc = ""
        caption_path = getattr(bot, "final_caption_path", None)
        if caption_path and os.path.exists(caption_path):
            try:
                with open(caption_path, "r", encoding="utf-8") as f:
                    default_desc = f.read().strip()
            except Exception:
                pass

        win = ctk.CTkToplevel(self)
        win.title("Upload to YouTube")
        win.geometry("640x600")
        win.transient(self)
        win.grab_set()

        frame = ctk.CTkFrame(win)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(frame, text="⬆ Upload to YouTube", font=("Arial", 20, "bold")).pack(pady=(5, 2))
        ctk.CTkLabel(frame, text=f"File: {os.path.basename(video_path)}",
                     text_color="gray", font=("Arial", 11)).pack()

        ctk.CTkLabel(frame, text="Title:", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        entry_title = ctk.CTkEntry(frame)
        entry_title.pack(fill="x", padx=10)
        entry_title.insert(0, default_title[:100])

        ctk.CTkLabel(frame, text="Description:", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        box_desc = ctk.CTkTextbox(frame, height=130, wrap="word")
        box_desc.pack(fill="x", padx=10)
        if default_desc:
            box_desc.insert("1.0", default_desc)

        ctk.CTkLabel(frame, text="Privacy:", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        var_privacy = ctk.StringVar(value="private")
        ctk.CTkSegmentedButton(frame, values=["private", "unlisted", "public"],
                               variable=var_privacy).pack(fill="x", padx=10)
        ctk.CTkLabel(frame,
                     text="Note: Google locks uploads from unverified API projects to Private "
                          "until your Cloud project passes verification.",
                     text_color="gray", font=("Arial", 10), wraplength=580,
                     justify="left").pack(fill="x", padx=10, pady=(3, 0))

        prog = ctk.CTkProgressBar(frame, mode="determinate")
        prog.pack(fill="x", padx=10, pady=(15, 3))
        prog.set(0)
        lbl_status = ctk.CTkLabel(frame, text="Ready to upload.", text_color="gray", font=("Arial", 12))
        lbl_status.pack()

        btn_upload = ctk.CTkButton(frame, text="START UPLOAD", font=("Arial", 15, "bold"), height=45,
                                   fg_color="#CC0000", hover_color="#990000")
        btn_upload.pack(fill="x", padx=10, pady=(10, 5))

        widgets = {"win": win, "prog": prog, "status": lbl_status, "btn": btn_upload}

        def start_upload():
            title = entry_title.get().strip()
            if not title:
                lbl_status.configure(text="Title is required.", text_color="red")
                return
            desc = box_desc.get("1.0", "end-1c").strip()
            btn_upload.configure(state="disabled", text="Uploading...")
            lbl_status.configure(text="Starting...", text_color="gray")
            threading.Thread(
                target=self._yt_upload_thread,
                args=(secret_path, video_path, title, desc, var_privacy.get(), widgets),
                daemon=True
            ).start()

        btn_upload.configure(command=start_upload)

    def _yt_upload_status(self, widgets, text, color="gray"):
        def apply():
            try:
                widgets["status"].configure(text=text, text_color=color)
            except Exception:
                pass  # dialog closed
        self.after(0, apply)

    def _yt_upload_thread(self, secret_path, video_path, title, desc, privacy, widgets):
        try:
            uploader = youtube_uploader.YouTubeUploader(secret_path, logger=self.logger)

            if not uploader.is_connected():
                self._yt_upload_status(widgets, "Sign in to Google in the browser window...", "orange")
                uploader.connect()

            self._yt_upload_status(widgets, "Uploading video...")

            def on_progress(percent):
                def apply():
                    try:
                        widgets["prog"].set(percent / 100.0)
                        widgets["status"].configure(text=f"Uploading... {percent}%")
                    except Exception:
                        pass
                self.after(0, apply)

            video_id = uploader.upload(video_path, title, desc,
                                       privacy=privacy, progress_callback=on_progress)
            url = f"https://youtu.be/{video_id}"
            self.logger.info(f"YouTube upload complete: {url}")

            def show_success():
                try:
                    widgets["prog"].set(1.0)
                    widgets["status"].configure(text=f"✅ Uploaded! {url}", text_color="green")
                    widgets["btn"].configure(text="OPEN ON YOUTUBE", state="normal",
                                             fg_color="green", hover_color="darkgreen",
                                             command=lambda: webbrowser.open(url))
                except Exception:
                    pass
            self.after(0, show_success)

        except Exception as e:
            error_message = str(e)
            self.logger.error(f"YouTube upload failed: {error_message}")

            def show_error():
                try:
                    widgets["status"].configure(text=f"❌ {error_message[:160]}", text_color="red")
                    widgets["btn"].configure(state="normal", text="RETRY UPLOAD")
                except Exception:
                    pass
            self.after(0, show_error)

    def open_output_folder(self):
        path = self.config.get("output_folder")
        if os.path.exists(path):
             if os.name == 'nt':
                 os.startfile(path)
             else:
                 os.system(f"xdg-open '{path}'")

    # --- GENERATION LOGIC ---
    def start_generation(self):
        """Validates inputs and starts video generation process"""
        self.logger.info("User initiated video generation")
        
        # === INPUT VALIDATION ===
        
        # 1. Validate API Keys based on Provider
        llm = self.config.get("llm_provider", "groq")
        if llm == "groq":
            key = self.config.get("groq_api_key", "").strip()
            if not key or len(key) < 10:
                self._show_validation_error("Invalid Groq Key", "Please enter a valid Groq API key in Settings.")
                return
        else: # Gemini
            key = self.config.get("gemini_api_key", "").strip()
            if not key or len(key) < 10:
                self._show_validation_error("Invalid Gemini Key", "Please enter a valid Gemini API key in Settings.")
                return
        
        # 2. Validate Output Folder
        output_folder = self.config.get("output_folder", "").strip()
        if not output_folder or output_folder == "output":
            output_folder = os.path.join(os.path.expanduser("~"), "Downloads")
            self.config_manager.set("output_folder", output_folder)
            self.logger.warning(f"No output folder set, defaulting to: {output_folder}")
        
        # Check if folder exists or can be created
        try:
            os.makedirs(output_folder, exist_ok=True)
            # Test write permissions
            test_file = os.path.join(output_folder, ".write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except Exception as e:
            self.logger.error(f"Output folder not writable: {e}")
            self._show_validation_error("Invalid Output Folder",
                                       f"Cannot write to folder: {output_folder}\n"
                                       f"Error: {str(e)}\n\n"
                                       "Please select a different folder in Settings.")
            return
        
        # 3. Validate Custom Prompt (if provided)
        custom_prompt = self.input_prompt.get("1.0", "end-1c").strip()
        if custom_prompt and len(custom_prompt) > 2000:
            self.logger.warning("Custom prompt too long")
            self._show_validation_error("Prompt Too Long",
                                       "Custom prompt must be under 2000 characters.\n"
                                       f"Current length: {len(custom_prompt)}")
            return
        
        # 4. Validate custom background music (if selected)
        if self.var_music.get() == "Custom File..." and not (
                self.custom_music_path and os.path.exists(self.custom_music_path)):
            self._show_validation_error("Music File Missing",
                                       "Custom background music is selected but the file "
                                       "was not found.\nPick the file again or switch to "
                                       "Default/None.")
            return

        # === VALIDATION PASSED ===
        self.logger.info("All validations passed, starting generation")

        # Save current options
        updated_cfg = {
            "last_blueprint": self.var_blueprint.get(),
            "last_topic": self.input_topic.get().strip(),
            "video_format": self.var_video_format.get(),
            "prompt_template": custom_prompt,
            "last_voice_kokoro": voice_catalog.to_voice_id(self.opt_voice.get().strip()),
            "last_font": self.opt_font.get(),
            "tts_provider": "kokoro",
            "bg_music_path": self._music_config_value(),
        }
        self.config_manager.save_config(updated_cfg)
        self.config = self.config_manager.config

        if self.manual_mode.get():
            # Manual scripts were written by the user, so no preview step.
            # Capture the textbox NOW: switching pages destroys the dashboard
            # widgets, so the worker thread can't read them later.
            self.config["manual_script_content"] = self.input_script_manual.get("1.0", "end-1c").strip()
            self.config["use_manual_script"] = True
            self.show_progress_page()
            threading.Thread(target=self.run_process, daemon=True).start()
        else:
            # Auto mode: generate the script first, let the user review/edit
            # it on the preview page, then render.
            self.config["use_manual_script"] = False
            self.start_script_generation()
    
    def _show_validation_error(self, title, message):
        """Shows a validation error dialog"""
        self.logger.warning(f"Validation Error: {title}")
        # Create error popup
        error_window = ctk.CTkToplevel(self)
        error_window.title(title)
        error_window.geometry("500x250")
        error_window.transient(self)
        error_window.grab_set()
        
        # Center the window
        error_window.update_idletasks()
        x = (error_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (error_window.winfo_screenheight() // 2) - (250 // 2)
        error_window.geometry(f"500x250+{x}+{y}")
        
        frame = ctk.CTkFrame(error_window)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(frame, text="⚠️", font=("Arial", 40)).pack(pady=10)
        ctk.CTkLabel(frame, text=title, font=("Arial", 18, "bold"), 
                    text_color="orange").pack(pady=5)
        ctk.CTkLabel(frame, text=message, font=("Arial", 12), 
                    wraplength=450).pack(pady=10)
        ctk.CTkButton(frame, text="OK", width=100, 
                     command=error_window.destroy).pack(pady=10)
        


if __name__ == "__main__":
    cm = ConfigManager()
    app = FacelessApp(cm)
    app.mainloop()
