"""
orchestrator.messaging — Transport abstraction layer.

Provides a unified interface for messenger backends (Telegram, MAX, etc.)
so that Bridge, Watcher, and main.py remain transport-agnostic.
"""
try:
    from orchestrator.messaging.base import MessengerTransport, CanonicalEvent
    from orchestrator.messaging.buttons import InlineKeyboard
except ModuleNotFoundError:
    from messaging.base import MessengerTransport, CanonicalEvent
    from messaging.buttons import InlineKeyboard

__all__ = ["MessengerTransport", "CanonicalEvent", "InlineKeyboard"]
