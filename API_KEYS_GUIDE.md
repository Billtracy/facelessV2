# How to Get Your API Keys (Step-by-Step Guide)

This application relies on external AI services to generate scripts, voices, and visuals. To use them, you'll need to obtain your own API keys for the AI providers.

---

## 1. AI Scriptwriters (Required)

You must provide at least one of these in the **Settings**.

### Option A: Groq API Key (Recommended for Speed)

**Cost**: Free (Beta) | **Speed**: Instant  
Best for fast iterations and quick video generation.

1. **Website**: Go to [https://console.groq.com/keys](https://console.groq.com/keys).
2. **Sign Up**: Create a free account.
3. **Create Key**: Click **"Create API Key"**, name it "FacelessApp", and copy the string (starts with `gsk_`).
4. **Enter in App**: Paste into the "Groq API Key" field in Settings.

### Option B: Google Gemini API Key (Recommended for Quality)

**Cost**: Free Tier Available | **Quality**: Creative & Nuanced  
Best for high-quality storytelling and complex scripts.

1. **Website**: Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. **Sign In**: Use your standard Google account.
3. **Create Key**: Click **"Create API Key"** and copy the string (starts with `AIza`).
4. **Enter in App**: Paste into the "Gemini API Key" field in Settings.

---

## 2. Visuals & Media (Automatic)

### Pexels & Pixabay

**Status**: **No API Key Required.**  
As of the latest update, the app handles stock video search automatically in the background using a built-in provider key. You no longer need to sign up for Pexels or Pixabay unless you want to use them for your own external projects.

---

## 3. AI Image Generation (Optional)

### Pollinations.ai API Key

**Cost**: Free / Optional Paid  
The app uses Pollinations.ai to generate unique cinematic images for your scenes.

1. **Is it required?**: No. The app works out of the box without a Pollen key.
2. **Why add one?**: If you find results are slow or you're hitting "Rate Limit" errors during peak hours, you can provide a Pollen API key to get priority access.
3. **Where to get it**: Visit [https://pollinations.ai/](https://pollinations.ai/) for more information on priority access.

---

## 4. Text-to-Speech (Dynamic)

### Kokoro & Edge TTS
**Status**: **No API Key Required.**
- **Kokoro (Default)**: Runs locally on your computer for high-quality, human-like narration. No internet required for voice generation once the model is downloaded.
- **Edge TTS (Fallback)**: Used automatically if Kokoro encounters a complex sentence. High-quality Microsoft cloud voices.

---

## 5. Direct YouTube Upload (Optional)

**Cost**: Free | Lets the app upload finished videos straight to your channel.

Because uploads go to **your** YouTube channel, Google requires you to create your own (free) credentials:

1. **Create a project**: Go to [https://console.cloud.google.com/](https://console.cloud.google.com/) and create a new project (any name, e.g. "FacelessUploader").
2. **Enable the API**: In "APIs & Services" → "Library", search for **YouTube Data API v3** and click **Enable**.
3. **Configure consent screen**: In "APIs & Services" → "OAuth consent screen", choose **External**, fill in the app name and your email, and add your own Google account as a **Test user**.
4. **Create credentials**: In "APIs & Services" → "Credentials", click **Create Credentials → OAuth client ID**, choose **Desktop app**, then **Download JSON** (this is your `client_secret.json`).
5. **Enter in App**: In Settings, browse to the downloaded `client_secret.json` and click **Connect YouTube Account**. A browser window opens — sign in with the channel's Google account and approve.
6. **Upload**: After each video is generated, click **⬆ Upload to YouTube** on the success screen. Title, description, and hashtags are pre-filled from the script.

> **Important**: While your Google Cloud project is unverified (the normal state for personal use), YouTube locks uploaded videos to **Private**. You can flip them to Public manually in YouTube Studio, or submit your project for verification to remove the limit. Quota note: uploads cost 1600 quota units each; the free daily quota (10,000 units) allows ~6 uploads per day.
