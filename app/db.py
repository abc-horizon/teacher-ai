from pathlib import Path

from sqlmodel import create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "app_dev.db"
DB_URL = f"sqlite:///{DB_PATH}"


def get_engine():
    return create_engine(DB_URL)
