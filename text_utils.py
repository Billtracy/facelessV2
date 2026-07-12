"""
Pure text and formatting helpers extracted from logic.ViralSafeBot.

Everything in this module is free of class/instance state and side effects,
which makes it straightforward to unit-test in isolation.
"""
import re


def format_elapsed(seconds):
    """Format a duration in seconds as e.g. '1h 02m 03s' / '2m 03s' / '3s'."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def safe_filename(title):
    """Reduce an arbitrary title to a filesystem-safe base name."""
    return re.sub(r'[^\w\-_\. ]', '_', title)


# Sentence punctuation stripped from the EDGES of on-screen caption words for a
# clean viral look. Internal hyphens/apostrophes are preserved ("TWENTY-THREE,"
# -> "TWENTY-THREE", "DON'T." -> "DON'T"), and internal commas in numbers survive
# ("1,000" -> "1,000") because only the leading/trailing run is removed.
_CAPTION_EDGE_PUNCT = ',.!?;:—–-"“”‘’'


def strip_caption_punct(word):
    """Strip leading/trailing sentence punctuation from a single caption word."""
    return word.strip(_CAPTION_EDGE_PUNCT)


# Common filler words we don't want to turn into hashtags.
_HASHTAG_STOPWORDS = {
    "the", "a", "an", "of", "to", "is", "are", "am", "and", "or", "for", "in",
    "on", "at", "by", "with", "your", "you", "someone", "how", "why", "what",
    "that", "this", "it", "its", "be", "do", "make", "get",
}


def hashtags_from_topic(topic, extra=("shorts", "viral", "fyp"), max_topic_tags=4):
    """
    Build a de-duplicated list of hashtags (each prefixed with '#') from a topic
    string plus a few evergreen tags. Filler words and very short words drop out.
    """
    words = re.findall(r"[A-Za-z]+", (topic or "").lower())
    topic_tags = [w for w in words if w not in _HASHTAG_STOPWORDS and len(w) > 2][:max_topic_tags]

    seen = []
    for tag in list(topic_tags) + list(extra):
        if tag and tag not in seen:
            seen.append(tag)
    return ["#" + tag for tag in seen]


def spell_year(num):
    """
    Spell out a 4-digit year (1000-2099) the way espeak should read it.
    Returns the spelled string, or str(num) for anything out of range.
    """
    if not (1000 <= num <= 2099):
        return str(num)

    hundreds = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
                14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
                18: "eighteen", 19: "nineteen", 20: "twenty"}

    if num < 2000:
        century = num // 100
        remainder = num % 100
        if remainder == 0:
            return f"{hundreds.get(century, str(century))} hundred"
        tens_map = {0: "", 1: "", 2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
                    6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
        ones_map = {0: "", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
                    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
                    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
                    19: "nineteen"}
        century_word = hundreds.get(century, str(century))
        if remainder < 20:
            return f"{century_word} {ones_map.get(remainder, str(remainder))}"
        tens = tens_map.get(remainder // 10, "")
        ones = ones_map.get(remainder % 10, "")
        rem_word = f"{tens} {ones}".strip() if ones else tens
        return f"{century_word} {rem_word}"
    elif num == 2000:
        return "two thousand"
    elif num < 2010:
        ones_map = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                    6: "six", 7: "seven", 8: "eight", 9: "nine"}
        return f"two thousand and {ones_map.get(num - 2000, str(num - 2000))}"
    else:
        remainder = num - 2000
        tens_map = {1: "ten", 2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
                    6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
        ones_map = {0: "", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                    6: "six", 7: "seven", 8: "eight", 9: "nine",
                    10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
                    14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
                    18: "eighteen", 19: "nineteen"}
        if remainder < 20:
            return f"twenty {ones_map.get(remainder, str(remainder))}"
        tens = tens_map.get(remainder // 10, "")
        ones = ones_map.get(remainder % 10, "")
        rem_word = f"{tens} {ones}".strip() if ones else tens
        return f"twenty {rem_word}"


# Abbreviations expanded before handing text to espeak. Certain abbreviations
# (with embedded periods) otherwise cause espeak to split one input line into
# multiple output lines -> "number of lines in input and output must be equal".
_ESPEAK_ABBREVIATIONS = {
    "e.g.": "for example",
    "i.e.": "that is",
    "etc.": "etcetera",
    "vs.": "versus",
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "Dr.": "Doctor",
    "Jr.": "Junior",
    "Sr.": "Senior",
    "St.": "Saint",
    "Prof.": "Professor",
    "Gen.": "General",
    "Gov.": "Governor",
    "Sgt.": "Sergeant",
    "Corp.": "Corporation",
    "Inc.": "Incorporated",
    "Ltd.": "Limited",
    "approx.": "approximately",
    "dept.": "department",
    "est.": "established",
    "govt.": "government",
    "ft.": "feet",
    "lb.": "pounds",
    "oz.": "ounces",
}


def sanitize_for_espeak(text):
    """
    Aggressively sanitize text to prevent espeak from producing mismatched
    input/output line counts (root cause of the 'number of lines in input and
    output must be equal' error).

    espeak can internally split a single input line into multiple output lines
    when it encounters certain characters like parentheses, brackets, dashes,
    slashes, and abbreviations.
    """
    # 1. Remove all newlines / carriage returns
    text = text.replace("\n", " ").replace("\r", " ")

    # 2. Expand common abbreviations that confuse espeak
    for abbr, expansion in _ESPEAK_ABBREVIATIONS.items():
        text = text.replace(abbr, expansion)
        text = text.replace(abbr.upper(), expansion)

    # 3. Replace characters that cause espeak to split lines
    #    Parentheses, brackets, braces, slashes -> commas or spaces
    text = re.sub(r'[(\[{]', ', ', text)
    text = re.sub(r'[)\]}]', ' ', text)
    text = re.sub(r'[/\\]', ' ', text)

    # 3b. Fix mid-word punctuation corruption (e.g. "T!DECISION!'S" -> "TDECISIONS")
    #     Remove exclamation marks and other symbols that appear INSIDE words
    text = re.sub(r'(?<=[a-zA-Z])[!?]+(?=[a-zA-Z])', '', text)

    # 4. Replace all dash variants (em-dash, en-dash, hyphens used as separators)
    #    Keep single hyphens in compound words (well-known) but remove separating dashes
    text = re.sub(r'[—–]', ', ', text)   # em-dash and en-dash -> comma
    text = re.sub(r'\s*-{2,}\s*', ', ', text)       # multiple hyphens -> comma
    text = re.sub(r'\s+-\s+', ', ', text)           # spaced single dash (separator) -> comma

    # 5. Remove problematic quotes and special punctuation
    #    straight/curly double + curly single + straight single + backtick
    text = re.sub(r'["“”‘’\'`]', '', text)

    # 6. Replace colons and semicolons
    text = text.replace(":", ",").replace(";", ",")

    # 7. Replace ampersand
    text = text.replace("&", "and")

    # 8. Remove hash, asterisk, underscore, tilde, pipe, caret
    text = re.sub(r'[#*_~|^@<>{}]', ' ', text)

    # 9. Spell out $ and % symbols
    text = text.replace("%", " percent")
    text = text.replace("$", " dollars ")

    # 10. Spell out standalone 4-digit numbers (years) espeak might mishandle
    text = re.sub(r'\b\d{4}\b', lambda m: spell_year(int(m.group(0))), text)

    # 11. Replace number ranges with "to" (e.g. "5-7" -> "5 to 7")
    text = re.sub(r'(\d+)\s*-\s*(\d+)', r'\1 to \2', text)

    # 12. Collapse multiple spaces and commas
    text = re.sub(r',\s*,+', ',', text)      # multiple commas
    text = re.sub(r'\s+', ' ', text)          # multiple spaces
    text = re.sub(r'\s*,\s*', ', ', text)     # normalize comma spacing

    # 13. Remove leading/trailing punctuation artifacts
    text = text.strip(' ,;')

    return text


def sanitize_for_display(text):
    """
    Sanitize dialogue_text for visual display on screen. Removes corrupted
    punctuation, brackets, and other artifacts the AI may have injected.
    """
    # Remove brackets and parentheses
    text = re.sub(r'[\[\](){}]', '', text)

    # Remove exclamation/question marks that appear INSIDE words (e.g. T!DECISION!'S)
    text = re.sub(r'(?<=[a-zA-Z])[!?]+(?=[a-zA-Z])', '', text)

    # Remove stray asterisks, underscores, pipes, carets
    text = re.sub(r'[*_|^~#]', '', text)

    # Normalize quotes - remove fancy quotes and stray single quotes not part of contractions
    text = re.sub(r'["“”]', '', text)
    # Keep apostrophes in contractions (don't, it's) but remove stray ones
    text = re.sub(r"(?<![a-zA-Z])'|'(?![a-zA-Z])", '', text)

    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()

    return text
