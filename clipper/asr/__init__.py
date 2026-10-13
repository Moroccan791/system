"""ASR providers: swappable speech-to-text backends.

Every provider returns the same `Transcript` (a list of `Word`s with timings),
so the caption stage never cares which engine produced it.

    moonshine      real weights bundled in the pip wheel, offline, CPU (default)
    faster_whisper real word timestamps, best quality; `pip install faster-whisper`
    fixture        deterministic words from a JSON/script, used by tests
"""
from .base import ASRProvider, Transcript, Word, get_provider, list_providers

__all__ = ["ASRProvider", "Transcript", "Word", "get_provider", "list_providers"]
