from app.grading.prompt_builder import MAX_SUBMISSION_TEXT_LENGTH, build_prompt
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
    prompt, _ = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert "مساعد لمدرّس BTEC" in prompt


def test_prompt_contains_every_criterion_descriptor_verbatim():
    prompt, _ = build_prompt(CRITERIA, SUBMISSION_TEXT)
    for criterion in CRITERIA:
        assert criterion.descriptor in prompt
        assert criterion.code in prompt


def test_prompt_contains_submission_text_verbatim():
    prompt, _ = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert SUBMISSION_TEXT in prompt
    assert "Student Submission:" in prompt


def test_prompt_contains_rag_disabled_note():
    prompt, _ = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert "RAG" in prompt
    assert "not enabled yet" in prompt


def test_prompt_contains_command_verb_definitions():
    prompt, _ = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert "Command-Verb Definitions:" in prompt
    assert "Evaluate:" in prompt
    assert "PEARSON_OFFICIAL" in prompt
    assert "sole basis for achieved/not achieved" in prompt


def test_prompt_pseudonymizes_person_names():
    text_with_name = "John Smith explained the process clearly in his submission."
    prompt, _ = build_prompt(CRITERIA, text_with_name)
    assert "John Smith" not in prompt
    assert "[NAME]" in prompt


def test_prompt_does_not_truncate_short_submission_text():
    prompt, was_truncated = build_prompt(CRITERIA, SUBMISSION_TEXT)
    assert was_truncated is False
    assert "TEXT TRUNCATED" not in prompt


def test_prompt_truncates_very_long_submission_text():
    long_text = "a" * (MAX_SUBMISSION_TEXT_LENGTH + 10_000)
    prompt, was_truncated = build_prompt(CRITERIA, long_text)
    assert was_truncated is True
    assert "TEXT TRUNCATED" in prompt
    assert f"original length: {len(long_text)} characters" in prompt
