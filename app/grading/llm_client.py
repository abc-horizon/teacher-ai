import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url="https://api.deepseek.com")


def evaluate(prompt: str) -> dict:
    response = _client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"DeepSeek response was not valid JSON: {content!r}"
        ) from exc
