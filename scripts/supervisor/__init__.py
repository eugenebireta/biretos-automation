from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS_DIR = ROOT / "downloads"
SCOUT_CACHE_DIR = DOWNLOADS_DIR / "scout_cache"
EVIDENCE_DIR = DOWNLOADS_DIR / "evidence"
STATE_ROOT = DOWNLOADS_DIR / "supervisor"
LOGS_DIR = STATE_ROOT / "logs"

QUEUE_SCHEMA_VERSION = "followup_queue_v2"
LOCK_TTL_SECONDS = 6 * 60 * 60
PHOTO_LIMIT = 10
PRICE_LIMIT = 20
REFRESH_PREFIX = "refreshed_catalog"
