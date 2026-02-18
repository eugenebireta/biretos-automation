class ConfigError(Exception):
    """Базовая ошибка конфигурации."""


class ConfigValidationError(ConfigError):
    """Ошибка валидации конфигурации."""

    def __init__(self, missing=None, invalid=None):
        self.missing = missing or []
        self.invalid = invalid or []
        super().__init__("Configuration validation failed")
