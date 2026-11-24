"""Indicadores do dashboard, com os mesmos filtros de GET /api/viagens."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import FiltroViagens, Indicadores
from app.services import indicadores as servico

router = APIRouter(prefix="/api/indicadores", tags=["indicadores"])


@router.get("", response_model=Indicadores, summary="Indicadores operacionais (mesmos filtros da listagem)")
def consultar_indicadores(
    db: Annotated[Session, Depends(get_db)],
    filtro: Annotated[FiltroViagens, Query()],
):
    return servico.calcular(db, filtro)
