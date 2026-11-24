import logging

from fastapi import FastAPI

from app.routers import empresas, health, viagens

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Controle de Viagens",
    version="0.1.0",
    description="API para cadastro de viagens programadas e indicadores operacionais.",
)

app.include_router(health.router)
app.include_router(empresas.router)
app.include_router(viagens.router)
