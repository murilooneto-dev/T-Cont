from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.conta_schemas import ContaOut
from app.api.schemas.import_schemas import ImportPreviewOut
from app.api.schemas.plano_contas_schemas import PlanoContasCreateIn, PlanoContasOut
from app.application.dto import CriarPlanoContasDTO
from app.application.use_cases.importar_plano_contas_use_cases import (
    ConfirmarImportacaoUseCase,
    PreviewImportacaoUseCase,
)
from app.application.use_cases.plano_contas_use_cases import (
    CriarPlanoContasUseCase,
    ListarPlanosContasUseCase,
)
from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)

router = APIRouter(tags=["planos-contas"])


@router.post(
    "/empresas/{empresa_id}/planos-contas",
    response_model=PlanoContasOut,
    status_code=status.HTTP_201_CREATED,
)
def criar_plano_contas(empresa_id: int, payload: PlanoContasCreateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyPlanoContasRepository(db)
    return CriarPlanoContasUseCase(repo).executar(empresa_id, CriarPlanoContasDTO(payload.nome))


@router.get("/empresas/{empresa_id}/planos-contas", response_model=list[PlanoContasOut])
def listar_planos_contas(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyPlanoContasRepository(db)
    return ListarPlanosContasUseCase(repo).executar(empresa_id)


@router.post("/planos-contas/{plano_id}/import/preview", response_model=ImportPreviewOut)
async def preview_importacao(plano_id: int, arquivo: UploadFile = File(...)):
    conteudo = await arquivo.read()
    try:
        return PreviewImportacaoUseCase().executar(conteudo, arquivo.filename)
    except ImportacaoPlanoContasInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/planos-contas/{plano_id}/import/confirm",
    response_model=list[ContaOut],
    status_code=201,
)
async def confirmar_importacao(
    plano_id: int, arquivo: UploadFile = File(...), db: Session = Depends(get_db)
):
    conteudo = await arquivo.read()
    try:
        resultado = PreviewImportacaoUseCase().executar(conteudo, arquivo.filename)
    except ImportacaoPlanoContasInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repo = SqlAlchemyContaRepository(db)
    return ConfirmarImportacaoUseCase(repo).executar(plano_id, resultado.linhas)
