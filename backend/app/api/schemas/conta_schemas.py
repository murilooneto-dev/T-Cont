from pydantic import BaseModel

from app.domain.enums import NaturezaConta


class ContaCreateIn(BaseModel):
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None


class ContaUpdateIn(BaseModel):
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None


class ContaOut(BaseModel):
    id: int
    plano_conta_id: int
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None

    model_config = {"from_attributes": True}
