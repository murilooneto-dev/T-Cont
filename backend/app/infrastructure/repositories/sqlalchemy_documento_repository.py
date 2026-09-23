from sqlalchemy.orm import Session

from app.application.repositories import DocumentoRepository
from app.domain.entities import Documento
from app.domain.enums import StatusDocumento
from app.infrastructure.db.models import DocumentoModel


def _to_entity(model: DocumentoModel) -> Documento:
    return Documento(
        id=model.id,
        empresa_id=model.empresa_id,
        nome_arquivo=model.nome_arquivo,
        nome_exibicao=model.nome_exibicao,
        caminho_arquivo=model.caminho_arquivo,
        extensao=model.extensao,
        tamanho_bytes=model.tamanho_bytes,
        status=StatusDocumento(model.status),
        mensagem_erro=model.mensagem_erro,
        created_at=model.created_at,
        updated_at=model.updated_at,
        documento_origem_id=model.documento_origem_id,
    )


class SqlAlchemyDocumentoRepository(DocumentoRepository):
    def __init__(self, session: Session):
        self._session = session

    def criar(self, documento: Documento) -> Documento:
        model = DocumentoModel(
            empresa_id=documento.empresa_id,
            nome_arquivo=documento.nome_arquivo,
            nome_exibicao=documento.nome_exibicao,
            caminho_arquivo=documento.caminho_arquivo,
            extensao=documento.extensao,
            tamanho_bytes=documento.tamanho_bytes,
            status=documento.status.value,
            mensagem_erro=documento.mensagem_erro,
            documento_origem_id=documento.documento_origem_id,
        )
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def obter_por_id(self, documento_id: int) -> Documento | None:
        model = self._session.get(DocumentoModel, documento_id)
        return _to_entity(model) if model else None

    def listar_por_empresa(self, empresa_id: int) -> list[Documento]:
        models = self._session.query(DocumentoModel).filter_by(empresa_id=empresa_id).all()
        return [_to_entity(m) for m in models]

    def listar_pendentes_por_empresa(self, empresa_id: int) -> list[Documento]:
        models = (
            self._session.query(DocumentoModel)
            .filter_by(empresa_id=empresa_id, status=StatusDocumento.PENDENTE.value)
            .order_by(DocumentoModel.id)
            .all()
        )
        return [_to_entity(m) for m in models]

    def atualizar(self, documento: Documento) -> Documento:
        model = self._session.get(DocumentoModel, documento.id)
        model.status = documento.status.value
        model.mensagem_erro = documento.mensagem_erro
        model.nome_exibicao = documento.nome_exibicao
        self._session.flush()
        return _to_entity(model)

    def deletar(self, documento_id: int) -> None:
        model = self._session.get(DocumentoModel, documento_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()
