import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url="https://api.deepseek.com")


def evaluate(prompt: str) -> tuple[dict, dict]:
    """Returns (parsed_json_content, usage) where usage is
    {"prompt_tokens", "completion_tokens", "total_tokens"} (values may be
    None if the API did not return usage data)."""
    model = os.getenv("LLM_MODEL") or "deepseek-v4-flash"
    response = _client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"DeepSeek response was not valid JSON: {content!r}"
        ) from exc

    usage_obj = response.usage
    usage = {
        "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
        "completion_tokens": getattr(usage_obj, "completion_tokens", None),
        "total_tokens": getattr(usage_obj, "total_tokens", None),
    }
    return parsed, usage
