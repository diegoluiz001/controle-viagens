"""Rotas REST de viagens: listar, consultar, criar, editar e excluir."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Viagem
from app.schemas import FiltroViagens, ListaViagens, ViagemEntrada, ViagemSaida
from app.services import viagens as servico

router = APIRouter(prefix="/api/viagens", tags=["viagens"])

Db = Annotated[Session, Depends(get_db)]


def _obter_ou_404(db: Session, id_viagem: str) -> Viagem:
    viagem = servico.buscar(db, id_viagem)
    if viagem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"viagem {id_viagem} não encontrada")
    return viagem


def _erro_linha(erro: servico.LinhaNaoEncontrada) -> HTTPException:
    # Mesmo formato dos erros de validação do FastAPI, para a interface tratar tudo igual.
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"loc": ["body", "linha_id"], "msg": str(erro), "type": "linha_inexistente"}],
    )


@router.get("", response_model=ListaViagens, summary="Listar viagens (com filtros e paginação)")
def listar_viagens(
    db: Db,
    filtro: Annotated[FiltroViagens, Query()],
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=500)] = 50,
):
    total, viagens = servico.listar(db, filtro, pagina, por_pagina)
    return ListaViagens(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        itens=[ViagemSaida.de_modelo(v) for v in viagens],
    )


@router.get("/{id_viagem}", response_model=ViagemSaida, summary="Consultar uma viagem")
def consultar_viagem(id_viagem: str, db: Db):
    return ViagemSaida.de_modelo(_obter_ou_404(db, id_viagem))


@router.post(
    "",
    response_model=ViagemSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Criar viagem (o id_viagem é gerado pelo servidor)",
)
def criar_viagem(dados: ViagemEntrada, db: Db):
    try:
        viagem = servico.criar(db, dados)
    except servico.LinhaNaoEncontrada as erro:
        raise _erro_linha(erro) from None
    return ViagemSaida.de_modelo(viagem)


@router.put("/{id_viagem}", response_model=ViagemSaida, summary="Editar viagem (todos os campos)")
def editar_viagem(id_viagem: str, dados: ViagemEntrada, db: Db):
    viagem = _obter_ou_404(db, id_viagem)
    try:
        viagem = servico.atualizar(db, viagem, dados)
    except servico.LinhaNaoEncontrada as erro:
        raise _erro_linha(erro) from None
    return ViagemSaida.de_modelo(viagem)


@router.delete("/{id_viagem}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir viagem")
def excluir_viagem(id_viagem: str, db: Db):
    servico.excluir(db, _obter_ou_404(db, id_viagem))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
