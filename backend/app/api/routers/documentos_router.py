from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage
from app.api.schemas.documento_schemas import (
    DocumentoOut,
    DocumentoResultadoOut,
    OcrResultadoOut,
    UploadItemOut,
)
from app.application.dto import ArquivoUploadDTO
from app.application.use_cases.documento_use_cases import (
    ListarDocumentosUseCase,
    ObterResultadoUseCase,
    UploadarDocumentosUseCase,
)
from app.core.exceptions import DocumentoNaoEncontrado, EmpresaNaoEncontrada
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
    SqlAlchemyOcrResultadoRepository,
)
from app.infrastructure.storage.file_storage import LocalFileStorageService

router = APIRouter(tags=["documentos"])


@router.post(
    "/empresas/{empresa_id}/documentos", response_model=list[UploadItemOut], status_code=201
)
async def upload_documentos(
    empresa_id: int,
    arquivos: list[UploadFile],
    db: Session = Depends(get_db),
    storage: LocalFileStorageService = Depends(get_storage),
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    empresa_repo = SqlAlchemyEmpresaRepository(db)
    dtos = [
        ArquivoUploadDTO(nome_original=arquivo.filename or "arquivo", conteudo=await arquivo.read())
        for arquivo in arquivos
    ]
    try:
        return UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
            empresa_id, dtos
        )
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/empresas/{empresa_id}/documentos", response_model=list[DocumentoOut])
def listar_documentos(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyDocumentoRepository(db)
    documentos = ListarDocumentosUseCase(repo).executar(empresa_id)
    return [DocumentoOut.model_validate(d, from_attributes=True) for d in documentos]


@router.get("/documentos/{documento_id}/resultado", response_model=DocumentoResultadoOut)
def obter_resultado(documento_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    resultado_repo = SqlAlchemyOcrResultadoRepository(db)
    try:
        documento, resultado = ObterResultadoUseCase(documento_repo, resultado_repo).executar(
            documento_id
        )
    except DocumentoNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    resultado_out = (
        OcrResultadoOut(
            texto_extraido=resultado.texto_extraido,
            metodo=resultado.metodo,
            tempo_processamento_ms=resultado.tempo_processamento_ms,
        )
        if resultado
        else None
    )
    return DocumentoResultadoOut(documento=documento, resultado=resultado_out)
