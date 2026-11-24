"""Importação do CSV: leitura, validação, idempotência, sequence e reset."""
import pytest
from sqlalchemy import func, select, text

from app.models import Empresa, Linha, Viagem, viagem_codigo_seq
from app.services.importacao import (
    COLUNAS,
    ErroImportacao,
    formatar_id_viagem,
    importar,
    ler_csv,
    proximo_id_viagem,
    resetar,
)

CABECALHO = ";".join(COLUNAS)
LINHA_VALIDA = "VG0001;001;Viação Aurora;101;Centro - Norte;2026-10-20;06:10;AUR-1001;REALIZADA;"


@pytest.fixture(scope="module")
def registros():
    return ler_csv()


def _contar(db, modelo) -> int:
    return db.scalar(select(func.count()).select_from(modelo))


def _csv(tmp_path, *linhas: str):
    arquivo = tmp_path / "viagens.csv"
    arquivo.write_text("\n".join([CABECALHO, *linhas]) + "\n", encoding="utf-8-sig")
    return arquivo


# --------------------------------------------------------------------------- leitura


def test_le_os_180_registros_preservando_formatos(registros):
    assert len(registros) == 180
    primeiro, segundo = registros[0], registros[1]
    assert primeiro.id_viagem == "VG0001"
    assert primeiro.empresa_codigo == "001"                 # zeros à esquerda preservados
    assert primeiro.empresa_nome == "Viação Aurora"         # acentuação (UTF-8) preservada
    assert primeiro.motivo_nao_realizacao == "MANUTENCAO"
    assert segundo.motivo_nao_realizacao is None            # vazio vira None (NULL no banco)


@pytest.mark.parametrize("formatado, numero", [("VG0001", 1), ("VG0181", 181), ("VG10000", 10000)])
def test_formatar_id_viagem(formatado, numero):
    assert formatar_id_viagem(numero) == formatado


def test_arquivo_invalido_lista_erros_por_linha_e_nao_grava(db, tmp_path):
    arquivo = _csv(
        tmp_path,
        LINHA_VALIDA,
        "VG0002;001;Viação Aurora;101;Centro - Norte;2026-10-20;06:20;AUR-1002;REALIZADA;PESSOAL",
        "VG0003;1;Viação Aurora;101;Centro - Norte;2026-13-01;25:00;AUR-1003;NAO_REALIZADA;",
        LINHA_VALIDA,  # id repetido
    )
    with pytest.raises(ErroImportacao) as erro:
        ler_csv(arquivo)

    mensagens = "\n".join(erro.value.erros)
    assert "linha 3: viagem REALIZADA não pode ter motivo" in mensagens
    assert "linha 4:" in mensagens and "3 dígitos" in mensagens and "data_viagem" in mensagens
    assert "horario_programado" in mensagens and "exige motivo" in mensagens
    assert "linha 5: id_viagem VG0001 repetido (já aparece na linha 2)" in mensagens
    assert _contar(db, Viagem) == 0


def test_cabecalho_errado_e_recusado(tmp_path):
    arquivo = tmp_path / "errado.csv"
    arquivo.write_text("id;empresa\nVG0001;001\n", encoding="utf-8")
    with pytest.raises(ErroImportacao, match="nada foi gravado"):
        ler_csv(arquivo)


# --------------------------------------------------------------------------- gravação


def test_primeira_importacao(db, registros):
    resultado = importar(db, registros)

    assert resultado.lidos == 180
    assert resultado.inseridos == 180
    assert resultado.existentes == 0
    assert (resultado.empresas_novas, resultado.linhas_novas) == (3, 9)
    assert (_contar(db, Empresa), _contar(db, Linha), _contar(db, Viagem)) == (3, 9, 180)
    assert sorted(db.scalars(select(Empresa.codigo))) == ["001", "002", "003"]
    assert proximo_id_viagem(db) == "VG0181"


def test_reimportacao_nao_duplica(db, registros):
    importar(db, registros)
    resultado = importar(db, registros)

    assert (resultado.inseridos, resultado.existentes) == (0, 180)
    assert (resultado.empresas_novas, resultado.linhas_novas) == (0, 0)
    assert _contar(db, Viagem) == 180


def test_reimportacao_repoe_somente_as_viagens_excluidas(db, registros):
    importar(db, registros)
    db.execute(text("DELETE FROM viagem WHERE id_viagem IN ('VG0005', 'VG0099')"))
    db.commit()

    resultado = importar(db, registros)

    assert (resultado.inseridos, resultado.existentes) == (2, 178)
    assert _contar(db, Viagem) == 180


def test_reimportacao_nao_reaproveita_id_ja_entregue(db, registros):
    importar(db, registros)
    db.scalar(select(viagem_codigo_seq.next_value()))  # simula a criação da VG0181 pela API
    db.commit()

    importar(db, registros)

    assert proximo_id_viagem(db) == "VG0182"


def test_reset_restaura_a_base_original(db, registros):
    importar(db, registros)
    db.execute(text("UPDATE viagem SET status = 'REALIZADA', motivo_nao_realizacao = NULL WHERE id_viagem = 'VG0001'"))
    db.execute(text("DELETE FROM viagem WHERE id_viagem = 'VG0002'"))
    db.commit()

    resultado = resetar(db, registros)

    assert resultado.inseridos == 180
    assert _contar(db, Viagem) == 180
    original = db.execute(
        text("SELECT status, motivo_nao_realizacao FROM viagem WHERE id_viagem = 'VG0001'")
    ).one()
    assert tuple(original) == ("NAO_REALIZADA", "MANUTENCAO")
    assert proximo_id_viagem(db) == "VG0181"


def test_reset_recusa_identificador_de_banco_errado(db, registros, capsys):
    from scripts.reset_db import main

    importar(db, registros)

    assert main(["--confirmar", "ep-banco-errado"]) == 2
    assert "RECUSADO" in capsys.readouterr().out
    assert _contar(db, Viagem) == 180  # nada foi apagado
