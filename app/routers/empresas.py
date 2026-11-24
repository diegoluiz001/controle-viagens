"""Empresas e suas linhas: alimentam os filtros e o formulário da interface."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Empresa
from app.schemas import EmpresaSaida

router = APIRouter(prefix="/api/empresas", tags=["empresas"])


@router.get("", response_model=list[EmpresaSaida], summary="Listar empresas com suas linhas")
def listar_empresas(db: Annotated[Session, Depends(get_db)]):
    empresas = db.scalars(
        select(Empresa).options(selectinload(Empresa.linhas)).order_by(Empresa.codigo)
    ).all()
    for empresa in empresas:
        empresa.linhas.sort(key=lambda linha: linha.codigo)
    return empresas
