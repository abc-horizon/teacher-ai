from app.grading.prompt_builder import build_prompt
from app.models import Criterion

CRITERIA = [
    Criterion(id=1, snapshot_id=1, code="P1", descriptor="Describe the sources and uses of oil, coal and natural gas."),
    Criterion(id=2, snapshot_id=1, code="P2", descriptor="Describe how the use of fossil fuels impacts human health and the environment."),
    Criterion(id=3, snapshot_id=1, code="M1", descriptor="Explain how the use of fossil fuels affects human health and the environment."),
]

SUBMISSION_TEXT = (
    "Coal, oil and natural gas are fossil fuels. Coal is extracted by mining. "
    "Oil and gas are extracted by drilling."
)


def test_prompt_contains_full_system_instructions():
    prompt = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert "مساعد لمدرّس BTEC" in prompt


def test_prompt_contains_every_criterion_descriptor_verbatim():
    prompt = build_prompt(CRITERIA, SUBMISSION_TEXT)
    for criterion in CRITERIA:
        assert criterion.descriptor in prompt
        assert criterion.code in prompt


def test_prompt_contains_submission_text_verbatim():
    prompt = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert SUBMISSION_TEXT in prompt
    assert "Student Submission:" in prompt


def test_prompt_contains_rag_disabled_note():
    prompt = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert "RAG" in prompt
    assert "not enabled yet" in prompt
