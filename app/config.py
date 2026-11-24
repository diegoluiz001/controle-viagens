from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente (prioridade) ou do arquivo .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    @field_validator("database_url")
    @classmethod
    def ajustar_driver(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("DATABASE_URL não configurada")
        # O Neon fornece "postgresql://"; o SQLAlchemy precisa saber que o driver é o psycopg 3.
        for prefixo in ("postgres://", "postgresql://"):
            if valor.startswith(prefixo):
                return "postgresql+psycopg://" + valor[len(prefixo):]
        return valor


@lru_cache
def get_settings() -> Settings:
    return Settings()
