import os
from urllib.parse import urlparse


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (stdlib only). Existing env vars win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if minimum <= parsed <= maximum else default


class Settings:
    def __init__(self) -> None:
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
        self.openai_compatible_base_url = os.getenv(
            "OPENAI_COMPATIBLE_BASE_URL",
            "http://127.0.0.1:1234/v1",
        )
        self.openai_compatible_model = os.getenv(
            "OPENAI_COMPATIBLE_MODEL",
            "qwen/qwen3.6-27b",
        )
        self.openai_compatible_api_key = os.getenv(
            "OPENAI_COMPATIBLE_API_KEY",
            "",
        )
        self.openai_compatible_max_tokens = _bounded_int(
            os.getenv("OPENAI_COMPATIBLE_MAX_TOKENS"),
            default=1_024,
            minimum=128,
            maximum=4_096,
        )
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
        self.jwt_secret = os.getenv("JWT_SECRET", "")
        self.jwt_algorithm = "HS256"
        self.jwt_issuer = "supportassist"
        self.jwt_audience = "supportassist-api"
        self.jwt_ttl_seconds = _bounded_int(
            os.getenv("JWT_TTL_SECONDS"),
            default=900,
            minimum=60,
            maximum=86_400,
        )
        self.db_path = os.getenv("DB_PATH", "./supportassist.db")
        self.expose_debug_trace = _as_bool(os.getenv("EXPOSE_DEBUG_TRACE"), default=False)


settings = Settings()


def _require_http_base_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{name} must be an absolute HTTP(S) URL")


def validate_llm_config() -> None:
    """Fail before serving requests when the selected model provider is invalid."""
    if settings.llm_provider == "ollama":
        _require_http_base_url(settings.ollama_base_url, "OLLAMA_BASE_URL")
        if not settings.ollama_model.strip():
            raise RuntimeError("OLLAMA_MODEL must not be empty")
        return
    if settings.llm_provider == "openai_compatible":
        _require_http_base_url(
            settings.openai_compatible_base_url,
            "OPENAI_COMPATIBLE_BASE_URL",
        )
        if not settings.openai_compatible_model.strip():
            raise RuntimeError("OPENAI_COMPATIBLE_MODEL must not be empty")
        return
    raise RuntimeError(
        "LLM_PROVIDER must be either 'ollama' or 'openai_compatible'"
    )
