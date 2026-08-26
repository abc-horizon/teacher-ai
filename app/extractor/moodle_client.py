"""Central Moodle Web Services connection helper.

Every call is a plain GET against {MOODLE_URL}/webservice/rest/server.php.
Error handling never surfaces str(exc) from `requests` (it embeds the full
request URL, wstoken included) and never echoes the token in any message.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL = os.getenv("MOODLE_URL", "").rstrip("/")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")


class MoodleCallError(Exception):
    pass


def call_moodle(wsfunction: str, **params) -> dict:
    """GETs {MOODLE_URL}/webservice/rest/server.php for wsfunction.

    List-valued kwargs are flattened into Moodle's expected
    name[0]=x&name[1]=y query-string form.
    """
    if not MOODLE_URL or not MOODLE_TOKEN:
        raise MoodleCallError("MOODLE_URL or MOODLE_TOKEN is not set in .env")

    query = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
    }
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                query[f"{key}[{index}]"] = item
        else:
            query[key] = value

    try:
        response = requests.get(
            f"{MOODLE_URL}/webservice/rest/server.php", params=query, timeout=20
        )
    except requests.RequestException:
        # Never surface str(exc) here: requests embeds the full request URL
        # (wstoken included) in its exception messages.
        raise MoodleCallError(
            "Network error while contacting Moodle (check MOODLE_URL/connectivity)."
        )

    if response.status_code != 200:
        raise MoodleCallError(f"HTTP {response.status_code} from Moodle server.")

    try:
        data = response.json()
    except ValueError:
        raise MoodleCallError(
            "Response was not valid JSON (check MOODLE_URL points at the Moodle root)."
        )

    if isinstance(data, dict) and ("exception" in data or "errorcode" in data):
        errorcode = data.get("errorcode", "unknown_error")
        message = data.get("message", "")
        raise MoodleCallError(f"{errorcode}: {message}")

    return data
