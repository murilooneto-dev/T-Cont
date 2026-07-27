from sqlalchemy.orm import Session

from app.application.repositories import LoteProcessamentoRepository
from app.domain.entities import LoteProcessamento
from app.domain.enums import StatusLote
from app.infrastructure.db.models import LoteProcessamentoModel


def _to_entity(model: LoteProcessamentoModel) -> LoteProcessamento:
    return LoteProcessamento(
        id=model.id,
        empresa_id=model.empresa_id,
        total_documentos=model.total_documentos,
        documentos_processados=model.documentos_processados,
        status=StatusLote(model.status),
        created_at=model.created_at,
        concluido_em=model.concluido_em,
    )


class SqlAlchemyLoteProcessamentoRepository(LoteProcessamentoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, lote: LoteProcessamento) -> LoteProcessamento:
        model = LoteProcessamentoModel(
            empresa_id=lote.empresa_id,
            total_documentos=lote.total_documentos,
            documentos_processados=lote.documentos_processados,
            status=lote.status.value,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, lote_id: int) -> LoteProcessamento | None:
        model = self._session.get(LoteProcessamentoModel, lote_id)
        return _to_entity(model) if model else None

    def atualizar(self, lote: LoteProcessamento) -> LoteProcessamento:
        model = self._session.get(LoteProcessamentoModel, lote.id)
        model.documentos_processados = lote.documentos_processados
        model.status = lote.status.value
        model.concluido_em = lote.concluido_em
        self._session.flush()
        return _to_entity(model)
