"""
Script parsing helpers extracted from logic.ViralSafeBot.

These turn raw user text / raw LLM output into the normalized script dict the
rest of the pipeline expects:

    {"topic": str, "title": str, "scenes": [
        {"scene_id": int, "dialogue_text": str, "image_generation_prompt": str}, ...
    ]}

They accept an optional ``log`` callback so they stay free of instance state
and easy to unit-test; callers pass ``self.log``.
"""
import json


def _noop(_message):
    pass


def parse_manual_script(raw_text, log=_noop):
    """
    Parse manual text where each line is 'Caption | Visual Query'.
    Returns the script dict, or None if no usable lines were found.
    """
    lines = raw_text.split('\n')
    scenes = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        parts = line.split('|')
        text = parts[0].strip()

        if len(parts) > 1:
            visual = parts[1].strip()
        else:
            # Provide a fallback visual query if user didn't specify one
            visual = "dark background abstract"

        scenes.append({
            "scene_id": i + 1,
            "dialogue_text": text,
            "image_generation_prompt": visual
        })

    if not scenes:
        log("[!] Error: Manual script is empty.")
        return None

    return {
        "topic": "Manual Subject",
        "title": "Manual Video",
        "scenes": scenes
    }


def parse_llm_json(content, selected_topic, log=_noop):
    """
    Parse (possibly messy) LLM JSON output into the normalized script dict.
    Tolerates missing keys, ``captions`` instead of ``scenes``, and scenes
    given as bare strings. Returns None on unrecoverable JSON errors.
    """
    try:
        data = json.loads(content)

        if not isinstance(data, dict):
            log("[!] JSON is not a dictionary. Forcing empty dict.")
            data = {}

        if "topic" not in data:
            data["topic"] = selected_topic
        if "title" not in data:
            data["title"] = f"{selected_topic} - Viral Video"
        if "scenes" not in data:
            if "captions" in data:
                data["scenes"] = []
                for i, c in enumerate(data["captions"]):
                    data["scenes"].append({
                        "scene_id": i + 1,
                        "dialogue_text": c.get("text", str(c)),
                        "image_generation_prompt": c.get("visual_query", f"dark {selected_topic} abstract")
                    })
            else:
                data["scenes"] = []

        # Normalize scenes to dicts if they are strings (fallback)
        normalized_scenes = []
        for i, item in enumerate(data["scenes"]):
            if isinstance(item, str):
                normalized_scenes.append({
                    "scene_id": i + 1,
                    "dialogue_text": item,
                    "image_generation_prompt": f"dark {selected_topic} abstract"
                })
            else:
                item["scene_id"] = item.get("scene_id", i + 1)
                if "dialogue_text" not in item and "text" in item:
                    item["dialogue_text"] = item.pop("text")
                if "image_generation_prompt" not in item and "visual_query" in item:
                    item["image_generation_prompt"] = item.pop("visual_query")
                normalized_scenes.append(item)
        data["scenes"] = normalized_scenes
        return data
    except Exception as e:
        log(f"[!] JSON Parse Error: {e}")
        return None
