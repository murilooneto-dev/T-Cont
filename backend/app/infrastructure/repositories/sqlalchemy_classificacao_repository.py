from sqlalchemy.orm import Session

from app.application.repositories import ClassificacaoRepository
from app.domain.entities import Classificacao
from app.domain.enums import OrigemClassificacao
from app.infrastructure.db.models import ClassificacaoModel


def _to_entity(model: ClassificacaoModel) -> Classificacao:
    return Classificacao(
        id=model.id,
        empresa_id=model.empresa_id,
        documento_id=model.documento_id,
        conta_id=model.conta_id,
        origem=OrigemClassificacao(model.origem),
        regra_id=model.regra_id,
        score_similaridade=model.score_similaridade,
        created_at=model.created_at,
    )


class SqlAlchemyClassificacaoRepository(ClassificacaoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, classificacao: Classificacao) -> Classificacao:
        model = ClassificacaoModel(
            empresa_id=classificacao.empresa_id,
            documento_id=classificacao.documento_id,
            conta_id=classificacao.conta_id,
            origem=classificacao.origem.value,
            regra_id=classificacao.regra_id,
            score_similaridade=classificacao.score_similaridade,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_documento_id(self, documento_id: int) -> Classificacao | None:
        model = (
            self._session.query(ClassificacaoModel)
            .filter_by(documento_id=documento_id)
            .first()
        )
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[Classificacao]:
        models = (
            self._session.query(ClassificacaoModel).filter_by(empresa_id=empresa_id).all()
        )
        return [_to_entity(m) for m in models]

    def atualizar(self, classificacao: Classificacao) -> Classificacao:
        model = self._session.get(ClassificacaoModel, classificacao.id)
        model.conta_id = classificacao.conta_id
        model.origem = classificacao.origem.value
        model.regra_id = classificacao.regra_id
        model.score_similaridade = classificacao.score_similaridade
        self._session.flush()
        return _to_entity(model)
