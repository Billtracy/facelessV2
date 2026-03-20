"""
Auto-update checker for Faceless Channel Generator.
Checks a remote version.json file and notifies users of available updates.
"""

import requests
import threading
import webbrowser
from packaging import version
from version import CURRENT_VERSION, APP_NAME
import customtkinter as ctk


class UpdateChecker:
    def __init__(self, remote_url=None):
        """
        Initialize the update checker.
        
        Args:
            remote_url: URL to the version.json file. 
                       Format: {"version": "7.0.1", "download_url": "https://..."}
        """
        # TODO: Replace this with your actual URL where you'll host version.json
        self.remote_url = remote_url or "https://YOUR_WEBSITE.com/faceless/version.json"
        
    def check_for_updates(self):
        """
        Check if a new version is available.
        
        Returns:
            tuple: (is_available, download_url, new_version)
                   - is_available: bool indicating if update exists
                   - download_url: str URL to download the update
                   - new_version: str version number of the new release
        """
        try:
            response = requests.get(self.remote_url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            remote_version = data.get("version", "0.0.0")
            download_url = data.get("download_url", "")
            
            # Compare versions using packaging library
            if version.parse(remote_version) > version.parse(CURRENT_VERSION):
                return (True, download_url, remote_version)
            else:
                return (False, "", remote_version)
                
        except Exception as e:
            # Silent fail - don't interrupt user experience if update check fails
            pass  # Silently fail - updater is non-critical
            return (False, "", "")
    
    def prompt_update_if_available(self, parent_window):
        """
        Show an update dialog if a new version is available.
        
        Args:
            parent_window: The parent CTk window to center the dialog on
        """
        is_available, download_url, new_version = self.check_for_updates()
        
        if is_available and download_url:
            # Create update dialog
            dialog = ctk.CTkToplevel(parent_window)
            dialog.title("Update Available")
            dialog.geometry("450x250")
            dialog.resizable(False, False)
            
            # Center the dialog
            dialog.lift()
            dialog.focus()
            
            # Content
            frame = ctk.CTkFrame(dialog)
            frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            ctk.CTkLabel(
                frame, 
                text="🎉 Update Available!", 
                font=("Arial", 20, "bold"),
                text_color="#00FF88"
            ).pack(pady=(10, 5))
            
            ctk.CTkLabel(
                frame,
                text=f"Version {new_version} is now available!",
                font=("Arial", 14)
            ).pack(pady=5)
            
            ctk.CTkLabel(
                frame,
                text=f"(You're running version {CURRENT_VERSION})",
                font=("Arial", 11),
                text_color="gray"
            ).pack(pady=(0, 20))
            
            ctk.CTkLabel(
                frame,
                text="Your license key will work on the new version.\nWould you like to download it now?",
                font=("Arial", 12)
            ).pack(pady=10)
            
            # Buttons
            btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
            btn_frame.pack(pady=20)
            
            def download_update():
                webbrowser.open(download_url)
                dialog.destroy()
            
            ctk.CTkButton(
                btn_frame,
                text="Download Update",
                command=download_update,
                width=150,
                height=40,
                fg_color="green",
                hover_color="darkgreen"
            ).pack(side="left", padx=10)
            
            ctk.CTkButton(
                btn_frame,
                text="Not Now",
                command=dialog.destroy,
                width=150,
                height=40,
                fg_color="gray",
                hover_color="darkgray"
            ).pack(side="left", padx=10)
            
            # Make dialog modal
            dialog.transient(parent_window)
            dialog.grab_set()
        else:
            # No update available - could show message or do nothing
            pass
    
    def start_background_check(self, parent_window):
        """
        Start update check in background thread to avoid freezing GUI.
        
        Args:
            parent_window: The parent CTk window
        """
        def check_thread():
            # Small delay to let app finish loading
            import time
            time.sleep(2)
            
            # Run check on main thread (required for GUI operations)
            parent_window.after(0, lambda: self.prompt_update_if_available(parent_window))
        
        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()
