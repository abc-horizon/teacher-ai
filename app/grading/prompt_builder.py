import json
from pathlib import Path

from app.models import Criterion
from app.privacy.pseudonymizer import pseudonymize

SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "prompts" / "system_v1.md"
)
COMMAND_VERBS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "sample_data"
    / "command-verbs.json"
)

RAG_NOTE = (
    "Note: the RAG layer (supporting excerpts from assignment guidance) is "
    "not enabled yet in this version (v1). It will be added later in M3."
)

COMMAND_VERB_GUIDANCE_RULES = (
    "Command-Verb Guidance Rules:\n"
    "- Apply the supplied command-verb definitions below when interpreting "
    "the command verb used in each criterion (e.g. what \"Evaluate\" or "
    "\"Explain\" actually requires).\n"
    "- These definitions explain the required type of thinking only — they "
    "do not replace, rewrite, expand, or add requirements to the criterion "
    "text itself. The exact criterion text remains the sole basis for "
    "achieved/not achieved.\n"
    "- Definitions marked PEARSON_OFFICIAL come from Pearson's own glossary; "
    "definitions marked OPERATIONAL are fixed supplementary interpretations "
    "and must not be presented as direct Pearson quotations."
)


def _load_command_verbs_block() -> str:
    data = json.loads(COMMAND_VERBS_PATH.read_text(encoding="utf-8"))
    lines = [
        f"- {verb}: {info['definition']} ({info['definition_type']})"
        for verb, info in data["command_verbs"].items()
    ]
    return (
        "Command-Verb Definitions:\n"
        + "\n".join(lines)
        + "\n\n"
        + COMMAND_VERB_GUIDANCE_RULES
    )

# Safety net against a pathologically large upload, not a realistic cap:
# the current model's context window is ~1M tokens, so this is roughly 6x
# the largest real submission seen so far (~88K chars), never expected to
# trigger on normal student work.
MAX_SUBMISSION_TEXT_LENGTH = 500_000


def prepare_submission_text(submission_text: str) -> tuple[str, bool]:
    """Pseudonymizes then length-caps submission text for the model.

    Returns (prepared_text, was_truncated). Callers that need to verify
    evidence_quote against what the model actually saw must use this same
    prepared text, not the raw original.
    """
    text = pseudonymize(submission_text)
    if len(text) <= MAX_SUBMISSION_TEXT_LENGTH:
        return text, False

    original_length = len(text)
    truncated = text[:MAX_SUBMISSION_TEXT_LENGTH]
    notice = f"\n\n[TEXT TRUNCATED — original length: {original_length} characters]"
    return truncated + notice, True


def build_prompt(criteria: list[Criterion], submission_text: str) -> tuple[str, bool]:
    """Returns (prompt, was_truncated)."""
    system_instructions = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    criteria_lines = [
        f"{index}. {criterion.code}: {criterion.descriptor}"
        for index, criterion in enumerate(criteria, start=1)
    ]
    criteria_block = "Assessment Criteria:\n" + "\n".join(criteria_lines)
    command_verbs_block = _load_command_verbs_block()

    prepared_text, was_truncated = prepare_submission_text(submission_text)

    prompt = "\n\n---\n\n".join(
        [
            system_instructions,
            criteria_block,
            command_verbs_block,
            RAG_NOTE,
            f"Student Submission:\n{prepared_text}",
        ]
    )
    return prompt, was_truncated
