# Faceless Channel Generator - Complete Build & Distribution Guide

This guide covers everything from pre-build preparation to customer delivery.

---

## 📋 PRE-BUILD CHECKLIST

Before building your EXE, ensure these are configured:

### 1. License Server Setup

✅ **Your license server is already configured:**
- License API: `https://stingray-app-flk7o.ondigitalocean.app`
- Location: `license_validator.py` (line 14)

**What this means:**
- ✅ No hardcoded keys in your app
- ✅ No rebuilds needed when adding customers
- ✅ Manage licenses from your admin dashboard
- ✅ Automatic activation tracking

### 2. Gumroad Integration (Optional)

**For automated Gumroad sales:**

1. **Verify your Product Permalink:**
   - Open `license_validator.py`
   - Line 18: `self.gumroad_product_permalink = "rlrsql"`
   - Update this to match your actual Gumroad product URL

2. **Gumroad serves as fallback:**
   - If your license server is down, app falls back to Gumroad
   - Customers can use either:
     - License from your server (via admin dashboard)
     - Gumroad purchase key (automatic)

**To disable Gumroad fallback:**
```python
# license_validator.py, line 17
self.use_gumroad_fallback = False
```

---

### 3. Remove Test Data

**CRITICAL - Do this before EVERY build:**

1. **Check `settings.json`:**
   - Open the file
   - Ensure it does NOT contain your real API keys
   - If it does, delete them or reset to empty strings

2. **Verify `.gitignore`:**
   - Confirm `settings.json` is listed (it already is)
   - This prevents accidentally committing API keys

---

### 4. Version Bump (Recommended)

1. Open `version.py`
2. Update `CURRENT_VERSION = "X.X.X"` to your new version
3. This shows in the app title bar and is sent to license server

---

## 🔨 BUILDING THE EXE

### Step 1: Install PyInstaller

Open your terminal in the project folder:

```bash
pip install pyinstaller
```

### Step 2: Prepare Icon (Optional)

If you have `app_icon.png`:
1. Convert it to `.ico` format using an online converter
2. Save as `icon.ico` in the project root
3. If you don't have this, the build will work without it.

### Step 3: Run the Build Command

**PREFERRED METHOD — Use the .spec file:**

```bash
pyinstaller FacelessGenerator.spec --noconfirm
```

**OR copy and paste this command (equivalent):**

```bash
pyinstaller --noconfirm --onedir --windowed --name "FacelessGenerator" --add-data "settings_template.json;." --add-data "assets;assets" --collect-all customtkinter --collect-all groq --collect-all edge_tts --collect-all movis --collect-all kokoro_onnx --copy-metadata imageio --copy-metadata requests --copy-metadata packaging --hidden-import "pydub" --hidden-import "requests" --hidden-import "PIL" --hidden-import "PIL.ImageDraw" --hidden-import "PIL.ImageFont" --hidden-import "numpy" --hidden-import "soundfile" --hidden-import "tkinter" --hidden-import "tkinter.ttk" --hidden-import "tkinter.font" --hidden-import "google.genai" --icon "icon.ico" main.py
```

**If you don't have `icon.ico`, remove** `--icon "icon.ico"` from the command.

**What's new:**
- `--add-data "assets;assets"` - **CRITICAL:** Bundles fonts, SFX, and background music.
- `--collect-all movis` - Required for the video rendering engine.
- `--collect-all kokoro_onnx` - Required for the premium local TTS engine.
- `--hidden-import "soundfile"` - Required for processing audio samples.
- `--hidden-import "google.genai"` - Required for Gemini AI provider.
- `--copy-metadata packaging` - Fixes version resolution for core libraries.

**What this does:**
- `--onedir` - Creates a folder with all dependencies.
- `--windowed` - Hides the console window (GUI only).
- Output goes to `dist/FacelessGenerator/`.


---

## ✅ TESTING YOUR BUILD

**CRITICAL: Test on YOUR machine first!**

### Test 1: Basic Launch

1. Navigate to `dist/FacelessGenerator/`
2. Double-click `FacelessGenerator.exe`
3. Should show license entry screen.
4. Enter a valid license key (Gumroad or manual).

### Test 2: First-Run Settings

1. After license activation, you'll see Settings page.
2. Enter dummy API keys:
   - Groq: `gsk_test1234567890` (just for testing).
   - Gemini: `AIzatest1234567890`.
3. Set output folder.
4. Click Save & Continue.

### Test 3: Check Auto-Created Files

The app should create:
- `settings.json` in the EXE folder (your customer's config, separate from yours!).
- Log files at `%APPDATA%/FacelessGenerator/logs/`.
- `models/` folder (on first run) containing the Kokoro TTS voice files.

### Test 4: Verify No Leaked Data

**CRITICAL CHECK:**

1. Search the `dist/FacelessGenerator/` folder for your REAL API keys.
2. Open any `.json` files you find.
3. Confirm they don't contain your REAL Groq or Gemini keys.
4. If they do, **DELETE THE BUILD** and restart from Pre-Build Checklist.

---

## 📦 PACKAGING FOR DISTRIBUTION

### Step 1: Clean the Build

Before zipping, optionally delete these (saves space):
- `build/` folder (not needed).
- `*.spec` files (not needed).
- Keep only `dist/FacelessGenerator/`.

### Step 2: Create Distribution Archive

**For Gumroad (Global):**
1. Right-click `dist/FacelessGenerator` folder.
2. Send to → Compressed (zipped) folder.
3. Rename to `FacelessGenerator_v1.2.0.zip`.

**For Offline Sales (Nigeria/Local):**
1. Same zip process
2. Upload to Google Drive or Mega
3. Set link to "Anyone with link can download"

### Step 3: Upload to Gumroad

1. Go to your Gumroad product page
2. Content tab → Add file
3. Upload the `.zip` file
4. Add instructions: "Extract the ZIP, run FacelessGenerator.exe, and enter your license key when prompted"

---

## 📧 CUSTOMER DELIVERY

### For Gumroad Customers (Automated)

1. Customer purchases on Gumroad
2. They receive:
   - Download link to your ZIP
   - Their unique Gumroad license key
3. They download, extract, run, and enter their key
4. App validates online → Unlocks automatically

### For Offline Customers (Manual)

Send them an email with:

```
Hi [Customer],

Thanks for your purchase! Here's how to get started:

1. Download: [Google Drive Link]
2. Extract the ZIP file.
3. Run FacelessGenerator.exe.
4. Enter this license key: OFFLINE_XXX

Setup Instructions:
- You'll need an AI API key (get a free one for Groq: https://console.groq.com).
- No stock video API keys are needed; the app handles media automatically!

Need help? Reply to this email!
```

---

## 🐛 TROUBLESHOOTING

### "ModuleNotFoundError: No module named 'customtkinter' or 'movis'"

**This means PyInstaller didn't bundle the libraries properly.**

**Solution:**
1. Delete the old build:
   ```bash
   rmdir /s dist
   rmdir /s build
   del *.spec
   ```

2. Rebuild with the updated command (includes `--collect-all`).
udes `--collect-all customtkinter`)

3. If still failing, try this alternative:
   ```bash
   pip install --upgrade customtkinter
   pip install --upgrade pyinstaller
   ```
   Then rebuild.

---

### Build Fails with "Module not found"

- Add the missing module to `--hidden-import` in the build command
- Common ones: `packaging`, `certifi`, `urllib3`
- For example: `--hidden-import "packaging"`

---

### EXE Won't Run on Customer's Machine

- Ensure they have Windows 10+ (Windows 7 may need Visual C++ Redistributable)
- Check their antivirus isn't blocking it
- Ask them to send you the log file from `%APPDATA%/FacelessGenerator/logs/`

---

### "Invalid License" for Valid Keys

- Check your Gumroad permalink is correct in `license_validator.py`
- Ensure customer has internet connection (for Gumroad validation)
- Check Gumroad API status

---

## 🔄 RE-BUILDING (Updates)

When you fix bugs or add features:

1. Update `version.py` with the new version number
2. Run Pre-Build Checklist again
3. Run the same PyInstaller command
4. Test the new build
5. Upload to Gumroad as a new file
6. **Notify existing customers** about the update

> 💡 **Tip:** For automatic updates, implement the update checker from your previous conversation!

---

## 📊 DISTRIBUTION SUMMARY

| Customer Type | Payment Method | License Source | Validation |
| :--- | :--- | :--- | :--- |
| Global (Automated) | Gumroad | Gumroad email | Online API |
| Offline (Manual) | Bank/Paystack | You assign key | Hardcoded list |
| Beta Testers | Free | Manual key | Hardcoded list |

---

## ✨ FINAL CHECKLIST

Before sending to first customer:

- [ ] Gumroad permalink configured in code
- [ ] Manual keys added (if doing offline sales)
- [ ] `settings.json` doesn't contain YOUR API keys
- [ ] Build completed without errors
- [ ] Tested license validation on your machine
- [ ] Tested file creation (logs, settings)
- [ ] Verified no data leakage in ZIP
- [ ] ZIP uploaded to Gumroad
- [ ] Product description includes setup instructions
- [ ] Support email/contact method set up

**You're ready to launch! 🚀**
---

## Part 5: Releasing Updates (For V7.0.1, V8.0.0, etc.)

When you release a new version with bug fixes or new features, follow these steps:

### Step 1: Update Version Number
1. Open `version.py`.
2. Change `CURRENT_VERSION = "7.0.0"` to your new version (e.g., `"7.0.1"` for patches, `"7.1.0"` for features, `"8.0.0"` for major changes).

### Step 2: Build the New Version
1. Follow **Part 3** above to rebuild the app with PyInstaller.
2. Test the new EXE to ensure it works correctly.

### Step 3: Upload to Gumroad
1. Go to your Gumroad product page.
2. Navigate to the **Content** tab.
3. Upload the new Zip file (replace the old one or add it as a new file).
4. **Important**: All existing customers will automatically have access to the new version in their Gumroad library. Their license keys will still work!

### Step 4: Create/Update version.json
1. Create a file called `version.json` with this exact format:
   ```json
   {
     "version": "7.0.1",
     "download_url": "https://YOUR_PRODUCT_URL_HERE"
   }
   ```
2. Update `version` to match your new version.
3. Set `download_url` to your Gumroad product page (e.g., `https://gumroad.com/l/mycoolapp`) or direct download link.
4. Upload this file to a public URL (GitHub Pages, your website, etc.).

### Step 5: Update the Remote URL in Code
1. Open `updater.py`.
2. Find the line: `self.remote_url = remote_url or "https://YOUR_WEBSITE.com/faceless/version.json"`
3. Replace with your actual URL (do this ONCE before your first release).

### How It Works
- When users open the app, it checks `version.json` in the background.
- If a new version exists, they get a popup notification with a download button.
- Their existing license key works on all new versions (lifetime free updates!).
