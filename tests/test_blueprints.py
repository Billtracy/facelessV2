"""Tests for the blueprint catalog and lookup in blueprints."""
import blueprints


REQUIRED_KEYS = {"role", "task", "hook", "cta"}


def test_every_blueprint_has_required_keys():
    for name, bp in blueprints.BLUEPRINTS.items():
        assert REQUIRED_KEYS.issubset(bp), f"{name} missing keys: {REQUIRED_KEYS - set(bp)}"
        assert all(isinstance(bp[k], str) and bp[k].strip() for k in REQUIRED_KEYS)


def test_get_blueprint_known_name():
    bp = blueprints.get_blueprint("True Crime Stories", "ignored")
    assert "true crime documentarian" in bp["role"]


def test_get_blueprint_unknown_name_falls_back_to_generic():
    bp = blueprints.get_blueprint("Totally Made Up Niche", "Black Holes")
    assert REQUIRED_KEYS.issubset(bp)
    # generic fallback weaves the selected topic into task + hook
    assert "Black Holes" in bp["task"]
    assert "Black Holes" in bp["hook"]


def test_get_blueprint_does_not_mutate_catalog():
    before = dict(blueprints.BLUEPRINTS["Law"])
    blueprints.get_blueprint("Law", "x")
    assert blueprints.BLUEPRINTS["Law"] == before
