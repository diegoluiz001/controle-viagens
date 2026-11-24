"""TESTE OBRIGATÓRIO (2): cálculo dos indicadores considerando filtros.

Os valores esperados NÃO vêm da própria API: são recontados em Python direto dos
registros do CSV (um "gabarito" independente) e comparados com GET /api/indicadores.
"""
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.enums import MotivoNaoRealizacao
from app.services.indicadores import calcular_percentual

MOTIVOS = [m.value for m in MotivoNaoRealizacao]


# --------------------------------------------------------------------------- percentual (sem banco)


@pytest.mark.parametrize(
    "realizadas, programadas, esperado",
    [
        (0, 0, None),  # sem viagens: "Sem dados", nunca divisão por zero
        (0, 5, 0.0),  # há viagens, nenhuma cumprida: 0% (diferente de "Sem dados")
        (1, 3, 33.33),
        (2, 3, 66.67),
        (3, 3, 100.0),
        (132, 180, 73.33),
        (1, 160, 0.63),  # 0,625 arredonda para cima (o round() do Python daria 0,62)
    ],
)
def test_calcular_percentual(realizadas, programadas, esperado):
    assert calcular_percentual(realizadas, programadas) == esperado


# --------------------------------------------------------------------------- gabarito independente


def _ids(cliente) -> dict:
    ids = {}
    for empresa in cliente.get("/api/empresas").json():
        ids[empresa["codigo"]] = empresa["id"]
        for linha in empresa["linhas"]:
            ids[(empresa["codigo"], linha["codigo"])] = linha["id"]
    return ids


def _gabarito(registros, inicio=None, fim=None, empresa=None, linha=None) -> dict:
    """Recalcula os indicadores em Python puro, a partir do CSV."""
    selecionados = [
        r
        for r in registros
        if (inicio is None or r.data_viagem >= inicio)
        and (fim is None or r.data_viagem <= fim)
        and (empresa is None or r.empresa_codigo == empresa)
        and (linha is None or (r.empresa_codigo, r.linha_codigo) == linha)
    ]
    status = Counter(r.status for r in selecionados)
    motivos = Counter(r.motivo_nao_realizacao for r in selecionados if r.motivo_nao_realizacao)
    programadas = len(selecionados)
    return {
        "programadas": programadas,
        "realizadas": status["REALIZADA"],
        "nao_realizadas": status["NAO_REALIZADA"],
        "percentual_cumprimento": (
            float((Decimal(status["REALIZADA"] * 100) / programadas).quantize(Decimal("0.01"), ROUND_HALF_UP))
            if programadas
            else None
        ),
        "sem_dados": programadas == 0,
        "motivos": {m: motivos[m] for m in MOTIVOS},
    }


CENARIOS = {
    "sem filtro": {},
    "periodo 21 a 23/10": {"inicio": date(2026, 10, 21), "fim": date(2026, 10, 23)},
    "um unico dia": {"inicio": date(2026, 10, 27), "fim": date(2026, 10, 27)},
    "so data final": {"fim": date(2026, 10, 22)},
    "empresa 002": {"empresa": "002"},
    "linha 003/301": {"linha": ("003", "301")},
    "empresa 001 + linha 102 + periodo": {
        "inicio": date(2026, 10, 22),
        "fim": date(2026, 10, 26),
        "empresa": "001",
        "linha": ("001", "102"),
    },
}


def _params(ids, inicio=None, fim=None, empresa=None, linha=None) -> dict:
    params = {
        "data_inicio": inicio and inicio.isoformat(),
        "data_fim": fim and fim.isoformat(),
        "empresa_id": empresa and ids[empresa],
        "linha_id": linha and ids[linha],
    }
    return {k: v for k, v in params.items() if v is not None}


# --------------------------------------------------------------------------- API com filtros


@pytest.mark.parametrize("cenario", CENARIOS)
def test_indicadores_com_filtros_conferem_com_o_gabarito(cliente, base_importada, cenario):
    filtros = CENARIOS[cenario]
    params = _params(_ids(cliente), **filtros)

    indicadores = cliente.get("/api/indicadores", params=params).json()

    assert indicadores == _gabarito(base_importada, **filtros)
    assert indicadores["realizadas"] + indicadores["nao_realizadas"] == indicadores["programadas"]
    assert sum(indicadores["motivos"].values()) == indicadores["nao_realizadas"]


def test_valores_da_base_completa(cliente, base_importada):
    indicadores = cliente.get("/api/indicadores").json()
    assert (indicadores["programadas"], indicadores["realizadas"], indicadores["nao_realizadas"]) == (180, 132, 48)
    assert indicadores["percentual_cumprimento"] == 73.33


@pytest.mark.parametrize("cenario", CENARIOS)
def test_usa_os_mesmos_filtros_da_listagem(cliente, base_importada, cenario):
    params = _params(_ids(cliente), **CENARIOS[cenario])

    listagem = cliente.get("/api/viagens", params=params).json()
    indicadores = cliente.get("/api/indicadores", params=params).json()

    assert indicadores["programadas"] == listagem["total"]


def test_filtro_sem_viagens_mostra_zeros_e_sem_dados(cliente, base_importada):
    indicadores = cliente.get(
        "/api/indicadores", params={"data_inicio": "2027-01-01", "data_fim": "2027-01-31"}
    ).json()

    assert indicadores == {
        "programadas": 0,
        "realizadas": 0,
        "nao_realizadas": 0,
        "percentual_cumprimento": None,
        "sem_dados": True,
        "motivos": {m: 0 for m in MOTIVOS},
    }


def test_banco_vazio_tambem_nao_gera_erro(cliente):
    resposta = cliente.get("/api/indicadores")
    assert resposta.status_code == 200
    assert resposta.json()["sem_dados"] is True


def test_periodo_invertido_e_recusado(cliente, base_importada):
    resposta = cliente.get("/api/indicadores", params={"data_inicio": "2026-10-25", "data_fim": "2026-10-20"})
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["type"] == "periodo_invalido"


# --------------------------------------------------------------------------- alterações refletidas


def test_alteracoes_sao_refletidas_nos_indicadores(cliente, base_importada):
    filtro = {"data_inicio": "2026-10-20", "data_fim": "2026-10-20"}
    antes = cliente.get("/api/indicadores", params=filtro).json()

    # VG0001 (20/10) é NAO_REALIZADA / MANUTENCAO: passa a REALIZADA.
    vg0001 = cliente.get("/api/viagens/VG0001").json()
    edicao = {
        "linha_id": vg0001["linha_id"],
        "data_viagem": vg0001["data_viagem"],
        "horario_programado": vg0001["horario_programado"],
        "veiculo": vg0001["veiculo"],
        "status": "REALIZADA",
        "motivo_nao_realizacao": None,
    }
    assert cliente.put("/api/viagens/VG0001", json=edicao).status_code == 200
    depois_edicao = cliente.get("/api/indicadores", params=filtro).json()

    assert depois_edicao["realizadas"] == antes["realizadas"] + 1
    assert depois_edicao["nao_realizadas"] == antes["nao_realizadas"] - 1
    assert depois_edicao["motivos"]["MANUTENCAO"] == antes["motivos"]["MANUTENCAO"] - 1
    assert depois_edicao["programadas"] == antes["programadas"]

    # Excluir uma viagem do dia reduz as programadas.
    assert cliente.delete("/api/viagens/VG0001").status_code == 204
    depois_exclusao = cliente.get("/api/indicadores", params=filtro).json()
    assert depois_exclusao["programadas"] == antes["programadas"] - 1
