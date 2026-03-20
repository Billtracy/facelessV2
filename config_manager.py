import json
import os

class ConfigManager:
    def __init__(self, filename="settings.json"):
        self.filename = filename
        self.default_config = {
            "llm_provider": "groq",
            "gemini_api_key": "",
            "groq_api_key": "",
            "video_provider": "pexels",
            "pixabay_api_key": "",
            "pexels_api_key": "",
            "output_folder": "output",
            "last_blueprint": "Custom Topic",
            "last_topic": "",
            "last_mood": "darkness",
            "last_voice": "en-US-ChristopherNeural",
            "last_font": "Arial-Bold",
            "prompt_template": "You are a viral scriptwriter...",
            "license_key": ""
        }
        self.config = self.load_config()

    def load_config(self):
        """Loads configuration from the file. Returns defaults if file is missing or invalid."""
        if not os.path.exists(self.filename):
            return self.default_config.copy()
        
        try:
            with open(self.filename, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure all keys exist
                config = self.default_config.copy()
                config.update(loaded)
                return config
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.default_config.copy()

    def save_config(self, new_config=None):
        """Saves the current configuration to the file."""
        if new_config:
            self.config.update(new_config)
            
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.config, f, indent=4)
            print("Configuration saved.")
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        """Safely gets a configuration value."""
        return self.config.get(key, default)

    def set(self, key, value):
        """Sets a configuration value and saves instantly."""
        self.config[key] = value
        self.save_config()
