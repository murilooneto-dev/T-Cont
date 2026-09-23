from app.application.ports import ArmazenamentoArquivos
from app.application.repositories import (
    AprendizadoRepository, ClassificacaoRepository, ContaRepository, DocumentoRepository,
    ExtracaoRepository, OcrResultadoRepository,
)
from app.application.use_cases.fila_revisao_use_cases import ListarFilaRevisaoUseCase
from app.domain.enums import StatusDocumento

_STATUS_PROCESSADOS = {
    StatusDocumento.CONCLUIDO, StatusDocumento.ERRO, StatusDocumento.DIVIDIDO,
}


class _ApagadorDeDocumento:
    """Remove um documento e tudo o que está ligado a ele (aprendizado,
    classificação, extração, resultado de OCR, arquivo físico), na ordem que
    respeita as foreign keys existentes.
    """

    def __init__(
        self,
        documento_repo: DocumentoRepository,
        ocr_repo: OcrResultadoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        aprendizado_repo: AprendizadoRepository,
        storage: ArmazenamentoArquivos,
    ):
        self._documento_repo = documento_repo
        self._ocr_repo = ocr_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._aprendizado_repo = aprendizado_repo
        self._storage = storage

    def apagar(self, documento_id: int) -> None:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            return
        self._aprendizado_repo.deletar_por_documento_id(documento_id)
        self._classificacao_repo.deletar_por_documento_id(documento_id)
        self._extracao_repo.deletar_por_documento_id(documento_id)
        self._ocr_repo.deletar_por_documento_id(documento_id)
        self._storage.apagar(documento.caminho_arquivo)
        self._documento_repo.deletar(documento_id)


class LimparFilaRevisaoUseCase:
    """Apaga todos os documentos atualmente na Fila de Revisão (sem
    classificação, ou com lançamento incompleto/FUZZY) — e tudo ligado a eles.
    """

    def __init__(
        self,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
        aprendizado_repo: AprendizadoRepository,
        ocr_repo: OcrResultadoRepository,
        storage: ArmazenamentoArquivos,
    ):
        self._listar_fila = ListarFilaRevisaoUseCase(
            documento_repo, extracao_repo, classificacao_repo, conta_repo
        )
        self._apagador = _ApagadorDeDocumento(
            documento_repo, ocr_repo, extracao_repo, classificacao_repo, aprendizado_repo, storage
        )

    def executar(self, empresa_id: int) -> int:
        itens = self._listar_fila.executar(empresa_id)
        for item in itens:
            self._apagador.apagar(item.documento.id)
        return len(itens)


class LimparDocumentosProcessadosUseCase:
    """Apaga todo documento CONCLUIDO/ERRO/DIVIDIDO da empresa (e tudo ligado
    a eles). Documentos PENDENTE/PROCESSANDO não são tocados — ainda estão na
    fila de trabalho. Filhos (documento_origem_id preenchido) são apagados
    antes dos pais, já que documento_origem_id é uma FK pra documentos.id.
    """

    def __init__(
        self,
        documento_repo: DocumentoRepository,
        ocr_repo: OcrResultadoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        aprendizado_repo: AprendizadoRepository,
        storage: ArmazenamentoArquivos,
    ):
        self._documento_repo = documento_repo
        self._apagador = _ApagadorDeDocumento(
            documento_repo, ocr_repo, extracao_repo, classificacao_repo, aprendizado_repo, storage
        )

    def executar(self, empresa_id: int) -> int:
        documentos = [
            d for d in self._documento_repo.listar_por_empresa(empresa_id)
            if d.status in _STATUS_PROCESSADOS
        ]
        filhos = [d for d in documentos if d.documento_origem_id is not None]
        pais = [d for d in documentos if d.documento_origem_id is None]
        for documento in filhos:
            self._apagador.apagar(documento.id)
        for documento in pais:
            self._apagador.apagar(documento.id)
        return len(documentos)
