from pydantic import BaseModel


class PlanoContasCreateIn(BaseModel):
    nome: str


class PlanoContasOut(BaseModel):
    id: int
    empresa_id: int
    nome: str
    versao: int
    ativo: bool

    model_config = {"from_attributes": True}
