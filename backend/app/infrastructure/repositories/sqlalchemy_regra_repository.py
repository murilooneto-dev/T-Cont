from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.repositories import RegraRepository
from app.core.exceptions import RegraEmUso
from app.domain.entities import Regra
from app.domain.enums import LadoRegra, TipoDocumento
from app.infrastructure.db.models import RegraModel


def _to_entity(model: RegraModel) -> Regra:
    return Regra(
        id=model.id,
        empresa_id=model.empresa_id,
        conta_id=model.conta_id,
        lado_alvo=LadoRegra(model.lado_alvo) if model.lado_alvo else None,
        documento_fiscal=model.documento_fiscal,
        tipo_documento=TipoDocumento(model.tipo_documento) if model.tipo_documento else None,
        valor_min=model.valor_min,
        valor_max=model.valor_max,
        palavra_chave_nome=model.palavra_chave_nome,
        ativo=model.ativo,
        created_at=model.created_at,
    )


class SqlAlchemyRegraRepository(RegraRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, regra: Regra) -> Regra:
        model = RegraModel(
            empresa_id=regra.empresa_id,
            conta_id=regra.conta_id,
            lado_alvo=regra.lado_alvo.value if regra.lado_alvo else None,
            documento_fiscal=regra.documento_fiscal,
            tipo_documento=regra.tipo_documento.value if regra.tipo_documento else None,
            valor_min=regra.valor_min,
            valor_max=regra.valor_max,
            palavra_chave_nome=regra.palavra_chave_nome,
            ativo=regra.ativo,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, regra_id: int) -> Regra | None:
        model = self._session.get(RegraModel, regra_id)
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[Regra]:
        models = self._session.query(RegraModel).filter_by(empresa_id=empresa_id).all()
        return [_to_entity(m) for m in models]

    def atualizar(self, regra: Regra) -> Regra:
        model = self._session.get(RegraModel, regra.id)
        model.conta_id = regra.conta_id
        model.lado_alvo = regra.lado_alvo.value if regra.lado_alvo else None
        model.documento_fiscal = regra.documento_fiscal
        model.tipo_documento = regra.tipo_documento.value if regra.tipo_documento else None
        model.valor_min = regra.valor_min
        model.valor_max = regra.valor_max
        model.palavra_chave_nome = regra.palavra_chave_nome
        model.ativo = regra.ativo
        self._session.flush()
        return _to_entity(model)

    def deletar(self, regra_id: int) -> None:
        model = self._session.get(RegraModel, regra_id)
        if model is not None:
            self._session.delete(model)
            try:
                self._session.flush()
            except IntegrityError as exc:
                self._session.rollback()
                raise RegraEmUso(regra_id) from exc
