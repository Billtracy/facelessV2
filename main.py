import os
import sys

# PyInstaller --windowed builds run with NO console, so sys.stdout / sys.stderr
# are None. Any library that writes to them then crashes -- notably tqdm's
# progress bar inside movis.write_video, which fails with
# "AttributeError: 'NoneType' object has no attribute 'write'" and aborts every
# render. Give them a harmless sink so those libraries work in the bundled app.
# (Must happen before importing gui/logic, which pull in movis/tqdm.)
for _stream_name in ("stdout", "stderr"):
    if getattr(sys, _stream_name, None) is None:
        try:
            setattr(sys, _stream_name, open(os.devnull, "w", encoding="utf-8"))
        except Exception:
            pass

from gui import FacelessApp
from config_manager import ConfigManager


def main():
    cm = ConfigManager()
    app = FacelessApp(cm)
    app.mainloop()


if __name__ == "__main__":
    main()
