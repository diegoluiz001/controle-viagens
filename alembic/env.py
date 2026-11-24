"""Configuração do Alembic.

Usa a mesma DATABASE_URL e os mesmos modelos da aplicação, garantindo que
migrations e código nunca divirjam. Nenhuma URL fica gravada em alembic.ini.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.models import Base  # registra as tabelas no metadata (necessário para o autogenerate)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar ao banco (alembic upgrade head --sql)."""
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrations conectando ao banco.

    Se quem chamou já forneceu uma conexão (os testes fazem isso, depois de
    verificar a identidade do banco), ela é reutilizada. Caso contrário, abre
    uma conexão nova a partir da DATABASE_URL.
    """
    conexao_externa = config.attributes.get("connection")
    if conexao_externa is not None:
        _executar(conexao_externa)
        return

    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as conexao:
        _executar(conexao)


def _executar(conexao) -> None:
    context.configure(connection=conexao, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
