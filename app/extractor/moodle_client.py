"""Central Moodle Web Services connection helper.

Every call is a GET (or POST for writes) against
{base_url}/webservice/rest/server.php. Error handling never surfaces
str(exc) from `requests` (it embeds the full request URL, wstoken included)
and never echoes the token in any message.

Supports more than one Moodle site: `default_client` talks to
MOODLE_URL/MOODLE_TOKEN (elearning.abchorizon.com — real production data,
unit 373). `lms_client` talks to LMS_MOODLE_URL/LMS_MOODLE_TOKEN
(lms.abchorizon.com — a separate site used for safely testing the
Moodle-embedded "grade with AI" button against a throwaway course).
Every call site that used the old module-level `call_moodle()` keeps
working unchanged — it is now a thin wrapper around `default_client.call()`.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL = os.getenv("MOODLE_URL", "").rstrip("/")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")

LMS_MOODLE_URL = os.getenv("LMS_MOODLE_URL", "").rstrip("/")
LMS_MOODLE_TOKEN = os.getenv("LMS_MOODLE_TOKEN", "")


class MoodleCallError(Exception):
    pass


class MoodleClient:
    """Bundles one Moodle site's (base_url, token) so callers can target a
    specific site explicitly instead of relying on a single global.
    """

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def call(self, wsfunction: str, *, http_method: str = "GET", **params) -> dict:
        """Calls {base_url}/webservice/rest/server.php for wsfunction.

        List-valued kwargs are flattened into Moodle's expected
        name[0]=x&name[1]=y query-string form. A caller may also pass an
        already-bracketed key directly (e.g. "plugindata[text]") via
        **{...} unpacking for nested Moodle params — Python allows
        non-identifier string keys through dict-unpacking into **params.

        http_method="POST" is for write calls (e.g. mod_assign_save_grade)
        whose payload (a full feedback comment) could exceed a GET URL
        length limit — read calls keep the default GET.
        """
        if not self.base_url or not self.token:
            raise MoodleCallError("Moodle base_url or token is not configured.")

        query = {
            "wstoken": self.token,
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
            if http_method == "POST":
                response = requests.post(
                    f"{self.base_url}/webservice/rest/server.php",
                    data=query,
                    timeout=20,
                )
            else:
                response = requests.get(
                    f"{self.base_url}/webservice/rest/server.php",
                    params=query,
                    timeout=20,
                )
        except requests.RequestException:
            # Never surface str(exc) here: requests embeds the full request
            # URL (wstoken included) in its exception messages.
            raise MoodleCallError(
                "Network error while contacting Moodle (check base_url/connectivity)."
            )

        if response.status_code != 200:
            raise MoodleCallError(f"HTTP {response.status_code} from Moodle server.")

        try:
            data = response.json()
        except ValueError:
            raise MoodleCallError(
                "Response was not valid JSON (check base_url points at the Moodle root)."
            )

        if isinstance(data, dict) and ("exception" in data or "errorcode" in data):
            errorcode = data.get("errorcode", "unknown_error")
            message = data.get("message", "")
            raise MoodleCallError(f"{errorcode}: {message}")

        return data


default_client = MoodleClient(MOODLE_URL, MOODLE_TOKEN)
lms_client = MoodleClient(LMS_MOODLE_URL, LMS_MOODLE_TOKEN)


def call_moodle(wsfunction: str, *, http_method: str = "GET", **params) -> dict:
    """Back-compat wrapper — always targets the default (elearning) site."""
    return default_client.call(wsfunction, http_method=http_method, **params)
