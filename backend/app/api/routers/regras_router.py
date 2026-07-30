from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas.regra_schemas import RegraCreateIn, RegraOut, RegraUpdateIn
from app.application.dto import AtualizarRegraDTO, CriarRegraDTO
from app.application.use_cases.regra_use_cases import (
    AtualizarRegraUseCase,
    CriarRegraUseCase,
    DeletarRegraUseCase,
    ListarRegrasUseCase,
)
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    RegraDocumentoFiscalInvalido,
    RegraNaoEncontrada,
    RegraSemCondicoes,
    RegraSemLadoAlvo,
)
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)
from app.infrastructure.repositories.sqlalchemy_regra_repository import (
    SqlAlchemyRegraRepository,
)

router = APIRouter(tags=["regras"])


def _dto_criar(payload: RegraCreateIn) -> CriarRegraDTO:
    return CriarRegraDTO(
        conta_id=payload.conta_id,
        lado_alvo=payload.lado_alvo.value if payload.lado_alvo else None,
        documento_fiscal=payload.documento_fiscal,
        tipo_documento=payload.tipo_documento.value if payload.tipo_documento else None,
        valor_min=payload.valor_min,
        valor_max=payload.valor_max,
        palavra_chave_nome=payload.palavra_chave_nome,
    )


@router.post(
    "/empresas/{empresa_id}/regras", response_model=RegraOut, status_code=status.HTTP_201_CREATED
)
def criar_regra(empresa_id: int, payload: RegraCreateIn, db: Session = Depends(get_db)):
    regra_repo = SqlAlchemyRegraRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    try:
        regra = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(
            empresa_id, _dto_criar(payload)
        )
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ContaNaoPertenceAEmpresa, ContaNaoAnalitica, RegraSemCondicoes, RegraSemLadoAlvo,
        RegraDocumentoFiscalInvalido,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RegraOut.from_regra(regra)


@router.get("/empresas/{empresa_id}/regras", response_model=list[RegraOut])
def listar_regras(empresa_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyRegraRepository(db)
    regras = ListarRegrasUseCase(repo).executar(empresa_id)
    return [RegraOut.from_regra(r) for r in regras]


@router.patch("/empresas/{empresa_id}/regras/{regra_id}", response_model=RegraOut)
def atualizar_regra(
    empresa_id: int, regra_id: int, payload: RegraUpdateIn, db: Session = Depends(get_db)
):
    regra_repo = SqlAlchemyRegraRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    dto = AtualizarRegraDTO(
        conta_id=payload.conta_id,
        lado_alvo=payload.lado_alvo.value if payload.lado_alvo else None,
        documento_fiscal=payload.documento_fiscal,
        tipo_documento=payload.tipo_documento.value if payload.tipo_documento else None,
        valor_min=payload.valor_min,
        valor_max=payload.valor_max,
        palavra_chave_nome=payload.palavra_chave_nome,
        ativo=payload.ativo,
    )
    try:
        regra = AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(
            empresa_id, regra_id, dto
        )
    except (RegraNaoEncontrada, ContaNaoEncontrada) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ContaNaoPertenceAEmpresa, ContaNaoAnalitica, RegraSemCondicoes, RegraSemLadoAlvo,
        RegraDocumentoFiscalInvalido,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RegraOut.from_regra(regra)


@router.delete("/empresas/{empresa_id}/regras/{regra_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_regra(empresa_id: int, regra_id: int, db: Session = Depends(get_db)):
    repo = SqlAlchemyRegraRepository(db)
    try:
        DeletarRegraUseCase(repo).executar(empresa_id, regra_id)
    except RegraNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
