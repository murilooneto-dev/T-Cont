from sqlalchemy.orm import Session

from app.application.repositories import OcrResultadoRepository
from app.domain.entities import OcrResultado
from app.domain.enums import MetodoOcr
from app.infrastructure.db.models import OcrResultadoModel


def _to_entity(model: OcrResultadoModel) -> OcrResultado:
    return OcrResultado(
        id=model.id,
        documento_id=model.documento_id,
        texto_extraido=model.texto_extraido,
        metodo=MetodoOcr(model.metodo),
        tempo_processamento_ms=model.tempo_processamento_ms,
        created_at=model.created_at,
    )


class SqlAlchemyOcrResultadoRepository(OcrResultadoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, resultado: OcrResultado) -> OcrResultado:
        model = OcrResultadoModel(
            documento_id=resultado.documento_id,
            texto_extraido=resultado.texto_extraido,
            metodo=resultado.metodo.value,
            tempo_processamento_ms=resultado.tempo_processamento_ms,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_documento_id(self, documento_id: int) -> OcrResultado | None:
        model = (
            self._session.query(OcrResultadoModel)
            .filter_by(documento_id=documento_id)
            .first()
        )
        return _to_entity(model) if model else None
