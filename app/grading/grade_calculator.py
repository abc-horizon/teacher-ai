LEVEL_ORDER = ["P", "M", "D"]


def calculate_suggested_grade(results: list[dict]) -> str:
    """Derives a BTEC-style suggested grade from criterion results.

    `results` is a list of {"criterion_code": str, "achieved": bool}.
    The grade is computed purely from whichever P/M/D codes are present,
    so it adapts to units with different numbers of criteria.
    """
    achieved_by_level = {level: [] for level in LEVEL_ORDER}
    for result in results:
        level = result["criterion_code"][0].upper()
        if level in achieved_by_level:
            achieved_by_level[level].append(result["achieved"])

    def level_fully_achieved(level: str) -> bool:
        items = achieved_by_level[level]
        return len(items) > 0 and all(items)

    if not level_fully_achieved("P"):
        return "NOT_YET_ACHIEVED"
    if level_fully_achieved("M") and level_fully_achieved("D"):
        return "DISTINCTION"
    if level_fully_achieved("M"):
        return "MERIT"
    return "PASS"
