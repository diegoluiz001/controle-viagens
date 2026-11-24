"""Configuração compartilhada dos testes.

Há dois tipos de teste:
- sem banco (ex.: test_health.py): trocam a sessão por uma falsa;
- com banco (fixture `db`): usam o branch `test` do Neon, protegido por três
  checagens antes de qualquer operação destrutiva:
    1. TEST_DATABASE_URL precisa estar preenchida;
    2. o host de teste precisa ser diferente do host de DATABASE_URL (dev);
    3. o próprio banco precisa ter o comentário 'ambiente=test'
       (gravado uma única vez com: COMMENT ON DATABASE neondb IS 'ambiente=test').
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.orm import Session

from app.config import Settings

MARCA_TESTE = "ambiente=test"
URL_FICTICIA = "postgresql://teste:teste@localhost:1/teste"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


class _ConfigTestes(BaseSettings):
    """Lê as duas URLs (variável de ambiente tem prioridade sobre o .env)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str = ""
    test_database_url: str = ""


_config = _ConfigTestes()

# Durante os testes a aplicação nunca aponta para dev/produção:
# usa o banco de teste (se configurado) ou uma URL fictícia que não conecta a nada.
os.environ["DATABASE_URL"] = _config.test_database_url.strip() or URL_FICTICIA


def _host(url: str) -> str | None:
    url = url.strip()
    return make_url(Settings(database_url=url).database_url).host if url else None


def _verificar_banco_de_teste(conexao: Connection) -> None:
    """Aborta toda a execução se a conexão não for do banco marcado como teste."""
    marca = conexao.execute(
        text(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        )
    ).scalar()
    if marca != MARCA_TESTE:
        pytest.exit(
            "ABORTADO: o banco de TEST_DATABASE_URL não tem a marca 'ambiente=test'. "
            "Nenhum dado foi alterado.",
            returncode=2,
        )


@pytest.fixture(scope="session")
def engine_teste():
    """Engine do banco de teste, já migrado até a última versão (alembic upgrade head)."""
    url_teste = _config.test_database_url.strip()
    if not url_teste:
        pytest.skip("TEST_DATABASE_URL não configurada: testes de banco ignorados")
    if _host(url_teste) == _host(_config.database_url):
        pytest.exit(
            "ABORTADO: TEST_DATABASE_URL aponta para o mesmo host de DATABASE_URL.",
            returncode=2,
        )

    engine = create_engine(Settings(database_url=url_teste).database_url, pool_pre_ping=True)
    with engine.begin() as conexao:
        _verificar_banco_de_teste(conexao)
        config_alembic = Config(str(ALEMBIC_INI))
        config_alembic.attributes["connection"] = conexao  # migra exatamente a conexão verificada
        command.upgrade(config_alembic, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine_teste):
    """Sessão limpa para cada teste: verifica o banco e só então apaga os dados."""
    with engine_teste.begin() as conexao:
        _verificar_banco_de_teste(conexao)
        conexao.execute(text("TRUNCATE viagem, linha, empresa RESTART IDENTITY CASCADE"))
        conexao.execute(text("ALTER SEQUENCE viagem_codigo_seq RESTART"))
    with Session(engine_teste) as sessao:
        yield sessao
