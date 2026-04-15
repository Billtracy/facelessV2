import customtkinter as ctk
import threading
import os
import time
from config_manager import ConfigManager
from logic import ViralSafeBot
from license_validator import LicenseValidator
from logger import AppLogger
from version import CURRENT_VERSION, APP_NAME
from updater import UpdateChecker
from resource_path import resource_path

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
        
        # ROUTING LOGIC (Bypassed License Check)
        if not self._check_credits_exist():
            self.show_credentials_page()
        else:
            self.show_main_dashboard()
            
    def _check_credits_exist(self):
        # Basic check if at least one LLM and one Video key exists
        c = self.config
        return (c.get("groq_api_key") or c.get("gemini_api_key")) and \
               (c.get("pexels_api_key") or c.get("pixabay_api_key"))

    def clear_view(self):
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
        voices_dir = os.path.join(resource_path("."), "voices")
        if not os.path.isdir(voices_dir):
            return []
        wav_files = sorted([
            os.path.splitext(f)[0]
            for f in os.listdir(voices_dir)
            if f.lower().endswith(".wav")
        ])
        return wav_files

    def update_voice_options(self, *args):
        self.frame_google_creds.pack_forget()
        # Kokoro Voices (Verified from voices.bin)
        voices = [
            "af",           # Default Female (Heart)
            "af_bella",
            "af_nicole",
            "af_sarah",
            "af_sky",
            "am_adam",
            "am_michael",
            "bf_emma",
            "bf_isabella",
            "bm_george",
            "bm_lewis"
        ]
        self.opt_voice.configure(values=voices)
        
        # Auto-correct old saved voice "af_heart" -> "af"
        saved = self.config.get("last_voice_kokoro", "af")
        if saved == "af_heart": saved = "af"
        if saved not in voices: saved = "af"
        
        self.opt_voice.set(saved)
            
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

    def save_credentials(self, go_to_main):
        new_conf = {
             "llm_provider": "gemini" if "Gemini" in self.combo_llm.get() else "groq",
             "groq_api_key": self.entry_groq_cred.get().strip(),
             "gemini_api_key": self.entry_gemini_cred.get().strip(),
             "pollen_api_key": self.entry_pollen_cred.get().strip(),
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

        
        # Voice (Editable Combobox for Custom Voice ID)
        ctk.CTkLabel(right_col, text="Narrator Voice:", anchor="w").pack(fill="x", padx=15, pady=(15,0))
        self.opt_voice = ctk.CTkComboBox(right_col, values=[
            "en-US-ChristopherNeural", 
            "en-US-GuyNeural", 
            "en-US-EricNeural", 
            "en-GB-RyanNeural", 
            "en-US-JennyNeural",
            "en-AU-NatashaNeural"
        ])
        self.opt_voice.pack(fill="x", padx=15, pady=5)
        
        # Init state
        self.update_voice_options() # Refresh UI state

        
        # Font
        ctk.CTkLabel(right_col, text="Caption Font:", anchor="w").pack(fill="x", padx=15, pady=(15,0))
        self.opt_font = ctk.CTkOptionMenu(right_col, values=["Anton-Regular", "Arial-Bold", "Impact", "Verdana-Bold", "Courier-Bold", "Times-Bold"])
        self.opt_font.pack(fill="x", padx=15, pady=5)
        self.opt_font.set(self.config.get("last_font", "Anton-Regular"))

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

    def run_process(self):
        """Background thread for video generation"""
        try:
            self.logger.info("Starting video generation process")
            # Pass progress callback
            bot = ViralSafeBot(self.config, status_callback=self.update_console, progress_callback=self.update_progress_display, logger=self.logger)
            
            # Check for Manual Override
            if self.manual_mode.get():
                raw_script = self.input_script_manual.get("1.0", "end-1c").strip()
                self.config["manual_script_content"] = raw_script
                self.config["use_manual_script"] = True
            else:
                self.config["use_manual_script"] = False
                
            success, msg = bot.run_full_process()
            
            if success:
                self.logger.info("Video generation completed successfully")
            else:
                self.logger.error(f"Video generation failed: {msg}")
            
            # Artificial sleep so user can see final logs
            time.sleep(1)
            
            # Switch to Result
            self.after(0, lambda: self.show_result_page(success, msg if not success else ""))
            
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
    def show_result_page(self, success, error_msg=""):
        self.clear_view()
        self.current_frame = ctk.CTkFrame(self)
        self.current_frame.pack(fill="both", expand=True)
        
        wrapper = ctk.CTkFrame(self.current_frame, fg_color="transparent")
        wrapper.place(relx=0.5, rely=0.5, anchor="center")
        
        if success:
            ctk.CTkLabel(wrapper, text="✅", font=("Arial", 60)).pack(pady=10)
            ctk.CTkLabel(wrapper, text="VIDEO GENERATED SUCCESSFULLY!", font=("Arial", 24, "bold"), text_color="green").pack(pady=10)
            ctk.CTkLabel(wrapper, text=f"Saved to: {self.config.get('output_folder')}", font=("Arial", 14), text_color="gray").pack(pady=5)
            
            ctk.CTkButton(wrapper, text="GENERATE ANOTHER", font=("Arial", 16, "bold"), height=50, width=300, command=self.show_main_dashboard).pack(pady=30)
            ctk.CTkButton(wrapper, text="Open Folder", font=("Arial", 14), width=300, fg_color="gray", command=self.open_output_folder).pack(pady=5)
        else:
            ctk.CTkLabel(wrapper, text="❌", font=("Arial", 60)).pack(pady=10)
            ctk.CTkLabel(wrapper, text="GENERATION FAILED", font=("Arial", 24, "bold"), text_color="red").pack(pady=10)
            ctk.CTkLabel(wrapper, text=error_msg[:200] + "...", font=("Arial", 12), text_color="gray").pack(pady=10)
            
            ctk.CTkButton(wrapper, text="TRY AGAIN", font=("Arial", 16, "bold"), height=50, width=300, command=self.show_main_dashboard).pack(pady=30)

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
        
        # === VALIDATION PASSED ===
        self.logger.info("All validations passed, starting generation")
        
        # Save current options
        updated_cfg = {
            "last_blueprint": self.var_blueprint.get(),
            "last_topic": self.input_topic.get().strip(),
            "video_format": self.var_video_format.get(),
            "prompt_template": custom_prompt,
            "last_voice_kokoro": self.opt_voice.get(),
            "last_font": self.opt_font.get(),
            "tts_provider": "kokoro",
            # "google_creds_path": ... removed
        }
        self.config_manager.save_config(updated_cfg)
        self.config = self.config_manager.config
        
        # Switch to Progress
        self.show_progress_page()
        
        # Start generation thread (daemon so it closes with app)
        threading.Thread(target=self.run_process, daemon=True).start()
    
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
