from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]

# TODO(auth): replace with the signed-in user once auth exists.
PLACEHOLDER_USER = "Demo CMO"
SYSTEM_USER = "system"


class Settings(BaseSettings):
    # Environment variables win over backend/.env.
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
