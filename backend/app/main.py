from fastapi import FastAPI

from app.api.routers.empresas_router import router as empresas_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(empresas_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
