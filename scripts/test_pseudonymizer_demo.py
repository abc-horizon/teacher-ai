from app.privacy.pseudonymizer import pseudonymize

SAMPLE_TEXT = (
    "This assignment was completed by John Smith. If you have questions, "
    "email john.smith@example.com or call 0791-112-3456. The report "
    "discusses Fossil Fuels, Solar Energy, and Carbon Dioxide emissions, "
    "explaining how Coal and Natural Gas are extracted and used for "
    "electricity generation."
)


def main():
    result = pseudonymize(SAMPLE_TEXT)
    print("BEFORE:")
    print(SAMPLE_TEXT)
    print("\nAFTER:")
    print(result)


if __name__ == "__main__":
    main()
