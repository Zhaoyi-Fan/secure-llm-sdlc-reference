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


class Settings:
    def __init__(self) -> None:
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.6")
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-only-not-for-production")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.db_path = os.getenv("DB_PATH", "./supportassist.db")


settings = Settings()
