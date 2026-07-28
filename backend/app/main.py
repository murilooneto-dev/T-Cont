from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.contas_router import router as contas_router
from app.api.routers.documentos_router import router as documentos_router
from app.api.routers.empresas_router import router as empresas_router
from app.api.routers.lotes_router import router as lotes_router
from app.api.routers.planos_contas_router import router as planos_contas_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(empresas_router)
app.include_router(planos_contas_router)
app.include_router(contas_router)
app.include_router(documentos_router)
app.include_router(lotes_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
