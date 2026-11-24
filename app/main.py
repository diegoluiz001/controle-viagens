import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import empresas, health, indicadores, viagens

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PASTA_ESTATICA = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Controle de Viagens",
    version="0.1.0",
    description="API para cadastro de viagens programadas e indicadores operacionais.",
)

app.include_router(health.router)
app.include_router(empresas.router)
app.include_router(viagens.router)
app.include_router(indicadores.router)

# Interface web: servida pela própria aplicação, no mesmo endereço da API (sem CORS).
app.mount("/static", StaticFiles(directory=PASTA_ESTATICA), name="static")


@app.get("/", include_in_schema=False)
def interface():
    return FileResponse(PASTA_ESTATICA / "index.html")
