"""Indicadores do dashboard: uma única consulta SQL com os mesmos filtros da listagem."""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import MotivoNaoRealizacao, StatusViagem
from app.models import Viagem
from app.schemas import FiltroViagens, Indicadores
from app.services.viagens import condicoes_filtro


def calcular_percentual(realizadas: int, programadas: int) -> float | None:
    """(realizadas / programadas) x 100 com 2 casas, arredondando o meio para cima.

    Sem viagens programadas não há percentual a calcular: devolve None ('Sem dados'),
    em vez de dividir por zero.
    """
    if programadas == 0:
        return None
    valor = Decimal(realizadas) * 100 / Decimal(programadas)
    return float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calcular(db: Session, filtro: FiltroViagens) -> Indicadores:
    # COUNT(*) FILTER (WHERE ...): o banco conta tudo de uma vez, sem trazer as viagens.
    # As colunas de motivo saem do Enum: um motivo novo entra aqui automaticamente.
    colunas = {
        "programadas": func.count(),
        "realizadas": func.count().filter(Viagem.status == StatusViagem.REALIZADA),
        "nao_realizadas": func.count().filter(Viagem.status == StatusViagem.NAO_REALIZADA),
        **{
            motivo.value: func.count().filter(Viagem.motivo_nao_realizacao == motivo)
            for motivo in MotivoNaoRealizacao
        },
    }
    consulta = select(*(coluna.label(nome) for nome, coluna in colunas.items())).where(
        *condicoes_filtro(filtro)
    )
    linha = db.execute(consulta).mappings().one()

    return Indicadores(
        programadas=linha["programadas"],
        realizadas=linha["realizadas"],
        nao_realizadas=linha["nao_realizadas"],
        percentual_cumprimento=calcular_percentual(linha["realizadas"], linha["programadas"]),
        sem_dados=linha["programadas"] == 0,
        motivos={motivo: linha[motivo.value] for motivo in MotivoNaoRealizacao},
    )
