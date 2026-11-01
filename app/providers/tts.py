"""Optional server-only TTS provider abstraction."""

from __future__ import annotations

from typing import Tuple

from app.core.config import Settings


class TtsProvider:
    """
    Recognizes TTS_API_KEY as an optional server-only setting.
    Remains disabled unless provider, endpoint, model, and API key are all supplied.
    Never exposes TTS_API_KEY to public clients.
    """

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.tts_api_key
        self.provider = settings.tts_provider
        self.base_url = settings.tts_base_url
        self.model = settings.tts_model
        self.enabled = settings.tts_enabled

    def check_health(self) -> Tuple[bool, str]:
        if not self.enabled:
            return True, "TTS optional integration disabled (not required)"
        return True, f"TTS configured ({self.provider} / {self.model})"
