from app.privacy.pseudonymizer import pseudonymize


def test_person_name_replaced_with_name_tag():
    result = pseudonymize("The submission was written by John Smith.")
    assert "[NAME]" in result
    assert "John Smith" not in result


def test_email_replaced_with_email_tag():
    result = pseudonymize("Contact john.smith@example.com for details.")
    assert result == "Contact [EMAIL] for details."
    assert "john.smith@example.com" not in result


def test_phone_number_replaced_with_phone_tag():
    result = pseudonymize("Call the student at 0791-112-3456 today.")
    assert "[PHONE]" in result
    assert "0791-112-3456" not in result


def test_scientific_terms_are_not_pseudonymized():
    text = (
        "Fossil Fuels are a major energy source. Solar Energy and Carbon "
        "Dioxide levels are discussed in this unit."
    )
    assert pseudonymize(text) == text


def test_mixed_text_replaces_name_and_email_but_keeps_scientific_terms():
    text = (
        "Sarah Ahmed Khalil (sarah.khalil@example.com) wrote about Fossil "
        "Fuels and Solar Energy in her assignment."
    )
    result = pseudonymize(text)
    assert "Sarah Ahmed Khalil" not in result
    assert "sarah.khalil@example.com" not in result
    assert "[NAME]" in result
    assert "[EMAIL]" in result
    assert "Fossil Fuels" in result
    assert "Solar Energy" in result


def test_pseudonymize_is_idempotent():
    text = "John Smith emailed john.smith@example.com about Fossil Fuels."
    once = pseudonymize(text)
    twice = pseudonymize(once)
    assert once == twice
