from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.lote_schemas import LoteOut
from app.application.use_cases.lote_use_cases import (
    CancelarLoteUseCase,
    IniciarProcessamentoUseCase,
    ObterStatusLoteUseCase,
)
from app.core.config import settings
from app.core.exceptions import (
    EmpresaNaoEncontrada,
    LoteNaoEncontrado,
    LoteNaoPodeSerCancelado,
    NenhumDocumentoPendente,
)
from app.infrastructure.workers.lote_worker import processar_lote_em_background
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
    SqlAlchemyLoteProcessamentoRepository,
)

router = APIRouter(tags=["lotes"])


@router.post(
    "/empresas/{empresa_id}/documentos/processar", response_model=LoteOut, status_code=201
)
def processar_documentos(
    empresa_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    lote_repo = SqlAlchemyLoteProcessamentoRepository(db)
    empresa_repo = SqlAlchemyEmpresaRepository(db)
    try:
        lote, documento_ids = IniciarProcessamentoUseCase(
            documento_repo, lote_repo, empresa_repo
        ).executar(empresa_id)
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NenhumDocumentoPendente as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Commit antes de agendar: o worker abre a própria sessão e precisa
    # enxergar o lote e os documentos já marcados como PROCESSANDO.
    db.commit()

    background_tasks.add_task(
        processar_lote_em_background, lote.id, documento_ids, settings.storage_root
    )
    return lote


@router.get("/lotes/{lote_id}", response_model=LoteOut)
def obter_status_lote(lote_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyLoteProcessamentoRepository(db)
    try:
        return ObterStatusLoteUseCase(repo).executar(lote_id)
    except LoteNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/lotes/{lote_id}/cancelar", response_model=LoteOut)
def cancelar_lote(lote_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyLoteProcessamentoRepository(db)
    documento_repo = SqlAlchemyDocumentoRepository(db)
    try:
        return CancelarLoteUseCase(repo, documento_repo).executar(lote_id)
    except LoteNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LoteNaoPodeSerCancelado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
