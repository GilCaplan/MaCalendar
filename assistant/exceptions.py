"""Custom exception hierarchy for the voice assistant."""


class AssistantError(Exception):
    """Base exception for all assistant errors."""


class ConfigError(AssistantError):
    """Bad or missing configuration."""


class AudioCaptureError(AssistantError):
    """Microphone permission denied or device not found."""


class STTError(AssistantError):
    """Speech-to-text transcription failed."""


class WhisperError(STTError):
    """Local Whisper model error."""


class GoogleSTTError(STTError):
    """Google Cloud STT error."""


class OllamaError(AssistantError):
    """Ollama LLM error."""


class LLMUnavailableError(AssistantError):
    """Raised when the chosen LLM backend cannot be reached."""


class LLMTimeoutError(AssistantError):
    """Raised when the LLM backend times out."""


class OllamaUnavailableError(OllamaError, LLMUnavailableError):
    """Cannot connect to Ollama (not running)."""


class OllamaTimeoutError(OllamaError, LLMTimeoutError):
    """Ollama took too long to respond."""


class ParseError(AssistantError):
    """Failed to parse LLM response into a valid intent."""


class AuthError(AssistantError):
    """Microsoft authentication error."""


class AuthExpiredError(AuthError):
    """Token expired — user needs to re-authenticate."""


class GraphAPIError(AssistantError):
    """Microsoft Graph API returned an error."""


class EventBuildError(AssistantError):
    """Cannot build a valid calendar event from the parsed intent."""
