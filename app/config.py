import os


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
