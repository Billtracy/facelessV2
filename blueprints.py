"""
Niche "blueprints" that steer the LLM script generation prompt.

Extracted from logic.ViralSafeBot so the catalog is plain data that can be
edited (or eventually loaded from JSON) without touching generation logic.
"""

BLUEPRINTS = {
    "Reddit Stories": {
        "role": 'an engaging voice actor reading a viral, top-tier Reddit "Am I The A**hole", Confession, or Creepypasta.',
        "task": "Write a gripping, 1st-person story.",
        "hook": "Start with an insane, dramatic statement or creepy premise.",
        "cta": "End on a cliffhanger or ask the viewers 'Am I the jerk?'"
    },
    "Motivation & Inspiration": {
        "role": "a hard-hitting motivational speaker and success analyst.",
        "task": "Write an intense script about discipline or a breakdown of a famous success story.",
        "hook": "Start with a hard truth (e.g. 'You are wasting your life...')",
        "cta": "Demand they save the video for when they want to quit."
    },
    "Historical Facts": {
        "role": "a viral history channel exposing hidden truths.",
        "task": "Share dark, mysterious, or mind-blowing historical facts. STRICT RULE: Use ONLY verified facts. No myths.",
        "hook": "Start with: 'Here are historical facts they didn't teach you in school...'",
        "cta": "Tell them to subscribe for more forbidden history."
    },
    "Historical Figures": {
        "role": "a fast-paced biographer of the bizarre.",
        "task": "Discuss the dark secrets or mind-blowing facts about a specific historical figure.",
        "hook": "Start with a crazy, lesser-known fact about the person.",
        "cta": "Ask: 'Who should we cover next? Comment below.'"
    },
    "Mythology & Ancient Lore": {
        "role": "a cinematic storyteller specializing in Mythology.",
        "task": "Share an epic, terrifying mythological tale or creature from world lore.",
        "hook": "An epic, mysterious hook about the myth's power or origin.",
        "cta": "Tell them to subscribe for more mythological lore."
    },
    "Stoicism & Daily Philosophy": {
        "role": "a calm, authoritative guide to Stoicism.",
        "task": "Share ancient philosophical wisdom applied to modern struggles.",
        "hook": "A profound quote or a highly relatable modern struggle.",
        "cta": "Tell them to save this video for when they need clarity."
    },
    "\"What If?\" & Cosmic Sci-Fi Scenarios": {
        "role": "a sci-fi narrator exploring mind-bending paradoxes.",
        "task": "Describe a terrifying or fascinating cosmic event.",
        "hook": "Ask: 'What would happen if...' (e.g., you fell into a black hole).",
        "cta": "Ask: 'Would you survive this? Comment below.'"
    },
    "Visual Lore & Design Mysteries": {
        "role": "an expert on liminal spaces and internet aesthetics.",
        "task": "Explain a mysterious visual subculture or eerie design concept.",
        "hook": "Ask: 'Why does this image make you feel nostalgia and dread?'",
        "cta": "Ask: 'Have you been here in your dreams? Subscribe.'"
    },
    "Law": {
        "role": "an expert legal commentator.",
        "task": "Tell the story of a crazy lawsuit, a weird law, or a medical malpractice case.",
        "hook": "Start with: 'Is this completely illegal?' or 'The most insane lawsuit.'",
        "cta": "Ask: 'Do you agree with the judge? Let me know.'"
    },
    "Personal Finance & Wealth": {
        "role": "a no-nonsense wealth expert.",
        "task": "Share financial hacks, investing rules, or mistakes keeping people broke.",
        "hook": "Start with: 'The system is designed to keep you broke. Here is how to escape.'",
        "cta": "Tell them to save this and subscribe for financial freedom."
    },
    "Top 10s & Listicles": {
        "role": "a fast-paced master of ranking fascinating things.",
        "task": "Rank a list of incredibly interesting or scary things.",
        "hook": "Start with: 'Here are the top most insane [topic] that will blow your mind.'",
        "cta": "Ask: 'Which one was the craziest? Subscribe.'"
    },
    "Hollywood Gossips and Lores": {
        "role": "a conspiratorial Hollywood pop culture historian.",
        "task": "Reveal a shocking piece of Hollywood lore or a crazy celebrity feud.",
        "hook": "Start with: 'The craziest Hollywood secret they tried to bury...'",
        "cta": "Ask: 'Do you believe it? Let me know.'"
    },
    "Dark Psychology": {
        "role": "a dark psychology and human behavior expert.",
        "task": "Share a powerful dark psychology trick, manipulation tactic (for awareness), or a secret about human behavior.",
        "hook": "Start with a provocative statement like 'If you want to control any conversation...' or 'The darkest trick to make someone...'",
        "cta": "Tell them to use this power wisely and subscribe for more psychological secrets."
    },
    "Historical Psychology": {
        "role": "a psychological profiler and historical analyst.",
        "task": "Provide a deep psychological breakdown of a famous historical figure's motivations or the hidden psychological impact of a major historical event.",
        "hook": "Start with a question like 'Why did [Figure] really do it?' or 'What if I told you the true cause of [Event] was a simple human psychological flaw?'",
        "cta": "Ask: 'Which historical mystery should we analyze next? Subscribe for more deep dives.'"
    },
    "True Crime Stories": {
        "role": "a meticulous true crime documentarian.",
        "task": "Write an intense, suspenseful true crime script about a fascinating unsolved mystery or infamous case.",
        "hook": "Start with a chilling fact or a terrifying realization about the case.",
        "cta": "Ask the viewers: 'Who do you think did it? Let me know.'"
    },
}


def get_blueprint(blueprint_name, selected_topic):
    """
    Return the blueprint dict for ``blueprint_name``, or a generic fallback
    built around ``selected_topic`` when the name isn't in the catalog.
    """
    return BLUEPRINTS.get(blueprint_name, {
        "role": "a viral scriptwriter for a popular YouTube channel.",
        "task": f"Write an engaging script about {selected_topic}.",
        "hook": f"A punchy, engaging question relating to {selected_topic}.",
        "cta": "A strong call to action to subscribe or comment."
    })
