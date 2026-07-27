from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.empresa_schemas import EmpresaCreateIn, EmpresaOut, EmpresaUpdateIn
from app.application.dto import AtualizarEmpresaDTO, CriarEmpresaDTO
from app.application.use_cases.empresa_use_cases import (
    AtualizarEmpresaUseCase,
    CriarEmpresaUseCase,
    DesativarEmpresaUseCase,
    ListarEmpresasUseCase,
    ObterEmpresaUseCase,
)
from app.core.exceptions import CnpjJaCadastrado, EmpresaNaoEncontrada
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)

router = APIRouter(prefix="/empresas", tags=["empresas"])


@router.post("", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def criar_empresa(payload: EmpresaCreateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        empresa = CriarEmpresaUseCase(repo).executar(
            CriarEmpresaDTO(payload.razao_social, payload.nome_fantasia, payload.cnpj)
        )
    except CnpjJaCadastrado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return empresa


@router.get("", response_model=list[EmpresaOut])
def listar_empresas(db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    return ListarEmpresasUseCase(repo).executar()


@router.get("/{empresa_id}", response_model=EmpresaOut)
def obter_empresa(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        return ObterEmpresaUseCase(repo).executar(empresa_id)
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{empresa_id}", response_model=EmpresaOut)
def atualizar_empresa(empresa_id: int, payload: EmpresaUpdateIn, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        return AtualizarEmpresaUseCase(repo).executar(
            empresa_id,
            AtualizarEmpresaDTO(payload.razao_social, payload.nome_fantasia, payload.ativo),
        )
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT)
def desativar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyEmpresaRepository(db)
    try:
        DesativarEmpresaUseCase(repo).executar(empresa_id)
    except EmpresaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
