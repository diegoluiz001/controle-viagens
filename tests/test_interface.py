"""A interface web é servida pela aplicação (sem banco: só arquivos estáticos)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_raiz_entrega_a_pagina_html():
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/html")
    assert "<title>Controle de Viagens</title>" in resposta.text
    assert '<script src="/static/app.js' in resposta.text


@pytest.mark.parametrize(
    "caminho, tipo",
    [("/static/app.js", "javascript"), ("/static/styles.css", "text/css")],
)
def test_arquivos_estaticos_sao_servidos(caminho, tipo):
    resposta = cliente.get(caminho)
    assert resposta.status_code == 200
    assert tipo in resposta.headers["content-type"]


def test_interface_nao_aparece_na_documentacao_da_api():
    assert "/" not in cliente.get("/openapi.json").json()["paths"]


def test_textos_do_banco_nunca_entram_como_html():
    """Proteção contra XSS: o script não usa innerHTML para montar a página."""
    script = cliente.get("/static/app.js").text
    assert "innerHTML" not in script.replace("(nunca innerHTML)", "")
