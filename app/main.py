from fastapi import FastAPI

from app import models  # noqa: F401  (carregar os modelos registra as tabelas)
from app.database import Base, engine
from app.routers import analises, auth, reembolsos, usuarios

# Cria as tabelas no banco, caso ainda não existam
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NexusCorp - Gestão de Reembolsos",
    description="API para gestão de reembolsos corporativos.",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(reembolsos.router)
app.include_router(analises.router)