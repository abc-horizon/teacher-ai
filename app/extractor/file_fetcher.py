"""Download a Moodle submission file and extract its text (T1.4).

download_file() never surfaces MOODLE_TOKEN — not in a printed message, not
in a raised exception's text — mirroring the same discipline as
moodle_client.call_moodle(). Bytes are handled entirely in memory: nothing
is ever written to disk, so there is no temp file to clean up afterwards.
"""

import os
from io import BytesIO

import requests
from dotenv import load_dotenv

load_dotenv()

MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")


class FileFetchError(Exception):
    pass


def download_file(fileurl: str, token: str = None) -> bytes:
    """GETs a Moodle pluginfile URL with the wstoken appended, per Moodle's
    file-serving convention. Returns the raw bytes.

    token defaults to MOODLE_TOKEN (the elearning.abchorizon.com instance) —
    pass the matching site's token explicitly when fileurl came from a
    different Moodle instance (e.g. app.extractor.moodle_client.LMS_MOODLE_TOKEN),
    since a fileurl only serves content to the token from its own site.
    """
    token = token or MOODLE_TOKEN
    if not token:
        raise FileFetchError("MOODLE_TOKEN is not set in .env")
    if not fileurl:
        raise FileFetchError("fileurl is empty")

    separator = "&" if "?" in fileurl else "?"
    url = f"{fileurl}{separator}token={token}"

    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException:
        # Never surface str(exc) here: requests embeds the full request URL
        # (token included) in its exception messages.
        raise FileFetchError("Network error while downloading file from Moodle.")

    if response.status_code != 200:
        raise FileFetchError(
            f"HTTP {response.status_code} while downloading file from Moodle."
        )

    return response.content


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extracts plain text from .docx/.pdf/.txt bytes. Raises ValueError for
    any other extension — callers decide how to record that as a status.
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    if suffix == "docx":
        from docx import Document

        document = Document(BytesIO(file_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    if suffix == "pdf":
        import pdfplumber

        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    raise ValueError(f"unsupported format: .{suffix or '(no extension)'}")
