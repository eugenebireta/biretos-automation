import sys

from .errors import ConfigValidationError
from .validator import format_config_error, validate_config

_CONFIG = None


def get_config():
    global _CONFIG
    if _CONFIG is None:
        try:
            _CONFIG = validate_config()
        except ConfigValidationError as exc:
            print(format_config_error(exc), file=sys.stderr)
            raise SystemExit(1)
    return _CONFIG
