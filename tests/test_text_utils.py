"""Tests for the pure text/formatting helpers in text_utils."""
import pytest

import text_utils as t


# --- format_elapsed ---------------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (0, "0s"),
    (3, "3s"),
    (59, "59s"),
    (60, "1m 00s"),
    (75, "1m 15s"),
    (599, "9m 59s"),
    (3600, "1h 00m 00s"),
    (3723, "1h 02m 03s"),
    (3.9, "3s"),        # truncates, not rounds
    (7261, "2h 01m 01s"),
])
def test_format_elapsed(seconds, expected):
    assert t.format_elapsed(seconds) == expected


# --- safe_filename ----------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Simple Title", "Simple Title"),
    ("A/B", "A_B"),
    ("Wow: A/B*C?", "Wow_ A_B_C_"),
    ("keeps-dash_and.dot", "keeps-dash_and.dot"),
    ('quote"here', "quote_here"),
])
def test_safe_filename(title, expected):
    assert t.safe_filename(title) == expected


# --- spell_year -------------------------------------------------------------

@pytest.mark.parametrize("num,expected", [
    (1000, "ten hundred"),
    (1776, "seventeen seventy six"),
    (1900, "nineteen hundred"),
    (1905, "nineteen five"),
    (1999, "nineteen ninety nine"),
    (2000, "two thousand"),
    (2005, "two thousand and five"),
    (2009, "two thousand and nine"),
    (2010, "twenty ten"),
    (2024, "twenty twenty four"),
    (2099, "twenty ninety nine"),
])
def test_spell_year_in_range(num, expected):
    assert t.spell_year(num) == expected


@pytest.mark.parametrize("num", [0, 42, 500, 999, 2100, 3000])
def test_spell_year_out_of_range_is_passthrough(num):
    assert t.spell_year(num) == str(num)


# --- sanitize_for_espeak ----------------------------------------------------

def test_espeak_expands_abbreviations():
    out = t.sanitize_for_espeak("e.g. Dr. Smith vs. Mr. Jones")
    assert "for example" in out
    assert "Doctor" in out
    assert "versus" in out
    assert "Mister" in out
    # no leftover abbreviation periods that would split espeak lines
    assert "Dr." not in out


def test_espeak_spells_years_and_ranges():
    out = t.sanitize_for_espeak("Back in 1999 prices rose 5-7 points")
    assert "nineteen ninety nine" in out
    assert "5 to 7" in out


def test_espeak_symbols_replaced():
    out = t.sanitize_for_espeak("Save 50% or $100 & win")
    assert "percent" in out
    assert "dollars" in out
    assert "and" in out
    assert "%" not in out and "$" not in out and "&" not in out


def test_espeak_removes_newlines_and_quotes():
    out = t.sanitize_for_espeak('line one\nline two “quoted”')
    assert "\n" not in out
    assert "“" not in out and "”" not in out


def test_espeak_strips_trailing_punctuation_artifacts():
    assert not t.sanitize_for_espeak("  , hello ; ").endswith((",", ";", " "))


def test_espeak_returns_str_and_is_idempotent_on_plain_text():
    plain = "just some clean words"
    assert t.sanitize_for_espeak(plain) == plain


# --- sanitize_for_display ---------------------------------------------------

def test_display_removes_brackets_and_stray_symbols():
    out = t.sanitize_for_display("Hello [world] (foo) *bar* _baz_")
    assert "[" not in out and "]" not in out
    assert "(" not in out and ")" not in out
    assert "*" not in out and "_" not in out


def test_display_keeps_contraction_apostrophes():
    out = t.sanitize_for_display("don't stop it's fine")
    assert "don't" in out
    assert "it's" in out


def test_display_removes_midword_bang():
    assert t.sanitize_for_display("T!DECISION") == "TDECISION"


def test_display_collapses_whitespace():
    assert t.sanitize_for_display("a    b\t c") == "a b c"


# --- hashtags_from_topic ----------------------------------------------------

def test_hashtags_basic_topic_plus_evergreen():
    tags = t.hashtags_from_topic("Signs Someone is Lying")
    assert tags[0] == "#signs"
    assert "#lying" in tags
    # evergreen defaults appended
    assert "#shorts" in tags and "#viral" in tags and "#fyp" in tags
    # stopwords filtered out
    assert "#someone" not in tags and "#is" not in tags


def test_hashtags_all_prefixed_and_deduped():
    tags = t.hashtags_from_topic("Viral viral VIRAL money")
    assert all(x.startswith("#") for x in tags)
    assert len(tags) == len(set(tags))


def test_hashtags_respects_max_topic_tags():
    tags = t.hashtags_from_topic("alpha beta gamma delta epsilon zeta", extra=(), max_topic_tags=3)
    assert tags == ["#alpha", "#beta", "#gamma"]


def test_hashtags_empty_topic_returns_only_extra():
    assert t.hashtags_from_topic("", extra=("shorts",)) == ["#shorts"]
    assert t.hashtags_from_topic(None) == ["#shorts", "#viral", "#fyp"]


# --- strip_caption_punct ----------------------------------------------------

@pytest.mark.parametrize("word,expected", [
    ("TWENTY-THREE,", "TWENTY-THREE"),   # trailing comma dropped, internal hyphen kept
    ("ARCHITECTURE,", "ARCHITECTURE"),
    ("HELLO.", "HELLO"),
    ("REALLY?!", "REALLY"),
    ("DON'T", "DON'T"),                  # internal apostrophe preserved
    ("1,000", "1,000"),                  # internal comma preserved
    ("WELL-KNOWN", "WELL-KNOWN"),        # internal hyphen preserved
    ("PLAIN", "PLAIN"),                  # unchanged
    ("“QUOTED”", "QUOTED"),              # edge curly quotes removed
    ("...", ""),                          # all-punctuation collapses to empty
])
def test_strip_caption_punct(word, expected):
    assert t.strip_caption_punct(word) == expected
