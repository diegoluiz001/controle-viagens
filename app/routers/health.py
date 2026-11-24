import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Verifica se a aplicação está no ar e se o banco responde."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Detalhes só no log do servidor; a resposta pública não expõe host nem credenciais.
        logger.exception("Falha ao acessar o banco de dados")
        return JSONResponse(status_code=503, content={"status": "erro", "database": "indisponivel"})
    return {"status": "ok", "database": "ok"}
