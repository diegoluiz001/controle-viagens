"""TESTE OBRIGATÓRIO (1): validação da regra de status/motivo.

Regra (item 05 do desafio):
- status = NAO_REALIZADA -> motivo obrigatório e um dos quatro previstos;
- status = REALIZADA     -> motivo vazio.

É verificada em duas camadas aqui: no modelo Pydantic (unidade, sem banco) e na API
(POST e PUT), confirmando que nada é gravado quando a regra é violada. A terceira
camada, o CHECK do banco, é testada em test_banco_constraints.py.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import Viagem
from app.schemas import MSG_NAO_REALIZADA_SEM_MOTIVO, MSG_REALIZADA_COM_MOTIVO, ViagemEntrada

BASE = {"linha_id": 1, "data_viagem": "2026-10-20", "horario_programado": "06:10", "veiculo": "AUR-1001"}


# --------------------------------------------------------------------------- unidade (sem banco)


@pytest.mark.parametrize(
    "status, motivo",
    [
        ("REALIZADA", None),
        ("REALIZADA", ""),  # campo vazio do formulário = sem motivo
        ("NAO_REALIZADA", "MANUTENCAO"),
        ("NAO_REALIZADA", "PESSOAL"),
        ("NAO_REALIZADA", "TRANSITO"),
        ("NAO_REALIZADA", "OPERACAO"),
    ],
)
def test_combinacoes_validas_sao_aceitas(status, motivo):
    viagem = ViagemEntrada(**BASE, status=status, motivo_nao_realizacao=motivo)
    assert viagem.status == status
    assert viagem.motivo_nao_realizacao == (motivo or None)


@pytest.mark.parametrize(
    "status, motivo, mensagem",
    [
        ("REALIZADA", "TRANSITO", MSG_REALIZADA_COM_MOTIVO),
        ("NAO_REALIZADA", None, MSG_NAO_REALIZADA_SEM_MOTIVO),
        ("NAO_REALIZADA", "", MSG_NAO_REALIZADA_SEM_MOTIVO),
        ("NAO_REALIZADA", "CHUVA", "'MANUTENCAO', 'PESSOAL', 'TRANSITO' or 'OPERACAO'"),
        ("NAO_REALIZADA", "transito", "'MANUTENCAO', 'PESSOAL', 'TRANSITO' or 'OPERACAO'"),
        ("CANCELADA", None, "'REALIZADA' or 'NAO_REALIZADA'"),
    ],
)
def test_combinacoes_invalidas_sao_recusadas(status, motivo, mensagem):
    with pytest.raises(ValidationError) as erro:
        ViagemEntrada(**BASE, status=status, motivo_nao_realizacao=motivo)
    assert mensagem in str(erro.value)


# --------------------------------------------------------------------------- API (com banco de teste)


def _total_viagens(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Viagem))


@pytest.mark.parametrize(
    "status, motivo, mensagem",
    [
        ("REALIZADA", "PESSOAL", MSG_REALIZADA_COM_MOTIVO),
        ("NAO_REALIZADA", None, MSG_NAO_REALIZADA_SEM_MOTIVO),
    ],
)
def test_api_recusa_criacao_que_viola_a_regra(cliente, db, base_importada, status, motivo, mensagem):
    resposta = cliente.post("/api/viagens", json={**BASE, "status": status, "motivo_nao_realizacao": motivo})

    assert resposta.status_code == 422
    erro = resposta.json()["detail"][0]
    assert erro["type"] == "status_motivo"
    assert erro["msg"] == mensagem
    assert _total_viagens(db) == 180  # nada foi gravado

    # E nenhum id_viagem foi consumido pela tentativa recusada.
    valida = cliente.post("/api/viagens", json={**BASE, "status": "REALIZADA"})
    assert valida.json()["id_viagem"] == "VG0181"


def test_api_recusa_edicao_que_viola_a_regra_e_preserva_o_registro(cliente, base_importada):
    # VG0001 é NAO_REALIZADA / MANUTENCAO no CSV. Mudar só o status deixaria o motivo "sobrando".
    resposta = cliente.put(
        "/api/viagens/VG0001",
        json={**BASE, "status": "REALIZADA", "motivo_nao_realizacao": "MANUTENCAO"},
    )
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["msg"] == MSG_REALIZADA_COM_MOTIVO

    atual = cliente.get("/api/viagens/VG0001").json()
    assert (atual["status"], atual["motivo_nao_realizacao"]) == ("NAO_REALIZADA", "MANUTENCAO")


def test_api_aceita_edicao_coerente_nos_dois_sentidos(cliente, base_importada):
    # NAO_REALIZADA -> REALIZADA (limpando o motivo)
    realizada = cliente.put("/api/viagens/VG0001", json={**BASE, "status": "REALIZADA", "motivo_nao_realizacao": None})
    assert realizada.status_code == 200
    assert (realizada.json()["status"], realizada.json()["motivo_nao_realizacao"]) == ("REALIZADA", None)

    # REALIZADA -> NAO_REALIZADA (informando o motivo)
    nao_realizada = cliente.put(
        "/api/viagens/VG0001", json={**BASE, "status": "NAO_REALIZADA", "motivo_nao_realizacao": "OPERACAO"}
    )
    assert nao_realizada.status_code == 200
    assert nao_realizada.json()["motivo_nao_realizacao"] == "OPERACAO"
