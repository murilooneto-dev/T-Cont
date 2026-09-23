from sqlalchemy.orm import Session

from app.application.repositories import ExtracaoRepository
from app.domain.entities import Extracao
from app.domain.enums import TipoDocumento
from app.infrastructure.db.models import ExtracaoModel


def _to_entity(model: ExtracaoModel) -> Extracao:
    return Extracao(
        id=model.id,
        documento_id=model.documento_id,
        pagador_nome=model.pagador_nome,
        pagador_documento=model.pagador_documento,
        recebedor_nome=model.recebedor_nome,
        recebedor_documento=model.recebedor_documento,
        valor=model.valor,
        data_pagamento=model.data_pagamento,
        tipo_documento=TipoDocumento(model.tipo_documento),
        banco_nome=model.banco_nome,
        created_at=model.created_at,
    )


class SqlAlchemyExtracaoRepository(ExtracaoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, extracao: Extracao) -> Extracao:
        model = ExtracaoModel(
            documento_id=extracao.documento_id,
            pagador_nome=extracao.pagador_nome,
            pagador_documento=extracao.pagador_documento,
            recebedor_nome=extracao.recebedor_nome,
            recebedor_documento=extracao.recebedor_documento,
            valor=extracao.valor,
            data_pagamento=extracao.data_pagamento,
            tipo_documento=extracao.tipo_documento.value,
            banco_nome=extracao.banco_nome,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_documento_id(self, documento_id: int) -> Extracao | None:
        model = (
            self._session.query(ExtracaoModel)
            .filter_by(documento_id=documento_id)
            .first()
        )
        return _to_entity(model) if model else None

    def deletar_por_documento_id(self, documento_id: int) -> None:
        self._session.query(ExtracaoModel).filter_by(documento_id=documento_id).delete()
        self._session.flush()
