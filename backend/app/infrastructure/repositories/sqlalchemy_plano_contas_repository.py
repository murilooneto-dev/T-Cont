from sqlalchemy.orm import Session

from app.application.repositories import PlanoContasRepository
from app.domain.entities import PlanoContas
from app.infrastructure.db.models import PlanoContasModel


def _to_entity(model: PlanoContasModel) -> PlanoContas:
    return PlanoContas(
        id=model.id,
        empresa_id=model.empresa_id,
        nome=model.nome,
        versao=model.versao,
        ativo=model.ativo,
        created_at=model.created_at,
    )


class SqlAlchemyPlanoContasRepository(PlanoContasRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, plano: PlanoContas) -> PlanoContas:
        model = PlanoContasModel(
            empresa_id=plano.empresa_id, nome=plano.nome, versao=plano.versao, ativo=plano.ativo
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, plano_id: int) -> PlanoContas | None:
        model = self._session.get(PlanoContasModel, plano_id)
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]:
        models = self._session.query(PlanoContasModel).filter_by(empresa_id=empresa_id).all()
        return [_to_entity(m) for m in models]
