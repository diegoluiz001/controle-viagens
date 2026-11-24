import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.database import get_db
from app.main import app


class SessaoFalsa:
    """Simula a sessão do banco: responde normalmente ou lança o erro informado."""

    def __init__(self, erro: Exception | None = None):
        self.erro = erro

    def execute(self, *args, **kwargs):
        if self.erro:
            raise self.erro


@pytest.fixture
def cliente():
    def _cliente(sessao: SessaoFalsa) -> TestClient:
        app.dependency_overrides[get_db] = lambda: sessao
        return TestClient(app)

    yield _cliente
    app.dependency_overrides.clear()


def test_health_ok(cliente):
    resposta = cliente(SessaoFalsa()).get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "database": "ok"}


def test_health_banco_indisponivel(cliente):
    erro = OperationalError("SELECT 1", {}, Exception("conexão recusada"))
    resposta = cliente(SessaoFalsa(erro)).get("/health")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "erro", "database": "indisponivel"}
    assert "conexão recusada" not in resposta.text  # detalhe interno não vaza


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("postgresql://u:s@h/db", "postgresql+psycopg://u:s@h/db"),
        ("postgres://u:s@h/db", "postgresql+psycopg://u:s@h/db"),
        ("postgresql+psycopg://u:s@h/db", "postgresql+psycopg://u:s@h/db"),
    ],
)
def test_config_ajusta_driver(entrada, esperado):
    assert Settings(database_url=entrada).database_url == esperado


def test_config_rejeita_url_vazia():
    with pytest.raises(ValueError):
        Settings(database_url="  ")
