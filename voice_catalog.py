"""
Friendly display names for the Kokoro narrator voices.

The engine keeps using raw Kokoro IDs (config key "last_voice_kokoro"); the
GUI shows these descriptive names and maps back on save. The voice ComboBox
stays editable, so unknown text passes through unchanged as a raw voice ID.
"""

# (kokoro_id, display name) - list order = dropdown order
KOKORO_VOICES = [
    ("af",          "Heart — Warm All-Rounder (US Female)"),
    ("af_bella",    "Bella — Energetic & Upbeat (US Female)"),
    ("af_nicole",   "Nicole — Soft ASMR Whisper (US Female)"),
    ("af_sarah",    "Sarah — Calm & Clear Explainer (US Female)"),
    ("af_sky",      "Sky — Youthful & Friendly (US Female)"),
    ("am_adam",     "Adam — Deep Movie-Trailer (US Male)"),
    ("am_michael",  "Michael — Smooth Documentary (US Male)"),
    ("bf_emma",     "Emma — Elegant Storyteller (UK Female)"),
    ("bf_isabella", "Isabella — Warm & Soothing (UK Female)"),
    ("bm_george",   "George — Classic History Narrator (UK Male)"),
    ("bm_lewis",    "Lewis — Bold & Dramatic (UK Male)"),
]

_DISPLAY_TO_ID = {display: vid for vid, display in KOKORO_VOICES}
_ID_TO_DISPLAY = {vid: display for vid, display in KOKORO_VOICES}


def display_names():
    return [display for _, display in KOKORO_VOICES]


def to_voice_id(text):
    """Map a display name back to its Kokoro ID; unknown text passes through."""
    return _DISPLAY_TO_ID.get(text, text)


def to_display(voice_id):
    """Map a Kokoro ID to its display name; unknown IDs pass through."""
    return _ID_TO_DISPLAY.get(voice_id, voice_id)
