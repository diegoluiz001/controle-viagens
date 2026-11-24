"""API de viagens: listagem com filtros, consulta, criação, edição e exclusão.

Base usada: os 180 registros do CSV (18 viagens por dia de 20 a 29/10/2026,
3 empresas com 60 viagens cada, 9 linhas com 20 viagens cada).
"""
from datetime import date, datetime

import pytest

NOVA = {
    "linha_id": 1,
    "data_viagem": "2026-11-02",
    "horario_programado": "07:45",
    "veiculo": "AUR-9999",
    "status": "NAO_REALIZADA",
    "motivo_nao_realizacao": "TRANSITO",
}


def _ids(cliente) -> dict:
    """{'001': id, ..., ('001','101'): id, ...} a partir de GET /api/empresas."""
    ids = {}
    for empresa in cliente.get("/api/empresas").json():
        ids[empresa["codigo"]] = empresa["id"]
        for linha in empresa["linhas"]:
            ids[(empresa["codigo"], linha["codigo"])] = linha["id"]
    return ids


def _listar(cliente, **params):
    resposta = cliente.get("/api/viagens", params={"por_pagina": 500, **params})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


# --------------------------------------------------------------------------- empresas


def test_lista_empresas_com_linhas(cliente, base_importada):
    empresas = cliente.get("/api/empresas").json()

    assert [e["codigo"] for e in empresas] == ["001", "002", "003"]  # zeros à esquerda preservados
    assert empresas[0]["nome"] == "Viação Aurora"
    assert [l["codigo"] for l in empresas[0]["linhas"]] == ["101", "102", "103"]


# --------------------------------------------------------------------------- listagem e filtros


def test_listagem_sem_filtro_pagina_e_formata(cliente, base_importada):
    pagina1 = cliente.get("/api/viagens").json()
    assert (pagina1["total"], pagina1["pagina"], pagina1["por_pagina"], len(pagina1["itens"])) == (180, 1, 50, 50)

    primeira = pagina1["itens"][0]
    assert primeira["data_viagem"] == "2026-10-20"
    assert len(primeira["horario_programado"]) == 5  # HH:MM, sem segundos
    assert {"empresa_codigo", "empresa_nome", "linha_codigo", "linha_descricao"} <= primeira.keys()

    ultima = cliente.get("/api/viagens", params={"pagina": 4}).json()
    assert len(ultima["itens"]) == 30  # 180 = 50 + 50 + 50 + 30


@pytest.mark.parametrize(
    "inicio, fim, esperado",
    [
        ("2026-10-21", "2026-10-23", 54),  # 3 dias x 18: as duas pontas entram
        ("2026-10-20", "2026-10-20", 18),  # início = fim: um dia inteiro
        ("2026-10-29", None, 18),  # só data inicial
        (None, "2026-10-20", 18),  # só data final
        ("2026-11-01", "2026-11-30", 0),  # período sem viagens
    ],
)
def test_filtro_de_periodo_e_inclusivo(cliente, base_importada, inicio, fim, esperado):
    params = {k: v for k, v in {"data_inicio": inicio, "data_fim": fim}.items() if v}
    resultado = _listar(cliente, **params)

    assert resultado["total"] == esperado
    for item in resultado["itens"]:
        dia = date.fromisoformat(item["data_viagem"])
        assert (inicio is None or dia >= date.fromisoformat(inicio)) and (fim is None or dia <= date.fromisoformat(fim))


def test_filtro_por_empresa_e_por_linha(cliente, base_importada):
    ids = _ids(cliente)

    por_empresa = _listar(cliente, empresa_id=ids["002"])
    assert por_empresa["total"] == 60
    assert {i["empresa_codigo"] for i in por_empresa["itens"]} == {"002"}

    por_linha = _listar(cliente, linha_id=ids[("003", "302")])
    assert por_linha["total"] == 20
    assert {(i["empresa_codigo"], i["linha_codigo"]) for i in por_linha["itens"]} == {("003", "302")}


def test_filtros_combinados(cliente, base_importada):
    ids = _ids(cliente)
    inicio, fim = date(2026, 10, 22), date(2026, 10, 25)
    esperado = sum(
        1
        for r in base_importada
        if r.empresa_codigo == "001" and r.linha_codigo == "102" and inicio <= r.data_viagem <= fim
    )

    resultado = _listar(
        cliente,
        data_inicio=inicio.isoformat(),
        data_fim=fim.isoformat(),
        empresa_id=ids["001"],
        linha_id=ids[("001", "102")],
    )
    assert esperado > 0
    assert resultado["total"] == esperado

    # Linha de outra empresa: a combinação é vazia, não um erro.
    assert _listar(cliente, empresa_id=ids["001"], linha_id=ids[("002", "201")])["total"] == 0


def test_periodo_invertido_e_recusado(cliente, base_importada):
    resposta = cliente.get("/api/viagens", params={"data_inicio": "2026-10-25", "data_fim": "2026-10-20"})
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["type"] == "periodo_invalido"


# --------------------------------------------------------------------------- consulta


def test_consulta_por_id_viagem(cliente, base_importada):
    viagem = cliente.get("/api/viagens/VG0001").json()
    assert viagem["id_viagem"] == "VG0001"
    assert (viagem["empresa_codigo"], viagem["linha_codigo"]) == ("001", "101")
    assert (viagem["horario_programado"], viagem["veiculo"]) == ("06:10", "AUR-1001")

    assert cliente.get("/api/viagens/VG9999").status_code == 404


# --------------------------------------------------------------------------- criação


def test_criacao_gera_id_sequencial(cliente, base_importada):
    primeira = cliente.post("/api/viagens", json=NOVA)
    segunda = cliente.post("/api/viagens", json=NOVA)

    assert primeira.status_code == 201
    assert primeira.json()["id_viagem"] == "VG0181"
    assert segunda.json()["id_viagem"] == "VG0182"
    assert primeira.json()["horario_programado"] == "07:45"
    assert _listar(cliente)["total"] == 182


def test_criacao_com_linha_inexistente(cliente, base_importada):
    resposta = cliente.post("/api/viagens", json={**NOVA, "linha_id": 999})

    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["type"] == "linha_inexistente"
    assert cliente.post("/api/viagens", json=NOVA).json()["id_viagem"] == "VG0181"  # nada consumido


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("id_viagem", "VG5000"),  # o servidor gera; o cliente não escolhe
        ("veiculo", "   "),
        ("horario_programado", "25:00"),
        ("data_viagem", "20/10/2026"),
    ],
)
def test_criacao_com_dados_invalidos(cliente, base_importada, campo, valor):
    assert cliente.post("/api/viagens", json={**NOVA, campo: valor}).status_code == 422
    assert _listar(cliente)["total"] == 180


# --------------------------------------------------------------------------- edição


def test_edicao_altera_campos_e_mantem_id(cliente, base_importada):
    ids = _ids(cliente)
    antes = cliente.get("/api/viagens/VG0002").json()

    resposta = cliente.put(
        "/api/viagens/VG0002",
        json={**NOVA, "linha_id": ids[("003", "301")], "status": "REALIZADA", "motivo_nao_realizacao": None},
    )

    assert resposta.status_code == 200
    depois = resposta.json()
    assert depois["id_viagem"] == "VG0002"
    assert (depois["empresa_codigo"], depois["linha_codigo"]) == ("003", "301")
    assert (depois["data_viagem"], depois["horario_programado"], depois["veiculo"]) == ("2026-11-02", "07:45", "AUR-9999")
    assert depois["created_at"] == antes["created_at"]
    assert datetime.fromisoformat(depois["updated_at"]) > datetime.fromisoformat(antes["updated_at"])  # trigger
    assert cliente.get("/api/viagens/VG0002").json() == depois  # persistido


def test_edicao_nao_permite_trocar_id_nem_editar_inexistente(cliente, base_importada):
    assert cliente.put("/api/viagens/VG0002", json={**NOVA, "id_viagem": "VG0003"}).status_code == 422
    assert cliente.put("/api/viagens/VG9999", json=NOVA).status_code == 404


# --------------------------------------------------------------------------- exclusão


def test_exclusao(cliente, base_importada):
    resposta = cliente.delete("/api/viagens/VG0010")

    assert resposta.status_code == 204
    assert resposta.content == b""
    assert cliente.get("/api/viagens/VG0010").status_code == 404
    assert cliente.delete("/api/viagens/VG0010").status_code == 404
    assert _listar(cliente)["total"] == 179


def test_id_de_viagem_excluida_nao_e_reaproveitado(cliente, base_importada):
    criada = cliente.post("/api/viagens", json=NOVA).json()["id_viagem"]
    cliente.delete(f"/api/viagens/{criada}")

    assert criada == "VG0181"
    assert cliente.post("/api/viagens", json=NOVA).json()["id_viagem"] == "VG0182"
