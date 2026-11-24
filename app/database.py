from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

# pool_pre_ping: o Neon suspende o banco ocioso e derruba conexões antigas;
# o SQLAlchemy testa a conexão antes de usá-la e reconecta se necessário.
engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def identificacao_banco() -> str:
    """Identificador do servidor de banco (no Neon, o endpoint 'ep-...'). Não contém credenciais."""
    return (engine.url.host or "desconhecido").split(".")[0]


def get_db() -> Iterator[Session]:
    """Abre uma sessão por requisição e garante o fechamento ao final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
