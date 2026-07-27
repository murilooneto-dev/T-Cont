from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.plano_contas_schemas import PlanoContasCreateIn, PlanoContasOut
from app.application.dto import CriarPlanoContasDTO
from app.application.use_cases.plano_contas_use_cases import (
    CriarPlanoContasUseCase,
    ListarPlanosContasUseCase,
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
