"""Environment-backed application settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable through ``ANTONIE_BOOKS_*`` variables."""

    model_config = SettingsConfigDict(env_prefix="ANTONIE_BOOKS_", extra="ignore")

    app_name: str = "Antonie Books API"
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_database: str = "antonie_books"


__all__ = ["Settings"]
