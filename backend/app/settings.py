from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parents[1]   # .../traffic_scan/backend
load_dotenv(BASE_DIR / ".env")

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")
DEFAULT_CITY    = os.getenv("DEFAULT_CITY", "Columbus,OH")
BBOX_SW         = os.getenv("BBOX_SW", "39.9300,-83.0550")
BBOX_NE         = os.getenv("BBOX_NE", "40.0300,-82.9650")

# Use a simple relative path from backend/, resolve to absolute
DB_PATH_ENV = os.getenv("DB_PATH", "data/traffic.sqlite")
DB_PATH     = str((BASE_DIR / DB_PATH_ENV).resolve())

INGEST_ROWS = int(os.getenv("INGEST_ROWS", "6"))
INGEST_COLS = int(os.getenv("INGEST_COLS", "6"))