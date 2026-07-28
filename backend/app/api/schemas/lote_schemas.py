from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import StatusLote


class LoteOut(BaseModel):
    id: int
    empresa_id: int
    total_documentos: int
    documentos_processados: int
    status: StatusLote
    created_at: datetime
    concluido_em: datetime | None

    model_config = {"from_attributes": True}
