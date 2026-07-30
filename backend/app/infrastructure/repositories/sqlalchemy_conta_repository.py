from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.repositories import ContaRepository
from app.core.exceptions import ContaEmUso
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta
from app.infrastructure.db.models import ContaModel


def _to_entity(model: ContaModel) -> Conta:
    return Conta(
        id=model.id,
        plano_conta_id=model.plano_conta_id,
        codigo=model.codigo,
        descricao=model.descricao,
        natureza=NaturezaConta(model.natureza),
        conta_analitica=model.conta_analitica,
        conta_pai_id=model.conta_pai_id,
    )


class SqlAlchemyContaRepository(ContaRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, conta: Conta) -> Conta:
        model = ContaModel(
            plano_conta_id=conta.plano_conta_id,
            codigo=conta.codigo,
            descricao=conta.descricao,
            natureza=conta.natureza.value,
            conta_analitica=conta.conta_analitica,
            conta_pai_id=conta.conta_pai_id,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]:
        return [self.criar(c) for c in contas]

    def obter_por_id(self, conta_id: int) -> Conta | None:
        model = self._session.get(ContaModel, conta_id)
        return _to_entity(model) if model else None

    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]:
        models = self._session.query(ContaModel).filter_by(plano_conta_id=plano_conta_id).all()
        return [_to_entity(m) for m in models]

    def atualizar(self, conta: Conta) -> Conta:
        model = self._session.get(ContaModel, conta.id)
        model.codigo = conta.codigo
        model.descricao = conta.descricao
        model.natureza = conta.natureza.value
        model.conta_analitica = conta.conta_analitica
        model.conta_pai_id = conta.conta_pai_id
        self._session.flush()
        return _to_entity(model)

    def deletar(self, conta_id: int) -> None:
        model = self._session.get(ContaModel, conta_id)
        if model is not None:
            self._session.delete(model)
            try:
                self._session.flush()
            except IntegrityError as exc:
                self._session.rollback()
                raise ContaEmUso(conta_id) from exc
