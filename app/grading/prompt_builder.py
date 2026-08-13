from pathlib import Path

from app.models import Criterion

SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "prompts" / "system_v1.md"
)

RAG_NOTE = (
    "Note: the RAG layer (supporting excerpts from assignment guidance) is "
    "not enabled yet in this version (v1). It will be added later in M3."
)


def build_prompt(criteria: list[Criterion], submission_text: str) -> str:
    system_instructions = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    criteria_lines = [
        f"{index}. {criterion.code}: {criterion.descriptor}"
        for index, criterion in enumerate(criteria, start=1)
    ]
    criteria_block = "Assessment Criteria:\n" + "\n".join(criteria_lines)

    return "\n\n---\n\n".join(
        [
            system_instructions,
            criteria_block,
            RAG_NOTE,
            f"Student Submission:\n{submission_text}",
        ]
    )
