from datetime import datetime

from pydantic import BaseModel


class EmpresaCreateIn(BaseModel):
    razao_social: str
    nome_fantasia: str | None = None
    cnpj: str


class EmpresaUpdateIn(BaseModel):
    razao_social: str
    nome_fantasia: str | None = None
    ativo: bool


class EmpresaOut(BaseModel):
    id: int
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    ativo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
