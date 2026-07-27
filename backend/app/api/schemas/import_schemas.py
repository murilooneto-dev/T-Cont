from pydantic import BaseModel


class LinhaPreviewOut(BaseModel):
    codigo: str
    descricao: str
    natureza: str | None
    conta_analitica: bool | None
    conta_pai: str | None


class ImportPreviewOut(BaseModel):
    mapeamento: dict[str, int | None]
    linhas: list[LinhaPreviewOut]
