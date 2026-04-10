"""
orchestrator.messaging — Transport abstraction layer.

Provides a unified interface for messenger backends (Telegram, MAX, etc.)
so that Bridge, Watcher, and main.py remain transport-agnostic.
"""
from orchestrator.messaging.base import MessengerTransport, CanonicalEvent

__all__ = ["MessengerTransport", "CanonicalEvent"]
