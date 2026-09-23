from sqlalchemy.orm import Session

from app.application.repositories import AprendizadoRepository
from app.domain.entities import Aprendizado
from app.domain.enums import OrigemClassificacao
from app.infrastructure.db.models import AprendizadoModel


def _to_entity(model: AprendizadoModel) -> Aprendizado:
    return Aprendizado(
        id=model.id,
        empresa_id=model.empresa_id,
        documento_id=model.documento_id,
        conta_anterior_id=model.conta_anterior_id,
        origem_anterior=(
            OrigemClassificacao(model.origem_anterior) if model.origem_anterior else None
        ),
        conta_corrigida_id=model.conta_corrigida_id,
        regra_id=model.regra_id,
        created_at=model.created_at,
    )


class SqlAlchemyAprendizadoRepository(AprendizadoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, aprendizado: Aprendizado) -> Aprendizado:
        model = AprendizadoModel(
            empresa_id=aprendizado.empresa_id,
            documento_id=aprendizado.documento_id,
            conta_anterior_id=aprendizado.conta_anterior_id,
            origem_anterior=(
                aprendizado.origem_anterior.value if aprendizado.origem_anterior else None
            ),
            conta_corrigida_id=aprendizado.conta_corrigida_id,
            regra_id=aprendizado.regra_id,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def listar_por_empresa(self, empresa_id: int) -> list[Aprendizado]:
        models = (
            self._session.query(AprendizadoModel).filter_by(empresa_id=empresa_id).all()
        )
        return [_to_entity(m) for m in models]

    def deletar_por_documento_id(self, documento_id: int) -> None:
        self._session.query(AprendizadoModel).filter_by(documento_id=documento_id).delete()
        self._session.flush()
