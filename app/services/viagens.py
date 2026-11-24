"""Regras de acesso a dados das viagens: filtros, consulta, criação, edição e exclusão.

As rotas (app/routers) só traduzem HTTP <-> estas funções; a lógica fica aqui para
poder ser reutilizada (ex.: os indicadores usam o mesmo filtro da listagem).
"""
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Linha, Viagem, viagem_codigo_seq
from app.schemas import FiltroViagens, ViagemEntrada
from app.services.importacao import formatar_id_viagem


class LinhaNaoEncontrada(Exception):
    def __init__(self, linha_id: int):
        self.linha_id = linha_id
        super().__init__(f"linha {linha_id} não encontrada")


def condicoes_filtro(filtro: FiltroViagens) -> list[ColumnElement[bool]]:
    """Traduz o filtro em condições SQL (WHERE). Fonte única para listagem e indicadores."""
    condicoes: list[ColumnElement[bool]] = []
    if filtro.data_inicio is not None:
        condicoes.append(Viagem.data_viagem >= filtro.data_inicio)  # inclusivo
    if filtro.data_fim is not None:
        condicoes.append(Viagem.data_viagem <= filtro.data_fim)  # inclusivo
    if filtro.linha_id is not None:
        condicoes.append(Viagem.linha_id == filtro.linha_id)
    if filtro.empresa_id is not None:
        linhas_da_empresa = select(Linha.id).where(Linha.empresa_id == filtro.empresa_id)
        condicoes.append(Viagem.linha_id.in_(linhas_da_empresa))
    return condicoes


def _com_linha_e_empresa():
    """Carrega linha e empresa junto com a viagem (JOIN), evitando uma consulta por linha."""
    return joinedload(Viagem.linha).joinedload(Linha.empresa)


def listar(db: Session, filtro: FiltroViagens, pagina: int, por_pagina: int) -> tuple[int, list[Viagem]]:
    condicoes = condicoes_filtro(filtro)
    total = db.scalar(select(func.count()).select_from(Viagem).where(*condicoes))
    consulta = (
        select(Viagem)
        .options(_com_linha_e_empresa())
        .where(*condicoes)
        .order_by(Viagem.data_viagem, Viagem.horario_programado, Viagem.id_viagem)
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    )
    return total, list(db.scalars(consulta))


def buscar(db: Session, id_viagem: str) -> Viagem | None:
    consulta = select(Viagem).options(_com_linha_e_empresa()).where(Viagem.id_viagem == id_viagem)
    return db.scalar(consulta)


def _garantir_linha(db: Session, linha_id: int) -> None:
    if db.get(Linha, linha_id) is None:
        raise LinhaNaoEncontrada(linha_id)


def criar(db: Session, dados: ViagemEntrada) -> Viagem:
    _garantir_linha(db, dados.linha_id)
    # nextval é atômico: duas criações simultâneas nunca recebem o mesmo número,
    # e um número já entregue nunca é reutilizado (mesmo se a viagem for excluída).
    numero = db.scalar(select(viagem_codigo_seq.next_value()))
    viagem = Viagem(id_viagem=formatar_id_viagem(numero), **dados.model_dump())
    db.add(viagem)
    db.commit()
    return buscar(db, viagem.id_viagem)


def atualizar(db: Session, viagem: Viagem, dados: ViagemEntrada) -> Viagem:
    _garantir_linha(db, dados.linha_id)
    for campo, valor in dados.model_dump().items():
        setattr(viagem, campo, valor)
    db.commit()
    db.expire(viagem)  # relê updated_at (trigger) e a linha/empresa, caso a linha tenha mudado
    return buscar(db, viagem.id_viagem)


def excluir(db: Session, viagem: Viagem) -> None:
    db.delete(viagem)
    db.commit()
