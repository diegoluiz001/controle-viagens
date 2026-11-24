"""Importação do CSV de viagens para o banco.

Fluxo: ler_csv() lê e valida TODAS as linhas -> importar() grava numa única transação.

Regras:
- tudo ou nada: se alguma linha for inválida, nada é gravado;
- idempotente: viagem com id_viagem já existente é ignorada (ON CONFLICT DO NOTHING);
- códigos são lidos como texto, preservando zeros à esquerda ("001").
"""
import csv
import re
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.enums import MotivoNaoRealizacao, StatusViagem
from app.models import Empresa, Linha, Viagem

CAMINHO_PADRAO = Path(__file__).resolve().parents[2] / "data" / "base_viagens_teste.csv"

COLUNAS = [
    "id_viagem",
    "empresa_codigo",
    "empresa_nome",
    "linha_codigo",
    "linha_descricao",
    "data_viagem",
    "horario_programado",
    "veiculo",
    "status",
    "motivo_nao_realizacao",
]

# Tamanhos máximos das colunas de texto no banco (evita erro no meio da gravação).
TAMANHO_MAXIMO = {"empresa_nome": 100, "linha_codigo": 10, "linha_descricao": 120, "veiculo": 30}

RE_ID_VIAGEM = re.compile(r"VG[0-9]{4,}")
RE_EMPRESA = re.compile(r"[0-9]{3}")
RE_DATA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
RE_HORA = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")

STATUS_VALIDOS = {s.value for s in StatusViagem}
MOTIVOS_VALIDOS = {m.value for m in MotivoNaoRealizacao}


class ErroImportacao(Exception):
    """Arquivo com problemas. `erros` lista cada problema com o número da linha."""

    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__(f"{len(erros)} problema(s) encontrado(s); nada foi gravado")


@dataclass(frozen=True)
class RegistroViagem:
    id_viagem: str
    empresa_codigo: str
    empresa_nome: str
    linha_codigo: str
    linha_descricao: str
    data_viagem: date
    horario_programado: time
    veiculo: str
    status: str
    motivo_nao_realizacao: str | None


@dataclass(frozen=True)
class ResultadoImportacao:
    lidos: int
    inseridos: int
    existentes: int
    empresas_novas: int
    linhas_novas: int


def formatar_id_viagem(numero: int) -> str:
    """181 -> 'VG0181'; 10000 -> 'VG10000' (completa com zeros, nunca corta)."""
    return f"VG{numero:04d}"


def proximo_id_viagem(db: Session) -> str:
    """Mostra qual será o próximo id_viagem, sem consumir a sequence."""
    numero = db.scalar(
        text("SELECT CASE WHEN is_called THEN last_value + 1 ELSE last_value END FROM viagem_codigo_seq")
    )
    return formatar_id_viagem(numero)


# --------------------------------------------------------------------------- leitura


def _validar_linha(numero: int, bruto: dict, erros: list[str]) -> RegistroViagem | None:
    """Valida uma linha do CSV. Devolve o registro ou None (registrando os erros)."""
    v = {coluna: (bruto.get(coluna) or "").strip() for coluna in COLUNAS}
    problemas = []

    if not RE_ID_VIAGEM.fullmatch(v["id_viagem"]):
        problemas.append(f"id_viagem inválido ({v['id_viagem']!r})")
    if not RE_EMPRESA.fullmatch(v["empresa_codigo"]):
        problemas.append(f"empresa_codigo deve ter 3 dígitos ({v['empresa_codigo']!r})")
    for campo, limite in TAMANHO_MAXIMO.items():
        if not v[campo]:
            problemas.append(f"{campo} é obrigatório")
        elif len(v[campo]) > limite:
            problemas.append(f"{campo} excede {limite} caracteres")

    data_viagem = None
    if RE_DATA.fullmatch(v["data_viagem"]):
        try:
            data_viagem = date.fromisoformat(v["data_viagem"])
        except ValueError:
            pass
    if data_viagem is None:
        problemas.append(f"data_viagem inválida, use AAAA-MM-DD ({v['data_viagem']!r})")

    horario = None
    if RE_HORA.fullmatch(v["horario_programado"]):
        horario = time.fromisoformat(v["horario_programado"])
    else:
        problemas.append(f"horario_programado inválido, use HH:MM ({v['horario_programado']!r})")

    status = v["status"]
    motivo = v["motivo_nao_realizacao"] or None
    if status not in STATUS_VALIDOS:
        problemas.append(f"status inválido ({status!r})")
    if motivo is not None and motivo not in MOTIVOS_VALIDOS:
        problemas.append(f"motivo_nao_realizacao inválido ({motivo!r})")
    if status == StatusViagem.REALIZADA and motivo is not None:
        problemas.append("viagem REALIZADA não pode ter motivo")
    if status == StatusViagem.NAO_REALIZADA and motivo is None:
        problemas.append("viagem NAO_REALIZADA exige motivo")

    if problemas:
        erros.append(f"linha {numero}: " + "; ".join(problemas))
        return None

    return RegistroViagem(
        id_viagem=v["id_viagem"],
        empresa_codigo=v["empresa_codigo"],
        empresa_nome=v["empresa_nome"],
        linha_codigo=v["linha_codigo"],
        linha_descricao=v["linha_descricao"],
        data_viagem=data_viagem,
        horario_programado=horario,
        veiculo=v["veiculo"],
        status=status,
        motivo_nao_realizacao=motivo,
    )


def ler_csv(caminho: Path = CAMINHO_PADRAO) -> list[RegistroViagem]:
    """Lê e valida o arquivo inteiro. Levanta ErroImportacao se houver qualquer problema."""
    erros: list[str] = []
    registros: list[RegistroViagem] = []
    ids_vistos: dict[str, int] = {}
    nome_da_empresa: dict[str, str] = {}
    descricao_da_linha: dict[tuple[str, str], str] = {}

    try:
        # utf-8-sig remove o BOM do início do arquivo; newline="" é exigido pelo módulo csv.
        with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
            leitor = csv.DictReader(arquivo, delimiter=";")
            if leitor.fieldnames != COLUNAS:
                raise ErroImportacao([f"cabeçalho inesperado: {leitor.fieldnames}"])

            for numero, bruto in enumerate(leitor, start=2):  # linha 1 é o cabeçalho
                if None in bruto:
                    erros.append(f"linha {numero}: colunas a mais")
                    continue
                registro = _validar_linha(numero, bruto, erros)
                if registro is None:
                    continue

                # Consistência entre linhas do próprio arquivo.
                if registro.id_viagem in ids_vistos:
                    erros.append(
                        f"linha {numero}: id_viagem {registro.id_viagem} repetido "
                        f"(já aparece na linha {ids_vistos[registro.id_viagem]})"
                    )
                    continue
                ids_vistos[registro.id_viagem] = numero

                nome = nome_da_empresa.setdefault(registro.empresa_codigo, registro.empresa_nome)
                if nome != registro.empresa_nome:
                    erros.append(f"linha {numero}: empresa {registro.empresa_codigo} com nomes diferentes")
                chave_linha = (registro.empresa_codigo, registro.linha_codigo)
                descricao = descricao_da_linha.setdefault(chave_linha, registro.linha_descricao)
                if descricao != registro.linha_descricao:
                    erros.append(f"linha {numero}: linha {registro.linha_codigo} com descrições diferentes")

                registros.append(registro)
    except FileNotFoundError:
        raise ErroImportacao([f"arquivo não encontrado: {caminho}"]) from None
    except UnicodeDecodeError:
        raise ErroImportacao(["o arquivo não está em UTF-8"]) from None

    if erros:
        raise ErroImportacao(erros)
    if not registros:
        raise ErroImportacao(["o arquivo não tem registros"])
    return registros


# --------------------------------------------------------------------------- gravação


def _ajustar_sequence(db: Session) -> None:
    """Posiciona viagem_codigo_seq após o maior id_viagem, sem nunca voltar atrás.

    GREATEST garante que um número já entregue (ex.: VG0181 criada e depois excluída)
    não seja reutilizado após uma reimportação.
    """
    db.execute(
        text(
            """
            SELECT setval('viagem_codigo_seq', GREATEST(
                (SELECT COALESCE(MAX(substring(id_viagem FROM 3)::bigint), 0) FROM viagem) + 1,
                (SELECT CASE WHEN is_called THEN last_value + 1 ELSE last_value END FROM viagem_codigo_seq)
            ), false)
            """
        )
    )


def importar(db: Session, registros: list[RegistroViagem]) -> ResultadoImportacao:
    """Grava empresas, linhas e viagens numa única transação (tudo ou nada)."""
    empresa_t, linha_t, viagem_t = Empresa.__table__, Linha.__table__, Viagem.__table__
    try:
        # 1. Empresas (chave natural: codigo)
        empresas = {r.empresa_codigo: r.empresa_nome for r in registros}
        empresas_novas = db.execute(
            insert(empresa_t)
            .values([{"codigo": c, "nome": n} for c, n in empresas.items()])
            .on_conflict_do_nothing(index_elements=["codigo"])
            .returning(empresa_t.c.id)
        ).all()
        id_empresa = dict(
            db.execute(select(empresa_t.c.codigo, empresa_t.c.id).where(empresa_t.c.codigo.in_(empresas))).all()
        )

        # 2. Linhas (chave natural: empresa + codigo)
        linhas = {(r.empresa_codigo, r.linha_codigo): r.linha_descricao for r in registros}
        linhas_novas = db.execute(
            insert(linha_t)
            .values(
                [
                    {"empresa_id": id_empresa[emp], "codigo": cod, "descricao": desc}
                    for (emp, cod), desc in linhas.items()
                ]
            )
            .on_conflict_do_nothing(index_elements=["empresa_id", "codigo"])
            .returning(linha_t.c.id)
        ).all()
        id_linha = {
            (codigo_empresa, codigo_linha): id_
            for codigo_empresa, codigo_linha, id_ in db.execute(
                select(empresa_t.c.codigo, linha_t.c.codigo, linha_t.c.id).join(
                    empresa_t, linha_t.c.empresa_id == empresa_t.c.id
                )
            )
        }

        # 3. Viagens (chave natural: id_viagem) — existentes são ignoradas
        inseridas = db.execute(
            insert(viagem_t)
            .values(
                [
                    {
                        "id_viagem": r.id_viagem,
                        "linha_id": id_linha[(r.empresa_codigo, r.linha_codigo)],
                        "data_viagem": r.data_viagem,
                        "horario_programado": r.horario_programado,
                        "veiculo": r.veiculo,
                        "status": r.status,
                        "motivo_nao_realizacao": r.motivo_nao_realizacao,
                    }
                    for r in registros
                ]
            )
            .on_conflict_do_nothing(index_elements=["id_viagem"])
            .returning(viagem_t.c.id_viagem)
        ).all()

        _ajustar_sequence(db)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return ResultadoImportacao(
        lidos=len(registros),
        inseridos=len(inseridas),
        existentes=len(registros) - len(inseridas),
        empresas_novas=len(empresas_novas),
        linhas_novas=len(linhas_novas),
    )


def resetar(db: Session, registros: list[RegistroViagem]) -> ResultadoImportacao:
    """Apaga todos os dados e recarrega o arquivo, na MESMA transação.

    Se a recarga falhar, o TRUNCATE também é desfeito: a base nunca fica vazia por erro.
    """
    db.execute(text("TRUNCATE viagem, linha, empresa RESTART IDENTITY"))
    db.execute(text("ALTER SEQUENCE viagem_codigo_seq RESTART"))
    return importar(db, registros)
