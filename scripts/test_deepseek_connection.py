from app.grading.llm_client import evaluate

PROMPT = (
    "Reply with a JSON object only, no other text, in exactly this shape: "
    '{"status": "connected", "message": "<a short greeting>"}'
)


def main():
    result, usage = evaluate(PROMPT)
    print(result)
    print(f"usage: {usage}")


if __name__ == "__main__":
    main()
