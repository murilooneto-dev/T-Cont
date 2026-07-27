from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import MetodoOcr, StatusDocumento


class DocumentoOut(BaseModel):
    id: int
    empresa_id: int
    nome_arquivo: str
    nome_exibicao: str
    extensao: str
    tamanho_bytes: int
    status: StatusDocumento
    mensagem_erro: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadItemOut(BaseModel):
    nome_original: str
    documento: DocumentoOut | None
    erro: str | None


class OcrResultadoOut(BaseModel):
    texto_extraido: str
    metodo: MetodoOcr
    tempo_processamento_ms: int


class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
