# Initial pattern-based implementation (T3.4 draft). Full coverage requires
# more sophisticated NER in a later iteration.

import re

# Words drawn from this unit's own assessment criteria, plus command verbs
# and a couple of institutional terms. A run of 2+ consecutive capitalized
# words is only treated as a possible person name if NONE of its words are
# in this set — this keeps phrases like "Fossil Fuels" or "Solar Energy"
# intact instead of being pseudonymized as a name, without needing full NER.
DOMAIN_EXCEPTION_WORDS = {
    "describe", "explain", "analyse", "evaluate", "compare",
    "sources", "uses", "using", "used", "use",
    "oil", "coal", "natural", "gas", "fossil", "fuel", "fuels",
    "human", "health", "environment", "environmental",
    "technologies", "renewable", "energy", "power",
    "advantages", "disadvantages", "nuclear",
    "social", "financial", "efficiency", "different",
    "biofuels", "impact", "impacts", "factors", "methods",
    "benefits", "detrimental", "effects", "affect", "affects",
    "solar", "wind", "hydroelectric", "biomass", "geothermal",
    "increasing", "increased", "generate", "generation",
    "electricity", "turbines", "mining", "drilling",
    "sustainable", "carbon", "dioxide", "panels", "emissions",
    "pearson", "btec",
}

NAME_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){1,3}\b")

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Candidate digit runs (7-15 actual digits, per spec) allowing an optional
# leading "+" and internal spaces/hyphens; the digit-count check happens in
# _replace_phones so short numbers (years, unit codes, ...) are left alone.
PHONE_CANDIDATE_PATTERN = re.compile(r"\+?\d[\d\-\s]{5,18}\d")


def _looks_like_name(match: "re.Match[str]") -> bool:
    words = match.group(0).split()
    return not any(word.lower() in DOMAIN_EXCEPTION_WORDS for word in words)


def _replace_names(text: str) -> str:
    return NAME_PATTERN.sub(
        lambda m: "[NAME]" if _looks_like_name(m) else m.group(0), text
    )


def _replace_phones(text: str) -> str:
    def replace(match: "re.Match[str]") -> str:
        digit_count = len(re.sub(r"\D", "", match.group(0)))
        return "[PHONE]" if 7 <= digit_count <= 15 else match.group(0)

    return PHONE_CANDIDATE_PATTERN.sub(replace, text)


def pseudonymize(text: str) -> str:
    text = EMAIL_PATTERN.sub("[EMAIL]", text)
    text = _replace_phones(text)
    text = _replace_names(text)
    return text
