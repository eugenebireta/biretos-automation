import os
from pathlib import Path
from typing import Dict, Optional

from .schema import ENV_NAMES

try:
    from dotenv import load_dotenv
    config_root = Path(__file__).resolve().parent.parent
    load_dotenv(config_root / ".env")
    load_dotenv(config_root.parent / ".env")
except ImportError:
    pass

_RAW_ENV: Dict[str, Optional[str]] = {name: os.getenv(name) for name in ENV_NAMES}


def get_raw_env() -> Dict[str, Optional[str]]:
    return dict(_RAW_ENV)


def get_env_value(name: str, default: Optional[str] = None) -> Optional[str]:
    value = _RAW_ENV.get(name)
    if value is None:
        return default
    return value
