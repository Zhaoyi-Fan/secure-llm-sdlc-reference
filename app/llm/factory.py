from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_compatible_provider import OpenAICompatibleProvider
from ..config import settings


def create_provider() -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider()
    raise RuntimeError("unsupported LLM provider")
