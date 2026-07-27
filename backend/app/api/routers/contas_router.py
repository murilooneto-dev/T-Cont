from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.conta_schemas import ContaCreateIn, ContaOut, ContaUpdateIn
from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.use_cases.conta_use_cases import (
    AtualizarContaUseCase,
    CriarContaUseCase,
    DeletarContaUseCase,
    ListarContasUseCase,
)
from app.core.exceptions import ContaNaoEncontrada
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)

router = APIRouter(tags=["contas"])


@router.post(
    "/planos-contas/{plano_id}/contas", response_model=ContaOut, status_code=status.HTTP_201_CREATED
)
def criar_conta(plano_id: int, payload: ContaCreateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    dto = CriarContaDTO(
        payload.codigo, payload.descricao, payload.natureza.value,
        payload.conta_analitica, payload.conta_pai_id,
    )
    return CriarContaUseCase(repo).executar(plano_id, dto)


@router.get("/planos-contas/{plano_id}/contas", response_model=list[ContaOut])
def listar_contas(plano_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    return ListarContasUseCase(repo).executar(plano_id)


@router.put("/contas/{conta_id}", response_model=ContaOut)
def atualizar_conta(conta_id: int, payload: ContaUpdateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    dto = AtualizarContaDTO(
        payload.codigo, payload.descricao, payload.natureza.value,
        payload.conta_analitica, payload.conta_pai_id,
    )
    try:
        return AtualizarContaUseCase(repo).executar(conta_id, dto)
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/contas/{conta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_conta(conta_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyContaRepository(db)
    DeletarContaUseCase(repo).executar(conta_id)
