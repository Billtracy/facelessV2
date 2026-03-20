from gui import FacelessApp
from config_manager import ConfigManager

def main():
    # Initialize Config Manager
    cm = ConfigManager()
    
    # Start App
    app = FacelessApp(cm)
    app.mainloop()

if __name__ == "__main__":
    main()
