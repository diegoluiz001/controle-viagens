"""O banco recusa dados inválidos mesmo sem passar pela API (defesa em profundidade).

Cada teste tenta gravar algo proibido e confere QUAL constraint barrou a gravação,
pelo nome definido na migration.
"""
from datetime import date, time

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Empresa, Linha, Viagem, viagem_codigo_seq


@pytest.fixture
def linha(db):
    empresa = Empresa(codigo="001", nome="Viação Aurora")
    linha = Linha(empresa=empresa, codigo="101", descricao="Centro - Norte")
    db.add(linha)
    db.commit()
    return linha


def _viagem(linha, **campos) -> Viagem:
    dados = {
        "id_viagem": "VG0001",
        "linha": linha,
        "data_viagem": date(2026, 10, 20),
        "horario_programado": time(6, 10),
        "veiculo": "AUR-1001",
        "status": "REALIZADA",
        "motivo_nao_realizacao": None,
    }
    dados.update(campos)
    return Viagem(**dados)


def _constraint_violada(db, objeto) -> str:
    """Tenta gravar o objeto e devolve o nome da constraint que impediu."""
    db.add(objeto)
    with pytest.raises(IntegrityError) as erro:
        db.commit()
    db.rollback()
    return erro.value.orig.diag.constraint_name


@pytest.mark.parametrize(
    "status, motivo",
    [("REALIZADA", None), ("NAO_REALIZADA", "MANUTENCAO"), ("NAO_REALIZADA", "TRANSITO")],
)
def test_aceita_combinacoes_validas(db, linha, status, motivo):
    db.add(_viagem(linha, status=status, motivo_nao_realizacao=motivo))
    db.commit()
    assert db.scalar(select(func.count()).select_from(Viagem)) == 1


@pytest.mark.parametrize(
    "campos, constraints_esperadas",
    [
        ({"status": "REALIZADA", "motivo_nao_realizacao": "PESSOAL"}, {"ck_viagem_status_motivo_coerente"}),
        ({"status": "NAO_REALIZADA", "motivo_nao_realizacao": None}, {"ck_viagem_status_motivo_coerente"}),
        ({"status": "NAO_REALIZADA", "motivo_nao_realizacao": "CHUVA"}, {"ck_viagem_motivo_valido"}),
        # Status fora da lista viola duas regras; o Postgres informa a primeira que avaliar.
        ({"status": "CANCELADA"}, {"ck_viagem_status_valido", "ck_viagem_status_motivo_coerente"}),
        ({"id_viagem": "X123"}, {"ck_viagem_id_viagem_formato"}),
        ({"id_viagem": "VG12"}, {"ck_viagem_id_viagem_formato"}),
    ],
)
def test_recusa_viagem_invalida(db, linha, campos, constraints_esperadas):
    assert _constraint_violada(db, _viagem(linha, **campos)) in constraints_esperadas


def test_recusa_id_viagem_duplicado(db, linha):
    db.add(_viagem(linha))
    db.commit()
    assert _constraint_violada(db, _viagem(linha, veiculo="AUR-1002")) == "uq_viagem_id_viagem"


@pytest.mark.parametrize("codigo", ["1", "01", "A01"])
def test_recusa_codigo_de_empresa_invalido(db, codigo):
    assert _constraint_violada(db, Empresa(codigo=codigo, nome="Teste")) == "ck_empresa_codigo_formato"


def test_preserva_zeros_a_esquerda(db, linha):
    assert db.scalar(text("SELECT codigo FROM empresa")) == "001"


def test_recusa_linha_repetida_na_mesma_empresa(db, linha):
    repetida = Linha(empresa=linha.empresa, codigo="101", descricao="Outra descrição")
    assert _constraint_violada(db, repetida) == "uq_linha_empresa_id_codigo"


def test_nao_apaga_linha_que_tem_viagens(db, linha):
    db.add(_viagem(linha))
    db.commit()
    # SQL direto: testa a regra do banco (ON DELETE RESTRICT), sem lógica do ORM no meio.
    with pytest.raises(IntegrityError) as erro:
        db.execute(text("DELETE FROM linha WHERE id = :id"), {"id": linha.id})
        db.commit()
    db.rollback()
    assert erro.value.orig.diag.constraint_name == "fk_viagem_linha_id_linha"


def test_updated_at_muda_quando_a_viagem_e_editada(db, linha):
    viagem = _viagem(linha)
    db.add(viagem)
    db.commit()
    criado_em = viagem.created_at
    atualizado_antes = viagem.updated_at

    viagem.veiculo = "AUR-2002"
    db.commit()

    assert viagem.created_at == criado_em          # data de criação não muda
    assert viagem.updated_at > atualizado_antes    # trigger atualizou


def test_sequence_de_negocio_e_independente_do_serial(db, linha):
    db.add(_viagem(linha))  # o INSERT consome a sequence do SERIAL (viagem.id)...
    db.commit()
    # ...mas não a do identificador de negócio, que continua no primeiro valor.
    assert db.scalar(select(viagem_codigo_seq.next_value())) == 1
