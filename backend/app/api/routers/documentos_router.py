from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage
from app.api.schemas.documento_schemas import (
    ClassificacaoOut,
    ClassificacaoSugeridaOut,
    CorrigirClassificacaoIn,
    CorrigirClassificacaoLoteIn,
    CorrigirClassificacaoLoteOut,
    DocumentoOut,
    DocumentoResultadoOut,
    ExtracaoOut,
    ItemFilaRevisaoOut,
    OcrResultadoOut,
    ResultadoCorrecaoLoteItemOut,
    UploadItemOut,
)
from app.application.dto import ArquivoUploadDTO
from app.application.use_cases.documento_use_cases import (
    ListarDocumentosUseCase,
    ObterResultadoUseCase,
    UploadarDocumentosUseCase,
)
from app.application.use_cases.fila_revisao_use_cases import ListarFilaRevisaoUseCase
from app.core.config import settings
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
    EmpresaNaoEncontrada,
)
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
    SqlAlchemyOcrResultadoRepository,
)
from app.infrastructure.repositories.sqlalchemy_extracao_repository import (
    SqlAlchemyExtracaoRepository,
)
from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
    SqlAlchemyClassificacaoRepository,
)
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.storage.file_storage import (
    TAMANHO_MAXIMO_BYTES,
    LocalFileStorageService,
)
from app.application.use_cases.classificacao_use_cases import (
    CorrigirClassificacaoEmLoteUseCase,
    CorrigirClassificacaoUseCase,
)
from app.infrastructure.repositories.sqlalchemy_aprendizado_repository import (
    SqlAlchemyAprendizadoRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)
from app.infrastructure.repositories.sqlalchemy_regra_repository import (
    SqlAlchemyRegraRepository,
)

router = APIRouter(tags=["documentos"])

async def _ler_arquivo_limitado(arquivo: UploadFile) -> ArquivoUploadDTO:
    """Lê o upload sem nunca materializar mais que o limite + 1 byte.

    Antes, o handler fazia `await arquivo.read()` sem limite e só depois o
    tamanho era validado — ou seja, o arquivo inteiro já estava em memória
    quando a validação rodava. Aqui checamos `UploadFile.size` (populado pelo
    parser multipart do Starlette) quando disponível e, de qualquer forma,
    lemos com um teto: mesmo que `size` não venha preenchido, no máximo
    `TAMANHO_MAXIMO_BYTES + 1` bytes entram em memória.
    """
    nome = arquivo.filename or "arquivo"
    limite_mb = max(TAMANHO_MAXIMO_BYTES // (1024 * 1024), 1)
    erro = f"Arquivo excede o tamanho máximo de {limite_mb}MB."

    tamanho = getattr(arquivo, "size", None)
    if tamanho is not None and tamanho > TAMANHO_MAXIMO_BYTES:
        return ArquivoUploadDTO(nome_original=nome, conteudo=b"", erro_previo=erro)

    conteudo = await arquivo.read(TAMANHO_MAXIMO_BYTES + 1)
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        return ArquivoUploadDTO(nome_original=nome, conteudo=b"", erro_previo=erro)
    return ArquivoUploadDTO(nome_original=nome, conteudo=conteudo)


@router.post(
    "/empresas/{empresa_id}/documentos", response_model=list[UploadItemOut], status_code=201
)
async def upload_documentos(
    empresa_id: int,
    arquivos: list[UploadFile],
    db: Session = Depends(get_db),
    storage: LocalFileStorageService = Depends(get_storage),
):
    if len(arquivos) > settings.max_arquivos_por_upload:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Envie no máximo {settings.max_arquivos_por_upload} arquivos por requisição "
                f"(recebidos {len(arquivos)})."
            ),
        )

    documento_repo = SqlAlchemyDocumentoRepository(db)
    empresa_repo = SqlAlchemyEmpresaRepository(db)
    dtos = [await _ler_arquivo_limitado(arquivo) for arquivo in arquivos]
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


@router.get(
    "/empresas/{empresa_id}/documentos/fila-revisao", response_model=list[ItemFilaRevisaoOut]
)
def listar_fila_revisao(empresa_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    itens = ListarFilaRevisaoUseCase(
        documento_repo, extracao_repo, classificacao_repo, conta_repo
    ).executar(empresa_id)
    return [
        ItemFilaRevisaoOut(
            documento=DocumentoOut.model_validate(item.documento, from_attributes=True),
            extracao=ExtracaoOut.from_extracao(item.extracao) if item.extracao else None,
            classificacao_sugerida=(
                ClassificacaoSugeridaOut(
                    conta_id=item.sugestao.conta_id,
                    conta_codigo=item.sugestao.conta_codigo,
                    conta_descricao=item.sugestao.conta_descricao,
                    score_similaridade=item.sugestao.score_similaridade,
                )
                if item.sugestao
                else None
            ),
        )
        for item in itens
    ]


@router.get("/documentos/{documento_id}/resultado", response_model=DocumentoResultadoOut)
def obter_resultado(documento_id: int, db: Session = Depends(get_db)):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    resultado_repo = SqlAlchemyOcrResultadoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    try:
        documento, resultado, extracao, classificacao = ObterResultadoUseCase(
            documento_repo, resultado_repo, extracao_repo, classificacao_repo
        ).executar(documento_id)
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
    extracao_out = ExtracaoOut.from_extracao(extracao) if extracao else None
    classificacao_out = None
    if classificacao:
        conta = conta_repo.obter_por_id(classificacao.conta_id)
        if conta is not None:
            classificacao_out = ClassificacaoOut.from_classificacao(classificacao, conta)
    return DocumentoResultadoOut(
        documento=documento, resultado=resultado_out, extracao=extracao_out,
        classificacao=classificacao_out,
    )


@router.patch("/documentos/classificacao/lote", response_model=CorrigirClassificacaoLoteOut)
def corrigir_classificacao_em_lote(
    payload: CorrigirClassificacaoLoteIn, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    regra_repo = SqlAlchemyRegraRepository(db)
    aprendizado_repo = SqlAlchemyAprendizadoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    corrigir_use_case = CorrigirClassificacaoUseCase(
        documento_repo, extracao_repo, classificacao_repo, regra_repo,
        aprendizado_repo, conta_repo, plano_repo,
    )
    resultados = CorrigirClassificacaoEmLoteUseCase(corrigir_use_case).executar(
        payload.documento_ids, payload.conta_id
    )
    resultados_out = []
    for resultado in resultados:
        classificacao_out = None
        if resultado.classificacao is not None:
            conta = conta_repo.obter_por_id(resultado.classificacao.conta_id)
            classificacao_out = ClassificacaoOut.from_classificacao(resultado.classificacao, conta)
        resultados_out.append(
            ResultadoCorrecaoLoteItemOut(
                documento_id=resultado.documento_id, sucesso=resultado.sucesso,
                classificacao=classificacao_out, erro=resultado.erro,
            )
        )
    return CorrigirClassificacaoLoteOut(resultados=resultados_out)


@router.patch("/documentos/{documento_id}/classificacao", response_model=ClassificacaoOut)
def corrigir_classificacao(
    documento_id: int, payload: CorrigirClassificacaoIn, db: Session = Depends(get_db)
):
    documento_repo = SqlAlchemyDocumentoRepository(db)
    extracao_repo = SqlAlchemyExtracaoRepository(db)
    classificacao_repo = SqlAlchemyClassificacaoRepository(db)
    regra_repo = SqlAlchemyRegraRepository(db)
    aprendizado_repo = SqlAlchemyAprendizadoRepository(db)
    conta_repo = SqlAlchemyContaRepository(db)
    plano_repo = SqlAlchemyPlanoContasRepository(db)
    try:
        classificacao = CorrigirClassificacaoUseCase(
            documento_repo, extracao_repo, classificacao_repo, regra_repo,
            aprendizado_repo, conta_repo, plano_repo,
        ).executar(documento_id, payload.conta_id)
    except DocumentoNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ContaNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ContaNaoPertenceAEmpresa, ContaNaoAnalitica) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conta = conta_repo.obter_por_id(classificacao.conta_id)
    return ClassificacaoOut.from_classificacao(classificacao, conta)
