from app.grading.grade_calculator import calculate_suggested_grade


def make_results(**achieved_by_code):
    return [
        {"criterion_code": code, "achieved": achieved}
        for code, achieved in achieved_by_code.items()
    ]


def test_all_criteria_achieved_gives_distinction():
    results = make_results(P1=True, P2=True, M1=True, M2=True, D1=True, D2=True)
    assert calculate_suggested_grade(results) == "DISTINCTION"


def test_pass_and_merit_only_gives_merit():
    results = make_results(P1=True, P2=True, M1=True, M2=True, D1=False, D2=False)
    assert calculate_suggested_grade(results) == "MERIT"


def test_pass_only_gives_pass():
    results = make_results(P1=True, P2=True, M1=False, M2=False, D1=False, D2=False)
    assert calculate_suggested_grade(results) == "PASS"


def test_one_missing_pass_gives_not_yet_achieved_even_if_merit_and_distinction_met():
    results = make_results(P1=True, P2=False, M1=True, M2=True, D1=True, D2=True)
    assert calculate_suggested_grade(results) == "NOT_YET_ACHIEVED"
