import os
import json
import asyncio
import random
import re
import shutil
import subprocess
import requests
import traceback
import time
import warnings

# pydub warns loudly at import time about missing ffmpeg/ffprobe on PATH. We
# supply ffmpeg via imageio_ffmpeg and route audio loads around ffprobe, so
# these warnings are expected noise -- filter them before importing pydub.
warnings.filterwarnings(
    "ignore",
    message="Couldn't find (ffmpeg or avconv|ffprobe or avprobe).*",
    category=RuntimeWarning,
)

from groq import Groq
import edge_tts
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from retry_utils import retry_with_backoff
from paths import resource_path, user_data_root, user_data_dir, app_dir
import soundfile as sf
import movis
import text_utils
from blueprints import get_blueprint
from script_parsing import parse_manual_script, parse_llm_json

try:
    from kokoro_onnx import Kokoro
except ImportError:
    Kokoro = None

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS


# --- Video assembly tuning constants -------------------------------------
SCENE_PAUSE_MS = 300           # silence appended after each scene's voiceover
END_BUFFER_MS = 1000           # trailing silence so the video doesn't cut off abruptly
END_BUFFER_SEC = END_BUFFER_MS / 1000.0
BG_MUSIC_DUCK_DB = 22          # how far to lower background music under the voice
KEN_BURNS_ZOOM = 1.12          # Ken Burns zoom factor applied to still images
SHORTS_SIZE = (1080, 1920)     # (width, height) vertical / Shorts
LONGFORM_SIZE = (1920, 1080)   # (width, height) horizontal / Long Form

# x264 encode quality for the Movis render. Lower CRF = higher quality/bitrate;
# 20 keeps the detailed AI imagery crisp on motion for a modest size increase
# over the libx264 default of 23. 'medium' preset balances speed vs. compression.
VIDEO_CRF = 20
VIDEO_PRESET = "medium"


class GenerationCancelled(Exception):
    """Raised at a checkpoint when the user requests cancellation."""
    pass



class ViralSafeBot:
    def __init__(self, config, status_callback=None, progress_callback=None, logger=None):
        self.config = config
        self.status_callback = status_callback
        self.progress_callback = progress_callback
        self.logger = logger
        
        # Skip ImageMagick check since we no longer use MoviePy
        self.imagemagick_available = False
        
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.output_folder = self.config.get("output_folder", downloads_path)
        if self.output_folder == "output":
             self.output_folder = downloads_path
             
        # Temp files go to the per-user data folder: the exe folder may be
        # read-only and the cwd is unreliable when launched from a shortcut.
        self.temp_folder = os.path.join(user_data_root(), "temp_assets")
        os.makedirs(self.output_folder, exist_ok=True)
        
        # Clean up old temp files from previous runs
        if os.path.exists(self.temp_folder):
            try:
                shutil.rmtree(self.temp_folder)
                self.log("[*] Cleaned up old temporary files")
            except Exception as e:
                self.log(f"[!] Warning: Could not clean temp folder: {e}")
        
        os.makedirs(self.temp_folder, exist_ok=True)
        

        api_key = self.config.get("groq_api_key")
        self.client = None
        if api_key:
            self.client = Groq(api_key=api_key)
            
        # Initialize Kokoro (Lazy load later)
        self.kokoro = None

        # Cooperative cancellation flag (set by request_cancel from the GUI thread)
        self.cancel_requested = False

        # Populated after a successful render; the GUI's success page reads
        # these to offer the direct YouTube upload.
        self.final_video_path = None
        self.final_caption_path = None
        self.final_script = None

        # Configure ffmpeg from imageio_ffmpeg
        self.ffmpeg_exe = "ffmpeg"  # PATH fallback if imageio_ffmpeg is unavailable
        try:
             import imageio_ffmpeg
             ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
             AudioSegment.converter = ffmpeg_path
             AudioSegment.ffmpeg = ffmpeg_path
             self.ffmpeg_exe = ffmpeg_path
             # Note: imageio_ffmpeg ships ffmpeg but NOT ffprobe, so audio loads
             # go through safe_load_audio (ffmpeg -> wav). The misleading pydub
             # "couldn't find ffprobe" warning is filtered at module import.
             self.log(f"[*] FFMPEG found via imageio_ffmpeg: {ffmpeg_path}")
        except Exception as e:
             self.log(f"[!] Warning: Could not locate imageio ffmpeg: {e}")

    def _run_ffmpeg(self, args):
        """
        Run the bundled ffmpeg binary without flashing a console window.
        Captures stderr so a failure carries ffmpeg's real message instead
        of just an opaque exit code.
        """
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == 'nt':
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run([self.ffmpeg_exe] + args, **kwargs)
        if proc.returncode != 0:
            # Keep the last few lines of ffmpeg output - the reason is at the end
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-6:])
            raise RuntimeError(
                f"ffmpeg exited with code {proc.returncode}.\n{tail}"
            )

    def log(self, message):
        """Log messages to console, callback, and file logger"""
        print(message)
        if self.status_callback:
            self.status_callback(message)
        if self.logger:
            # Remove ANSI color codes for file logging
            clean_msg = message.replace('[!]', '').replace('[*]', '').replace('[-]', '').strip()
            if '[!]' in message or 'Error' in message or 'CRITICAL' in message:
                self.logger.error(clean_msg)
            elif 'SUCCESS' in message:
                self.logger.info(clean_msg)
            else:
                self.logger.debug(clean_msg)

    def report_progress(self, percent, message):
        """Report progress to callback and log"""
        self.log(f"[{percent}%] {message}")
        if self.progress_callback:
            self.progress_callback(percent, message)

    def request_cancel(self):
        """Signal the running generation to stop at the next checkpoint (thread-safe)."""
        self.cancel_requested = True
        self.log("[!] Cancellation requested - stopping at next checkpoint...")

    def _check_cancel(self):
        """Raise GenerationCancelled if a cancel has been requested."""
        if self.cancel_requested:
            raise GenerationCancelled("Generation cancelled by user.")

    def _target_size(self):
        """Return (width, height) for the currently configured video format."""
        return LONGFORM_SIZE if self.config.get("video_format") == "Long Form" else SHORTS_SIZE

    def _write_caption_file(self, script, video_path):
        """
        Write a companion '<video>_caption.txt' next to the rendered video with a
        ready-to-paste title, description, and hashtags. Best-effort: never fatal.
        """
        try:
            title = script.get("title", "Untitled")
            topic = script.get("topic", "")
            first_line = ""
            scenes = script.get("scenes") or []
            if scenes:
                first_line = scenes[0].get("dialogue_text", "").strip()

            hashtags = text_utils.hashtags_from_topic(topic or title)
            caption_path = os.path.splitext(video_path)[0] + "_caption.txt"

            lines = [title, ""]
            if first_line:
                lines += [first_line, ""]
            lines.append(" ".join(hashtags))

            with open(caption_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines).strip() + "\n")

            self.log(f"[*] Caption file written: {caption_path}")
            return caption_path
        except Exception as e:
            self.log(f"[!] Warning: Could not write caption file: {e}")
            return None

    def generate_script_and_topic(self):
        # CHECK MANUAL MODE FIRST
        if self.config.get("use_manual_script"):
             self.log("[*] Manual Mode Active: Parsing user script...")
             script = self._parse_manual_script(self.config.get("manual_script_content", ""))
             if script:
                 return script, None
             return None, "Manual script parsing failed (Empty or Invalid Format)"
             
        if not self.config.get("llm_provider") == "gemini" and not getattr(self, 'client', None):
            msg = "AI Client not initialized (Check API Key)."
            self.log(f"[!] {msg}")
            return None, msg

        # 1. BLUEPRINT & TOPIC SELECTION
        blueprint = self.config.get("last_blueprint", "Custom Topic")
        config_topic = self.config.get("last_topic")
        
        if blueprint == "Custom Topic":
            if config_topic and config_topic.strip():
                selected_topic = config_topic
                self.log(f"[*] Using Custom Topic: {selected_topic}")
            else:
                topics = [
                    "Signs Someone is Lying", "Psychological Tricks to Make Someone Miss You",
                    "Mind-Blowing Space Facts", "History's Deadliest Inventions",
                    "Stoic Rules for a Better Life", "How to Learn Anything Faster"
                ]
                selected_topic = random.choice(topics)
                self.log(f"[*] I'm Feeling Lucky: Selected '{selected_topic}'")
        else:
            selected_topic = blueprint
            self.log(f"[*] Generating Niche Blueprint: {blueprint}")
        
        # 2. DURATION & FORMATTING RULES
        video_format = self.config.get("video_format", "Shorts")
        is_long_form = video_format == "Long Form"
        
        if is_long_form:
             point_count = random.randint(8, 12)
             word_count_rule = "minimum 600 words total across all scenes"
             structure_rule = f"List exactly {point_count} highly detailed points."
        else:
             point_count = random.randint(3, 5)
             word_count_rule = "Strictly 130-150 words MAX total"
             structure_rule = f"List exactly {point_count} punchy, distinct points."

        # 3-4. FETCH BLUEPRINT OR FALLBACK TO GENERIC (catalog lives in blueprints.py)
        bp = get_blueprint(blueprint, selected_topic)

        # 5. ASSEMBLE THE MASTER PROMPT
        master_prompt = f"""
        You are {bp['role']}
        
        TASK: {bp['task']}
        TOPIC: "{selected_topic}"
        
        STRUCTURE (Strictly Follow This):
        1. HOOK: {bp['hook']}
        2. BODY: {structure_rule} Break the script down into short sentences (scenes).
        3. CTA: {bp['cta']}
        
        CRITICAL RULES:
        - PACING: Make it fast, engaging, and highly dramatic.
        - WORD COUNT: {word_count_rule}.
        - FACT-CHECKING: If discussing History, Science, or Law, you MUST use real, verified facts. Do not hallucinate or invent details.
        
        TTS PRONUNCIATION RULES (MANDATORY):
        The `dialogue_text` will be fed directly into a Text-To-Speech engine. You MUST format it so the robot reads it correctly natively:
        1. NO DASHES FOR RANGES: Never write "5-7". You MUST spell it out completely as "five to seven".
        2. NO RAW YEARS: Never write "1999" or "2004". You MUST write them out phonetically as words (e.g., "nineteen ninety-nine", "the year two thousand and four").
        3. SPELL OUT SYMBOLS: You MUST write "percent" instead of "%" and "dollars" instead of "$". Do not use any mathematical symbols.
        
        IMAGE GENERATION RULES (CRUCIAL):
        - For EACH scene, you must provide an 'image_generation_prompt'.
        - DO NOT USE 1-3 words. You must write a highly descriptive, comma-separated string (10-15 words) optimized for an AI image generator.
        - Example: "Cinematic wide shot of an abandoned Soviet spaceship in a frozen wasteland, eerie blue lighting, hyper-realistic, 8k resolution"
        
        JSON ENFORCEMENT:
        You MUST output strict JSON with this exact structure. Do NOT wrap in markdown blocks (no ```json). Plain text only. No asterisks (*).
        
        {{
            "topic": "{selected_topic}",
            "title": "A Searchable, High-Click-Through-Rate Title",
            "scenes": [
                {{
                    "scene_id": 1,
                    "dialogue_text": "The spoken sentence goes here...",
                    "image_generation_prompt": "highly descriptive visual keyword string here..."
                }}
            ]
        }}
        """

        # Custom Prompt Override
        custom_prompt_template = self.config.get("prompt_template")
        if blueprint == "Custom Topic" and custom_prompt_template and len(custom_prompt_template) > 50:
            master_prompt = f"Topic: {selected_topic}. Format as JSON as requested below.\n" + custom_prompt_template

        self.log(f"[*] Asking AI for: {selected_topic} ({video_format})...")

        # Primary Generation (Groq or Gemini based on config)
        script = None
        error_msg = "Unknown Error"
        
        if self.config.get("llm_provider") == "gemini":
            script, error_msg = self._generate_with_gemini(master_prompt, selected_topic)
        else:
            # Default Groq
            script, error_msg = self._generate_with_groq(master_prompt, selected_topic)
            
            # FALLBACK to Gemini if Groq fails
            if not script and self.config.get("gemini_api_key"):
                self.log(f"[!] Groq failed: {error_msg}. Attempting fallback to Gemini...")
                script, error_msg = self._generate_with_gemini(master_prompt, selected_topic)
        
        return script, error_msg
        
    def _generate_with_groq(self, prompt, selected_topic):
        if not self.client:
            return None, "Groq Client not initialized"
            
        try:
            def make_groq_call():
                """Wrapped function for retry logic"""
                return self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a JSON-only API. Output strictly JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    model="llama-3.1-8b-instant",
                    response_format={"type": "json_object"}
                )
            
            chat_completion = retry_with_backoff(
                make_groq_call,
                max_retries=3,
                initial_delay=2.0,
                exceptions=(Exception,),
                logger=self.logger
            )
            
            content = chat_completion.choices[0].message.content
            parsed = self._parse_llm_json(content, selected_topic)
            if parsed:
                return parsed, None
            else:
                return None, "Groq JSON Parse Failed"
                
        except Exception as e:
            err = f"Groq API Error: {str(e)}"
            self.log(f"[!] {err}")
            return None, err

    def _generate_with_gemini(self, prompt, selected_topic):
        try:
            api_key = self.config.get("gemini_api_key")
            if not api_key:
                return None, "Gemini API Key missing"
                
            from google import genai
            client = genai.Client(api_key=api_key)
            
            response = client.models.generate_content(
                # Use the newer model for script generation (text-only)
                model='gemini-2.5-flash', 
                contents=prompt,
                config={
                    'response_mime_type': 'application/json'
                }
            )
            parsed = self._parse_llm_json(response.text, selected_topic)
            if parsed:
                return parsed, None
            else:
                return None, "Gemini JSON Parse Failed"
                
        except Exception as e:
            err = f"Gemini API Error: {str(e)}"
            self.log(f"[!] {err}")
            return None, err

    def _parse_manual_script(self, raw_text):
        """Parse manual 'Caption | Visual Query' text (see script_parsing.py)."""
        return parse_manual_script(raw_text, self.log)

    def _parse_llm_json(self, content, selected_topic):
        """Normalize raw LLM JSON into the script dict (see script_parsing.py)."""
        return parse_llm_json(content, selected_topic, self.log)


    def trim_audio_silence(self, audio_segment):
        """
        Removes silent parts from the start/end of the audio clip
        to ensure perfect text sync.
        """
        non_silent_ranges = detect_nonsilent(audio_segment, min_silence_len=50, silence_thresh=-40)
        
        if non_silent_ranges:
            start_trim = non_silent_ranges[0][0]
            end_trim = non_silent_ranges[-1][1]
            return audio_segment[start_trim:end_trim]
        else:
            return audio_segment 

    def safe_load_audio(self, file_path):
        """
        Robustly load audio files without requiring ffmpeg/ffprobe on PATH.
        pydub's generic from_file() shells out to ffprobe, which customer
        machines don't have, so WAV gets a pure-python fast path and
        everything else falls back to the bundled imageio ffmpeg binary.
        """
        if not os.path.exists(file_path):
            self.log(f"[!] Audio file missing: {file_path}")
            return AudioSegment.silent(duration=500)

        # 1. WAV fast path (no ffmpeg/ffprobe involved)
        if file_path.lower().endswith(".wav"):
            try:
                return AudioSegment.from_wav(file_path)
            except Exception:
                pass

        # 2. Direct load (works when ffmpeg/ffprobe are installed system-wide)
        try:
            return AudioSegment.from_file(file_path)
        except Exception:
            pass

        # 3. Fallback: bundled FFmpeg -> WAV -> pydub
        temp_wav = file_path + ".temp_loader.wav"
        try:
            self._run_ffmpeg(["-y", "-i", file_path, "-acodec", "pcm_s16le", "-ar", "44100", temp_wav])
            return AudioSegment.from_wav(temp_wav)
        except Exception as fallback_error:
            self.log(f"[!] CRITICAL: Failed to load audio {file_path} even with fallback. Error: {fallback_error}")
            raise
        finally:
            if os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except OSError:
                    pass

    async def generate_audio_for_line(self, text, index):
        # Determine Provider
        provider = self.config.get("tts_provider", "kokoro")

        if provider == "kokoro":
            # WAV: written by soundfile, loadable without ffmpeg.
            # _generate_kokoro_tts raises on failure - fall through to a
            # fresh .mp3 path for Edge TTS rather than reusing this one
            # (Edge TTS writes MP3 bytes, which would corrupt a .wav path).
            filename = f"{self.temp_folder}/line_{index}.wav"
            try:
                voice_id = self.config.get("last_voice_kokoro", "af_heart")
                await self._generate_kokoro_tts(text, voice_id, filename)
                return filename
            except Exception as e:
                self.log(f"[!] Kokoro TTS failed: {e}. Falling back to Edge TTS.")

        # Default Edge TTS (either selected provider, or Kokoro fallback)
        filename = f"{self.temp_folder}/line_{index}.mp3"
        voice_id = self.config.get("last_voice", "en-US-ChristopherNeural")
        # +10% speed is the viral sweet spot
        communicate = edge_tts.Communicate(text, voice_id, rate="+10%")
        await communicate.save(filename)
        return filename

    def _ensure_kokoro_models(self):
        """Return (onnx_path, voices_path) for Kokoro.

        Prefers model files shipped WITH the app (bundled via PyInstaller, or the
        repo's models/ folder in dev) so no 80MB first-run download is needed.
        Only if those are absent does it fall back to downloading into a writable
        models/ folder next to the executable.
        """
        onnx_name = "kokoro-v0_19.int8.onnx"
        voices_bin_name = "voices.bin"

        # 1. Prefer bundled copies (resource_path -> sys._MEIPASS when frozen).
        bundled_onnx = resource_path(os.path.join("models", onnx_name))
        bundled_voices = resource_path(os.path.join("models", voices_bin_name))
        if os.path.exists(bundled_onnx) and os.path.exists(bundled_voices):
            self.log("[*] Using bundled Kokoro model (no download needed).")
            return bundled_onnx, bundled_voices

        # 2. Fall back to downloading into a writable dir next to the app.
        self.log("[*] Bundled Kokoro model not found; will download if missing.")
        models_dir = os.path.join(app_dir(), "models")
        os.makedirs(models_dir, exist_ok=True)

        onnx_path = os.path.join(models_dir, "kokoro-v0_19.int8.onnx")
        voices_path = os.path.join(models_dir, "voices.json") # The raw JSON download
        voices_json_path = voices_path
        voices_bin_path = os.path.join(models_dir, "voices.bin") # The converted binary
        
        # URLs for 0.19 quantized model
        onnx_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.int8.onnx"
        voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json"
        
        # Cleanup old large model if exists
        old_onnx_path = os.path.join(models_dir, "kokoro-v0_19.onnx")
        if os.path.exists(old_onnx_path):
             try:
                 os.remove(old_onnx_path)
                 self.log("[*] Removed old large Kokoro model (300MB+) to save space.")
             except: pass
        
        if not os.path.exists(onnx_path):
            self.log("[*] Downloading Kokoro Quantized Model (80MB)... This runs only once.")
            self._download_file(onnx_url, onnx_path)
            
        if not os.path.exists(voices_path):
            self.log("[*] Downloading Kokoro Voices...")
            self._download_file(voices_url, voices_path)
            
        # Conversion Logic: voices.json -> voices.bin (npz)
        # Kokoro-onnx requires a binary file loadable by np.load(), JSON text causes pickle errors.
        if not os.path.exists(voices_bin_path) and os.path.exists(voices_json_path):
            self.log("[*] Converting voices.json to binary format for Kokoro...")
            try:
                with open(voices_json_path, 'r') as f:
                    data = json.load(f)
                
                voices = {}
                for name, val in data.items():
                    voices[name] = np.array(val, dtype=np.float32)
                
                # Save as .npz (numpy archive) which np.load can read safely
                np.savez(voices_bin_path, **voices)
                
                # np.savez appends .npz, we rename to keep it clean if desired, or just use it
                if os.path.exists(voices_bin_path + ".npz"):
                    os.rename(voices_bin_path + ".npz", voices_bin_path)
                    
                self.log("[+] Voice conversion complete.")
            except Exception as e:
                self.log(f"[!] Voice conversion failed: {e}")
        
        # Prefer the binary file if it exists
        final_voices_path = voices_bin_path if os.path.exists(voices_bin_path) else voices_json_path
            
        return onnx_path, final_voices_path

    def _download_file(self, url, path):
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
    def _sanitize_for_espeak(self, text):
        """Sanitize text for espeak TTS (see text_utils.sanitize_for_espeak)."""
        return text_utils.sanitize_for_espeak(text)

    def _sanitize_for_display(self, text):
        """Sanitize dialogue_text for on-screen display (see text_utils.sanitize_for_display)."""
        return text_utils.sanitize_for_display(text)

    async def _generate_kokoro_tts(self, text, voice_name, output_file):
        """Generates audio using local Kokoro-82M"""
        try:
            if not Kokoro:
                raise ImportError("kokoro-onnx not installed")
                
            if not self.kokoro:
                onnx_path, voices_path = self._ensure_kokoro_models()
                self.kokoro = Kokoro(onnx_path, voices_path)

            # Fallback if voice not found (e.g. af_heart -> af)
            available_voices = self.kokoro.get_voices()
            if voice_name not in available_voices:
                self.log(f"[!] Voice '{voice_name}' not found. Falling back to default 'af'.")
                if "af" in available_voices:
                    voice_name = "af"
                elif available_voices:
                    voice_name = available_voices[0]
                    self.log(f"[!] 'af' also missing. Using '{voice_name}'.")
            
            # AGGRESSIVE sanitization to prevent espeak line-count mismatches
            text = self._sanitize_for_espeak(text)
            
            # Split into sentences to prevent espeak from generating mismatched line counts
            sentences = re.split(r'(?<=[.!?])\s+', text)
            all_samples = []
            sample_rate = 24000
            
            import numpy as np
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence: continue
                
                try:
                    samps, sr = self.kokoro.create(
                        sentence, 
                        voice=voice_name, 
                        speed=1.0, 
                        lang="en-us"
                    )
                    all_samples.append(samps)
                    sample_rate = sr
                except Exception as chunk_ex:
                    error_str = str(chunk_ex)
                    self.log(f"[!] Kokoro chunk retry for '{sentence[:30]}': {error_str}")
                    
                    # FALLBACK 1: Split on commas into smaller clauses
                    safe_clauses = [c.strip() for c in re.split(r'[,]', sentence) if c.strip()]
                    
                    if len(safe_clauses) > 1:
                        self.log(f"[*] Splitting into {len(safe_clauses)} smaller clauses")
                        for clause in safe_clauses:
                            try:
                                samps, sr = self.kokoro.create(
                                    clause, 
                                    voice=voice_name, 
                                    speed=1.0, 
                                    lang="en-us"
                                )
                                all_samples.append(samps)
                                sample_rate = sr
                            except Exception:
                                # FALLBACK 2: Strip ALL non-alphanumeric chars
                                safe_clause = re.sub(r'[^a-zA-Z0-9\s]', '', clause).strip()
                                if safe_clause:
                                    try:
                                        samps, sr = self.kokoro.create(safe_clause, voice=voice_name, speed=1.0, lang="en-us")
                                        all_samples.append(samps)
                                        sample_rate = sr
                                    except Exception as final_ex:
                                        self.log(f"[!] Skipping unrecoverable clause: '{safe_clause[:20]}' ({final_ex})")
                    else:
                        # FALLBACK 2: Nuclear option - strip everything non-alphanumeric
                        safe_sentence = re.sub(r'[^a-zA-Z0-9\s]', '', sentence).strip()
                        if safe_sentence:
                            try:
                                samps, sr = self.kokoro.create(
                                    safe_sentence, 
                                    voice=voice_name, 
                                    speed=1.0, 
                                    lang="en-us"
                                )
                                all_samples.append(samps)
                                sample_rate = sr
                            except Exception as final_ex:
                                self.log(f"[!] Skipping unrecoverable sentence: '{safe_sentence[:20]}' ({final_ex})")
                        
            if not all_samples:
                raise ValueError("No audio generated from Kokoro.")
                
            final_samples = np.concatenate(all_samples)
            sf.write(output_file, final_samples, sample_rate)
            
        except Exception as e:
            self.log(f"[!] Kokoro TTS Error: {e}. Falling back to Edge TTS...")
            # Fallback to Edge TTS if Kokoro fails
            voice_id = self.config.get("last_voice", "en-US-ChristopherNeural")
            communicate = edge_tts.Communicate(text, voice_id, rate="+10%")
            await communicate.save(output_file)




    async def generate_all_audio(self, scenes):
        """
        scenes: list of dicts {'dialogue_text': '...', ...}
        """
        tasks = []
        for i, item in enumerate(scenes):
            text = item.get('dialogue_text', '')
            tasks.append(self.generate_audio_for_line(text, i))
        return await asyncio.gather(*tasks)

    async def _generate_pollen_image(self, query, index):
        """Generates an image using Pollinations.ai"""
        full_query = f"{query}, highly detailed, cinematic lighting, 8k resolution"        
        import urllib.parse
        encoded_prompt = urllib.parse.quote(full_query)
        is_long_form = self.config.get("video_format") == "Long Form"
        width = 1920 if is_long_form else 1080
        height = 1080 if is_long_form else 1920
        seed = random.randint(1, 1000000)
        
        pollen_key = self.config.get("pollen_api_key", "").strip()
        
        if pollen_key:
            url_base = f"https://gen.pollinations.ai/image/{encoded_prompt}?width={width}&height={height}&seed={seed}&nologo=true"
        else:
            url_base = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&seed={seed}&nologo=true"
            
        fname = f"bg_{index}_{random.randint(1000,9999)}.jpg"
        output_path = os.path.join(self.temp_folder, fname)
        
        models = ["flux", "turbo", ""] 
        
        try:
            def download_img():
                last_err = None
                for model in models:
                    model_param = f"&model={model}" if model else ""
                    current_url = url_base + model_param
                    req_headers = {"Connection": "close"}
                    if pollen_key:
                        req_headers["Authorization"] = f"Bearer {pollen_key}"
                    
                    try:
                        with requests.get(current_url, headers=req_headers, stream=True, timeout=120) as r:
                            r.raise_for_status()
                            with open(output_path, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192): 
                                    if chunk:
                                        f.write(chunk)
                        return output_path 
                    except Exception as e:
                        last_err = e
                        import time
                        time.sleep(1) 
                
                raise Exception(f"All models failed. Last error: {last_err}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: retry_with_backoff(
                    download_img,
                    max_retries=3,
                    initial_delay=3.0,
                    exceptions=(Exception,),
                    logger=self.logger
                )
            )
            return True, output_path
        except Exception as e:
            return False, str(e)

    async def _download_video_bg(self, video_link, index):
        v_fname = f"bg_{index}_{random.randint(1000,9999)}.mp4"
        v_output_path = os.path.join(self.temp_folder, v_fname)
        
        try:
            def download_video():
                req_headers = {"Connection": "close"}
                with requests.get(video_link, headers=req_headers, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    expected = int(r.headers.get("Content-Length", 0))
                    written = 0
                    with open(v_output_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                written += len(chunk)
                # A truncated download decodes past its header but breaks movis
                # mid-render, so reject it here and let retry_with_backoff retry.
                if expected and written < expected:
                    raise IOError(f"Truncated video download: got {written} of {expected} bytes")
                return v_output_path
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: retry_with_backoff(
                    download_video,
                    max_retries=3,
                    initial_delay=2.0,
                    exceptions=(requests.exceptions.RequestException, Exception),
                    logger=self.logger
                )
            )
            return True, v_output_path
        except Exception as e2:
            return False, f"[!] Stock Video Fallback Error: {e2}"

    async def download_single_background(self, query, index):
        success = False
        msg = ""
        try:
            # TRY POLLINATIONS (IMAGE)
            success, msg = await self._generate_pollen_image(query, index)
            if not success:
                self.log(f"[~] Pollinations failed: {msg}. Falling back to Pexels Video...")
                video_link = await self._search_pexels(query)
                if video_link:
                    success, msg = await self._download_video_bg(video_link, index)
                else:
                    msg = "No Pexels videos found for fallback."
        except Exception as final_e:
            self.log(f"[!] Background generation logic error: {final_e}")
            success, msg = False, str(final_e)
        
        return msg if success else None

    async def _search_pexels(self, query):
        # Prefer the customer's own key (Settings); the shared fallback key
        # ships inside the binary and can get rate-limited for everyone.
        key = (self.config.get("pexels_api_key") or "").strip()
        if not key:
            key = "3vDp08ehXYBwPMaKMUgHED9Jqxa3cvykQoiQMjSsvx0dMGvPRN1TwfYp"

        headers = {'Authorization': key, 'Connection': 'close'}
        orientation = "landscape" if self.config.get("video_format") == "Long Form" else "portrait"
        url = f"https://api.pexels.com/videos/search?query={query}&orientation={orientation}&per_page=10"
        
        try:
             loop = asyncio.get_event_loop()
             r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, timeout=30))
             data = r.json()
            
             if not data.get('videos'): return None
            
             video = random.choice(data['videos'])
            
             # Smart Quality Selection: Prefer HD (1080w for portrait) over 4K
             # Smart Quality Selection: Prefer HD
             # Portrait target: 1080w (video is typically 1080x1920)
             # Landscape target: 1920w (video is typically 1920x1080)
             is_long_form = self.config.get("video_format") == "Long Form"
             target_width = 1920 if is_long_form else 1080
            
             files = video.get('video_files', [])
             best_file = min(files, key=lambda f: abs(f.get('width', 0) - target_width))
            
             if best_file:
                  return best_file['link']
             else:
                  return files[0]['link']
        except Exception as e:
            self.log(f"[!] Pexels Error: {e}")
            return None

    async def download_backgrounds_for_scenes(self, scenes):
        """
        Downloads a background for EACH scene based on its image_generation_prompt.
        Returns a list of file paths (or None if failed), corresponding to indices.
        """
        self.log(f"[*] Downloading visuals for {len(scenes)} scenes...")
        self.report_progress(50, "Searching & Downloading visuals...")
        
        results = []
        for i, scene in enumerate(scenes):
            query = scene.get('image_generation_prompt', 'dark abstract')
            res = await self.download_single_background(query, i)
            results.append(res)
            if i < len(scenes) - 1:
                await asyncio.sleep(2.0) # Respect Pollinations.ai rate limits
        # results is a list of paths (or None)
        
        # Fallback for failures: fill None with a random valid one or generic
        valid_paths = [p for p in results if p and not p.startswith('[!') and not p.startswith('No ')]
        if not valid_paths:
             # If completely failed, try one generic download
             fallback_success, fallback_path = await self._generate_pollen_image("dark abstract", -1)
             if not fallback_success:
                 fallback_link = await self._search_pexels("dark abstract")
                 if fallback_link:
                     fallback_success, fallback_path = await self._download_video_bg(fallback_link, -1)
             
             if fallback_success:
                 valid_paths.append(fallback_path)
             else:
                 # Last resort: if we have NO files, we can't make a video
                 return []
                 
        final_paths = []
        for res in results:
            if res and not res.startswith('[!') and not res.startswith('No '):
                final_paths.append(res)
            else:
                final_paths.append(random.choice(valid_paths))
                
        return final_paths

    def create_highlighted_text_image(self, words, active_index, font_name, fontsize, color, highlight_color, stroke_width, size):
        """Generates a premium Hormozi-style text image with the active word highlighted and popped."""
        w, h_min = size
        
        # We need a dummy draw object to measure fonts before creating the final canvas
        dummy_img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_img)
        
        try:
             font_map = {
                 "Arial-Bold": "arialbd.ttf",
                 "Impact": "impact.ttf", 
                 "Verdana-Bold": "verdanab.ttf",
                 "Courier-Bold": "courbd.ttf",
                 "Times-Bold": "timesbd.ttf",
                 "Anton-Regular": "Anton-Regular.ttf"
             }
             
             # Fallback to Anton-Regular if Arial isn't requested or isn't available
             user_font_file = font_map.get(font_name, "Anton-Regular.ttf")
             
             # Check if it's in the bundled assets/fonts folder first
             local_font_path = resource_path("assets", "fonts", user_font_file)
             if os.path.exists(local_font_path):
                 font_file = local_font_path
             else:
                 # Otherwise try system fonts
                 font_file = user_font_file
                 
             font = ImageFont.truetype(font_file, fontsize)
             active_font = ImageFont.truetype(font_file, fontsize + 12) # Pop effect for active word
        except Exception as e:
             # Silencing the font fallback warnings
             try:
                 default_font_path = resource_path("assets", "fonts", "Anton-Regular.ttf")
                 font = ImageFont.truetype(default_font_path, fontsize)
                 active_font = ImageFont.truetype(default_font_path, fontsize + 12)
             except Exception as inner_e:
                 self.log(f"[!] Fatal: Even Anton failed. Using tiny bitmap default: {inner_e}")
                 font = ImageFont.load_default()
                 active_font = font

        max_line_width = w - 40
        lines = []
        current_line = []
        current_line_width = 0
        
        word_metrics = []
        for i, word in enumerate(words):
            word = word.upper() # Fix: measure uppercase since we draw uppercase
            # Drop trailing/leading sentence punctuation for a clean viral caption
            # look (upstream chunking already used the punctuation as a break hint).
            word = text_utils.strip_caption_punct(word)
            use_font = active_font if i == active_index else font
            bbox = draw.textbbox((0, 0), word, font=use_font)
            ww = draw.textlength(word, font=use_font) # Use true advance width
            wh = bbox[3] - bbox[1]
            word_metrics.append({"word": word, "width": ww, "height": wh, "font": use_font, "index": i})

        space_w = draw.textlength(" ", font=font) + 12 # True advance width with extra padding

        for wm in word_metrics:
            if current_line_width + wm["width"] <= max_line_width:
                current_line.append(wm)
                current_line_width += wm["width"] + space_w
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [wm]
                current_line_width = wm["width"] + space_w
        if current_line:
            lines.append(current_line)
            
        line_height = fontsize + 25 
        total_text_height = len(lines) * line_height
        
        # Dynamic height to prevent cutoff on long sentences
        actual_h = max(h_min, total_text_height + 60)
        
        # Create actual image
        img = Image.new('RGBA', (w, actual_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        y = (actual_h - total_text_height) // 2
        
        for line in lines:
            line_w = sum(wm["width"] for wm in line) + space_w * (len(line) - 1)
            x = (w - line_w) // 2
            
            for wm in line:
                fill_color = highlight_color if wm["index"] == active_index else color
                fnt = wm["font"]
                word_text = wm["word"] # Already uppercased
                
                # Heavy Drop Shadow
                shadow_offset = 6
                draw.text((x + shadow_offset, y + shadow_offset), word_text, font=fnt, fill='black', stroke_width=stroke_width, stroke_fill='black')
                
                # Main Text with Native Vectorized Stroke
                draw.text((x, y), word_text, font=fnt, fill=fill_color, stroke_width=stroke_width, stroke_fill='black')
                
                x += wm["width"] + space_w
                
            y += line_height
            
        return np.array(img)

    def create_word_by_word_clip(self, full_line, total_duration, cumulative_start):
        """
        Premium Hormozi-style animated scenes.
        Shows the full wrapped sentence, highlighting and popping the active word.
        """
        clips = []
        words = full_line.split()
        if not words:
            return clips
        
        # Character-weighted word durations for better audio sync
        # Longer words get proportionally more display time
        char_counts = [max(len(w), 1) for w in words]
        total_chars = sum(char_counts)
        word_durations = [(c / total_chars) * total_duration for c in char_counts]
        # Enforce minimum duration per word
        word_durations = [max(d, 0.1) for d in word_durations]
        
        fontsize = 85 # Premium size
        user_font = self.config.get("last_font", "Anton-Regular")
        highlight_color = "#FFD700" # Vibrant Yellow
        
        # Intelligent Text Chunking (track word indices for timing)
        chunks = []           # list of word lists
        chunk_word_indices = [] # list of (start_word_idx, end_word_idx) tuples
        current_chunk = []
        chunk_start_idx = 0
        for i, w in enumerate(words):
            current_chunk.append(w)
            has_punct = bool(re.search(r'[.,!?;:\-]$', w))
            is_last_word = (i == len(words) - 1)
            
            if is_last_word:
                chunks.append(current_chunk)
                chunk_word_indices.append((chunk_start_idx, i))
                current_chunk = []
            elif has_punct and len(current_chunk) >= 2:
                chunks.append(current_chunk)
                chunk_word_indices.append((chunk_start_idx, i))
                current_chunk = []
                chunk_start_idx = i + 1
            elif len(current_chunk) >= 4: # Screen width optimization -> 4 words max
                words_left = len(words) - i - 1
                if words_left == 1:
                    pass # Let it become a 5-word chunk to avoid a 1-word orphan
                else:
                    chunks.append(current_chunk)
                    chunk_word_indices.append((chunk_start_idx, i))
                    current_chunk = []
                    chunk_start_idx = i + 1
        if current_chunk:
            chunks.append(current_chunk)
            chunk_word_indices.append((chunk_start_idx, len(words) - 1))
            
        # Determine the most important word per chunk
        # Rules: Longest word, ignoring simple stop words
        stop_words = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "in", "at", "to", "of", "is", "are", "was", "were"}
        
        chunk_clips = []
        for ci, chunk in enumerate(chunks):
            if not chunk: continue
            
            # Find the index of the most important (longest non-stop) word
            best_idx = 0
            max_len = -1
            for idx, w in enumerate(chunk):
                clean_w = re.sub(r'[^a-zA-Z0-9]', '', w.lower())
                if clean_w not in stop_words and len(clean_w) > max_len:
                    max_len = len(clean_w)
                    best_idx = idx
            
            # If all were stop words, just highlight the longest one anyway
            if max_len == -1:
                best_idx = max(range(len(chunk)), key=lambda i: len(chunk[i]))
            
            # Calculate timing from tracked word indices (NOT words.index())
            start_word_idx, end_word_idx = chunk_word_indices[ci]
            chunk_start_time = cumulative_start + sum(word_durations[:start_word_idx])
            chunk_duration = sum(word_durations[start_word_idx:end_word_idx + 1])
            # Slightly reduce duration to prevent overlap with next chunk
            chunk_duration = max(chunk_duration - 0.05, 0.1)
            
            img_array = self.create_highlighted_text_image(
                words=chunk,
                active_index=best_idx, # Only highlight the most important word
                font_name=user_font,
                fontsize=fontsize,
                color='white',
                highlight_color=highlight_color,
                stroke_width=5,
                size=(950, 950) 
            )
            
            chunk_clips.append({
                "image": img_array,
                "start": chunk_start_time,
                "duration": chunk_duration
            })
            
        return chunk_clips

    def get_sfx(self, name):
        """Helper to get SFX audio segment"""
        path = resource_path("assets", "sfx", name)

        if not os.path.exists(path):
            return None

        try:
            # Check file size, if 0 byte (placeholder), return silent
            if os.path.getsize(path) < 100:
                return AudioSegment.silent(duration=500)
            # Route through safe_load_audio so it survives a missing system ffprobe
            # (imageio_ffmpeg ships ffmpeg only, not ffprobe).
            return self.safe_load_audio(path)
        except Exception as e:
            self.log(f"[!] Warning: Could not load SFX '{name}': {e}")
            return None

    def inject_sfx(self, audio_segment, text, previous_text=""):
        """
        Analyzes text to inject sound effects.
        Returns modified audio_segment.
        """
        text_lower = text.lower()
        
        # 0. Scene Transition SFX
        if previous_text != "":
            transition_sfx = self.get_sfx("whoosh.mp3")
            if transition_sfx:
                # Lower volume significantly so it's subtle, not disruptive
                transition_sfx = transition_sfx - 15
                audio_segment = audio_segment.overlay(transition_sfx, position=0)
        
        # 1. BOOM for heavy words
        if any(w in text_lower for w in ["shocking", "suddenly", "stop", "warning", "never"]):
            boom = self.get_sfx("boom.mp3")
            if boom:
                # Overlay at start
                audio_segment = audio_segment.overlay(boom, position=0)
        
        # 2. WHOOSH for list items (Number X, Sign #1)
        # Check if text starts with a number or "sign"
        if re.search(r'^(sign|#|number|trick|tip)\s*\d', text_lower) or \
           (re.search(r'^\d', text_lower)):
            whoosh = self.get_sfx("whoosh.mp3")
            if whoosh:
                audio_segment = audio_segment.overlay(whoosh, position=0)
                
        # 3. GLITCH for "Dark Psychology"
        if "dark psychology" in text_lower:
            glitch = self.get_sfx("glitch.mp3")
            if glitch:
                audio_segment = audio_segment.overlay(glitch, position=0)
                
        # 4. CAMERA SHUTTER for facts (maybe random if no other sfx?)
        # Let's say if it contains "fact" or "truth"
        if "fact" in text_lower or "truth" in text_lower:
            shutter = self.get_sfx("camera_shutter.mp3")
            if shutter:
                audio_segment = audio_segment.overlay(shutter, position=0)
                
        return audio_segment

    async def assemble_video(self, script, bg_paths):
        self.report_progress(60, f"Assembling V2 Masterpiece: {script.get('topic', 'Unknown')}...")
        
        if not bg_paths:
             self.log("[!] No backgrounds available. Aborting assembly.")
             return
             
        # PARALLEL AUDIO GENERATION
        self.report_progress(65, "Generating voiceovers in parallel...")
        audio_files = await self.generate_all_audio(script['scenes'])
             
        audio_segments = []
        all_visual_clips = []
        total_duration = 0.0
        
        num_scenes = len(script['scenes'])
        self.log(f"[*] Assembling {num_scenes} scenes with synced audios/visuals...")

        # bg_paths ideally corresponds 1:1 to scenes. If some downloads failed the
        # lists differ in length and we wrap around with modulo -- warn when that
        # happens so a silently-reused/mismatched background is visible in the logs.
        if len(bg_paths) != num_scenes:
            self.log(
                f"[!] Warning: {len(bg_paths)} background(s) for {num_scenes} scene(s); "
                f"some scenes will reuse backgrounds (wrap-around)."
            )

        for i, scene_obj in enumerate(script['scenes']):
            self._check_cancel()
            # Per-scene progress across the assembly band (65% -> 82%)
            if num_scenes:
                self.report_progress(
                    65 + int(17 * i / num_scenes),
                    f"Assembling scene {i + 1} of {num_scenes}..."
                )
            text = scene_obj.get('dialogue_text', '')
            # --- AUDIO PROCESSING ---
            audio_file = audio_files[i]
            # Safe load
            raw_seg = self.safe_load_audio(audio_file)
            # Trim silence
            seg = self.trim_audio_silence(raw_seg)
            # Add pause
            seg = seg + AudioSegment.silent(duration=SCENE_PAUSE_MS)

            # --- SFX INJECTION ---
            prev_text = script['scenes'][i-1]['dialogue_text'] if i > 0 else ""
            seg = self.inject_sfx(seg, text, prev_text)

            dur_sec = len(seg) / 1000.0

            # --- VISUAL PROCESSING (SYNCED) ---
            # Get specific background for this scene
            bg_file = bg_paths[i % len(bg_paths)]

            try:
                target_w, target_h = self._target_size()

                if bg_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                     # PREMIUM FEATURE: Ken Burns Effect on AI Images
                     from PIL import Image
                     base_img = Image.open(bg_file).convert("RGB")
                     
                     # Resize to cover exactly
                     img_ratio = base_img.width / base_img.height
                     tgt_ratio = target_w / target_h
                     if img_ratio > tgt_ratio:
                         new_h = target_h
                         new_w = int(new_h * img_ratio)
                     else:
                         new_w = target_w
                         new_h = int(new_w / img_ratio)
                     # Use LANCZOS (ANTIALIAS replacement)
                     resample_mode = getattr(Image, 'Resampling', Image).LANCZOS
                     base_img = base_img.resize((new_w, new_h), resample_mode)
                     
                     # Center crop
                     left = (new_w - target_w) / 2
                     top = (new_h - target_h) / 2
                     base_img = base_img.crop((left, top, left + target_w, top + target_h))
                     
                     bg_layer = movis.layer.Image(base_img)
                     all_visual_clips.append({
                         "layer": bg_layer,
                         "start": total_duration,
                         "duration": dur_sec,
                         "type": "image"
                     })
                     
                else:
                    # Video logic via Movis
                    bg_layer = movis.layer.Video(bg_file)
                    
                    # If video is too short, it might disappear in Movis, 
                    # but typically stock videos are 10s+, and sentences are < 5s.
                    # We just rely on scale handling
                    all_visual_clips.append({
                        "layer": bg_layer,
                        "start": total_duration,
                        "duration": dur_sec,
                        "type": "video"
                    })
                
            except Exception as e:
                self.log(f"[!] Video Clip Error for {bg_file}: {e}")
                # Fallback: create black clip
                fallback = movis.layer.Rectangle((target_w, target_h), color=(0,0,0))
                all_visual_clips.append({
                    "layer": fallback,
                    "start": total_duration,
                    "duration": dur_sec,
                    "type": "fallback"
                })

            # --- TEXT OVERLAY ---
            display_text = self._sanitize_for_display(text)
            typewriter_clips = self.create_word_by_word_clip(display_text, dur_sec, total_duration)
            for txt_clip in typewriter_clips:
                txt_layer = movis.layer.Image(txt_clip["image"])
                all_visual_clips.append({
                    "layer": txt_layer,
                    "start": txt_clip["start"],
                    "duration": txt_clip["duration"],
                    "type": "text"
                })
            
            audio_segments.append(seg)
            total_duration += dur_sec

        # --- FINAL ASSEMBLY ---

        # Add trailing buffer to audio so the video doesn't cut off abruptly
        audio_segments.append(AudioSegment.silent(duration=END_BUFFER_MS))
        total_duration_video = total_duration + END_BUFFER_SEC

        # Extend the last visual clip to cover the buffer (prevents black screen at end)
        for clip_data in reversed(all_visual_clips):
            if clip_data["type"] != "text":
                clip_data["duration"] += END_BUFFER_SEC  # Extend last background over buffer
                break
            
        final_audio_path = f"{self.output_folder}/final_audio.mp3"
        full_voice = sum(audio_segments)
        
        # --- BACKGROUND MUSIC ---
        # Config "bg_music_path": "" -> bundled default track, "none" -> music
        # disabled, anything else -> user-supplied audio file.
        default_music = os.path.join(resource_path("assets"), "audio", "bg-music.mp3")
        bg_choice = (self.config.get("bg_music_path") or "").strip()
        if bg_choice.lower() == "none":
            bg_music_path = None
            self.log("[*] Background music disabled by user.")
        elif bg_choice:
            bg_music_path = bg_choice
            if not os.path.exists(bg_music_path):
                self.log(f"[!] Custom music file missing: {bg_music_path}. Using bundled track.")
                bg_music_path = default_music
            else:
                self.log(f"[*] Using custom background music: {os.path.basename(bg_music_path)}")
        else:
            # Use resource_path so this resolves inside a PyInstaller bundle (assets
            # are extracted to sys._MEIPASS), consistent with fonts/SFX loading.
            bg_music_path = default_music

        if bg_music_path and os.path.exists(bg_music_path):
            try:
                self.log("[*] Adding background music...")
                bg_track = self.safe_load_audio(bg_music_path)

                # Lower volume significantly so it doesn't overpower the voice
                bg_track = bg_track - BG_MUSIC_DUCK_DB
                
                # Loop bg music if it's shorter than the voice track
                voice_len_ms = len(full_voice)
                if len(bg_track) < voice_len_ms:
                    loop_count = (voice_len_ms // len(bg_track)) + 1
                    bg_track = bg_track * loop_count
                    
                # Trim to exact length of voiceover
                bg_track = bg_track[:voice_len_ms]
                
                # Overlay
                full_voice = full_voice.overlay(bg_track)
            except Exception as e:
                self.log(f"[!] Warning: Failed to mix background music: {e}")
                
        full_voice.export(final_audio_path, format="mp3")
        
        self._check_cancel()
        self.report_progress(85, "Rendering final video composition with Movis...")

        target_w, target_h = self._target_size()

        comp = movis.layer.Composition(size=(target_w, target_h), duration=total_duration_video)
        
        zoom_in = True
        for clip_data in all_visual_clips:
            layer_obj = clip_data["layer"]
            start_t = clip_data["start"]
            end_t = start_t + clip_data["duration"]
            
            if clip_data["type"] == "text":
                comp_item = comp.add_layer(
                    layer_obj, 
                    start_time=start_t, 
                    end_time=end_t, 
                    position=(target_w // 2, int(target_h * 0.65))
                )
            else:
                comp_item = comp.add_layer(layer_obj, start_time=start_t, end_time=end_t)
            
            if clip_data["type"] == "image":
                # Ken Burns Effect alternating zoom in / zoom out
                zoom_factor = KEN_BURNS_ZOOM
                # Note: Movis interprets keyframes based on absolute composition time
                motion = comp_item.scale.enable_motion()
                if zoom_in:
                     motion.append(start_t, (1.0, 1.0)).append(end_t, (zoom_factor, zoom_factor))
                else:
                     motion.append(start_t, (zoom_factor, zoom_factor)).append(end_t, (1.0, 1.0))
                zoom_in = not zoom_in
            elif clip_data["type"] == "video":
                # Center and scale to fill
                layer_w, layer_h = layer_obj.size
                ratio_w = target_w / layer_w
                ratio_h = target_h / layer_h
                s = max(ratio_w, ratio_h)
                comp_item.scale = (s, s)
                
        safe_title = text_utils.safe_filename(script['title'])
        temp_vid = f"{self.output_folder}/{safe_title}_temp_movis.mp4"
        out_file = f"{self.output_folder}/{safe_title}_V2.0.mp4"
        
        # Render silent video directly with FFmpeg via Movis (blazing fast compared to MoviePy).
        # Pass explicit x264 quality so detailed AI imagery stays crisp on motion.
        comp.write_video(
            temp_vid,
            output_params=["-crf", str(VIDEO_CRF), "-preset", VIDEO_PRESET]
        )
        
        # Mux audio with FFmpeg
        self.report_progress(95, "Muxing Audio with FFmpeg...")
        import subprocess
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        mux_ok = False
        try:
             proc = subprocess.run([
                 ffmpeg_exe, "-y", "-i", temp_vid, "-i", final_audio_path,
                 "-c:v", "copy", "-c:a", "aac", out_file
             ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
             if proc.returncode != 0:
                 err = proc.stderr.decode("utf-8", "ignore").strip().splitlines()
                 detail = err[-1] if err else f"exit code {proc.returncode}"
                 raise RuntimeError(detail)
             mux_ok = True
        except Exception as e:
             self.log(f"[!] Muxing failed: {e}")

        # Verify the final file actually exists and is non-empty before claiming success.
        if not (mux_ok and os.path.exists(out_file) and os.path.getsize(out_file) > 0):
             # Keep the silent temp video around so the run isn't a total loss / is debuggable.
             self.log(f"[!] Final muxed video was not produced. Silent render kept at: {temp_vid}")
             raise RuntimeError(
                 f"Failed to produce final video (audio muxing did not complete). "
                 f"Silent video preserved at: {temp_vid}"
             )

        self.log(f"\n[SUCCESS] Video Saved: {out_file}")

        # Write a ready-to-paste caption/hashtags file next to the video
        caption_path = self._write_caption_file(script, out_file)

        # Remember the outputs for the GUI (YouTube upload button etc.)
        self.final_video_path = out_file
        self.final_caption_path = caption_path
        self.final_script = script

        # Robust Temp Cleanup (only reached once the final video exists)
        try:
             import gc
             gc.collect()
             if os.path.exists(temp_vid):
                 os.remove(temp_vid)
             shutil.rmtree(self.temp_folder, ignore_errors=True)
             os.makedirs(self.temp_folder, exist_ok=True)
        except Exception as cleanup_err:
             self.log(f"[!] Warning: temp cleanup failed: {cleanup_err}")

    def _format_elapsed(self, seconds):
        """Format a duration in seconds (see text_utils.format_elapsed)."""
        return text_utils.format_elapsed(seconds)

    async def run_full_process_async(self, script=None):
        """Async wrapper for the full process.

        If `script` is provided (already generated and approved/edited by the
        user on the preview page), the LLM generation step is skipped.
        """
        start_time = time.time()
        try:
            self.report_progress(0, "Initializing and checking API keys...")

            self._check_cancel()
            if script is None:
                self.report_progress(10, "Generating Viral Script with AI...")
                script, error = self.generate_script_and_topic()
                if not script:
                     return False, f"Failed to generate script: {error}"
            else:
                self.report_progress(10, "Rendering approved script...")

            self.log(f"Topic: {script.get('topic', 'Unknown')}")

            # PARALLEL DOWNLOADS for PER-CAPTION VISUALS
            self._check_cancel()
            bg_paths = await self.download_backgrounds_for_scenes(script['scenes'])

            if not bg_paths:
                 return False, "Failed to download backgrounds (Pexels API Error or no results)."

            # Assemble video
            await self.assemble_video(script, bg_paths)
            elapsed = self._format_elapsed(time.time() - start_time)
            return True, f"Video generated successfully! (Time taken: {elapsed})"

        except GenerationCancelled as e:
            self.log(f"[!] {e}")
            return False, "Generation cancelled by user."
        except Exception as e:
            err_details = traceback.format_exc()
            self.log(f"[CRITICAL ERROR]\n{err_details}")
            return False, f"Critical Logic Error:\n{err_details}"
        finally:
            elapsed = self._format_elapsed(time.time() - start_time)
            self.log(f"[*] Time taken: {elapsed}")
            # Final safety cleanup
            try:
                import gc
                gc.collect()
                if os.path.exists(self.temp_folder):
                    shutil.rmtree(self.temp_folder, ignore_errors=True)
                    os.makedirs(self.temp_folder, exist_ok=True)
            except Exception as cleanup_error:
                self.log(f"[!] Failed to cleanup temp folder: {cleanup_error}")

    def run_full_process(self, script=None):
        """Entry point for worker threads. Runs the async pipeline to completion."""
        # asyncio.run() creates, drives, and cleanly closes a fresh event loop for
        # this thread -- the modern replacement for the deprecated get_event_loop().
        return asyncio.run(self.run_full_process_async(script))


if __name__ == "__main__":
    print("Run via gui.py or main.py for full features.")