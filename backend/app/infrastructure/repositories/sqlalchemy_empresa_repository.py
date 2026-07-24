from sqlalchemy.orm import Session

from app.application.repositories import EmpresaRepository
from app.domain.entities import Empresa
from app.infrastructure.db.models import EmpresaModel


def _to_entity(model: EmpresaModel) -> Empresa:
    return Empresa(
        id=model.id,
        razao_social=model.razao_social,
        nome_fantasia=model.nome_fantasia,
        cnpj=model.cnpj,
        ativo=model.ativo,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyEmpresaRepository(EmpresaRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, empresa: Empresa) -> Empresa:
        model = EmpresaModel(
            razao_social=empresa.razao_social,
            nome_fantasia=empresa.nome_fantasia,
            cnpj=empresa.cnpj,
            ativo=empresa.ativo,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, empresa_id: int) -> Empresa | None:
        model = self._session.get(EmpresaModel, empresa_id)
        return _to_entity(model) if model else None

    def obter_por_cnpj(self, cnpj: str) -> Empresa | None:
        model = self._session.query(EmpresaModel).filter_by(cnpj=cnpj).first()
        return _to_entity(model) if model else None

    def listar(self) -> list[Empresa]:
        return [_to_entity(m) for m in self._session.query(EmpresaModel).all()]

    def atualizar(self, empresa: Empresa) -> Empresa:
        model = self._session.get(EmpresaModel, empresa.id)
        model.razao_social = empresa.razao_social
        model.nome_fantasia = empresa.nome_fantasia
        model.ativo = empresa.ativo
        self._session.flush()
        return _to_entity(model)
