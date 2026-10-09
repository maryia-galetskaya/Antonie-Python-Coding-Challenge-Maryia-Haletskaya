"""Environment-backed settings shared by the API and command-line tools."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable through ``ANTONIE_BOOKS_*`` variables."""

    model_config = SettingsConfigDict(env_prefix="ANTONIE_BOOKS_", extra="ignore")

    app_name: str = "Antonie Books API"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_database: str = "antonie_books"
