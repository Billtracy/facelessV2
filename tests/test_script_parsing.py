"""Tests for manual/LLM script parsing in script_parsing."""
import json

import script_parsing as sp


# --- parse_manual_script ----------------------------------------------------

def test_manual_basic_caption_and_visual():
    result = sp.parse_manual_script("Hello world | space background")
    assert result["topic"] == "Manual Subject"
    assert result["title"] == "Manual Video"
    assert len(result["scenes"]) == 1
    scene = result["scenes"][0]
    assert scene["scene_id"] == 1
    assert scene["dialogue_text"] == "Hello world"
    assert scene["image_generation_prompt"] == "space background"


def test_manual_missing_visual_gets_fallback():
    result = sp.parse_manual_script("Just a caption")
    assert result["scenes"][0]["image_generation_prompt"] == "dark background abstract"


def test_manual_skips_blank_lines_and_numbers_scenes():
    result = sp.parse_manual_script("First | a\n\n  \nSecond | b")
    ids = [s["scene_id"] for s in result["scenes"]]
    texts = [s["dialogue_text"] for s in result["scenes"]]
    assert texts == ["First", "Second"]
    # scene_id follows original line index (blank lines advance the counter)
    assert ids[0] == 1
    assert len(result["scenes"]) == 2


def test_manual_empty_returns_none():
    assert sp.parse_manual_script("") is None
    assert sp.parse_manual_script("   \n  \n") is None


def test_manual_log_called_on_empty():
    calls = []
    sp.parse_manual_script("", log=calls.append)
    assert any("empty" in c.lower() for c in calls)


# --- parse_llm_json ---------------------------------------------------------

def test_llm_fills_missing_topic_and_title():
    data = sp.parse_llm_json(json.dumps({"scenes": []}), "Space Facts")
    assert data["topic"] == "Space Facts"
    assert data["title"] == "Space Facts - Viral Video"


def test_llm_string_scenes_are_normalized():
    data = sp.parse_llm_json(json.dumps({"scenes": ["one", "two"]}), "T")
    assert data["scenes"][0] == {
        "scene_id": 1, "dialogue_text": "one", "image_generation_prompt": "dark T abstract"
    }
    assert data["scenes"][1]["scene_id"] == 2


def test_llm_dict_scenes_key_aliases():
    raw = json.dumps({"scenes": [{"text": "hi", "visual_query": "ocean"}]})
    scene = sp.parse_llm_json(raw, "T")["scenes"][0]
    assert scene["dialogue_text"] == "hi"
    assert scene["image_generation_prompt"] == "ocean"
    assert scene["scene_id"] == 1


def test_llm_captions_key_is_converted_to_scenes():
    raw = json.dumps({"captions": [{"text": "c1", "visual_query": "v1"}, {"text": "c2"}]})
    scenes = sp.parse_llm_json(raw, "T")["scenes"]
    assert len(scenes) == 2
    assert scenes[0]["dialogue_text"] == "c1"
    assert scenes[0]["image_generation_prompt"] == "v1"
    assert scenes[1]["image_generation_prompt"] == "dark T abstract"


def test_llm_non_dict_json_becomes_empty_scaffold():
    data = sp.parse_llm_json(json.dumps([1, 2, 3]), "T")
    assert data["scenes"] == []
    assert data["topic"] == "T"


def test_llm_invalid_json_returns_none_and_logs():
    calls = []
    assert sp.parse_llm_json("not json at all", "T", log=calls.append) is None
    assert any("JSON Parse Error" in c for c in calls)


def test_llm_existing_scene_id_is_preserved():
    raw = json.dumps({"scenes": [{"dialogue_text": "x", "scene_id": 99}]})
    assert sp.parse_llm_json(raw, "T")["scenes"][0]["scene_id"] == 99
