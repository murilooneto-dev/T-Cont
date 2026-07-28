from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    LoteProcessamentoRepository,
)
from app.core.exceptions import (
    EmpresaNaoEncontrada,
    LoteNaoEncontrado,
    LoteNaoPodeSerCancelado,
    NenhumDocumentoPendente,
)
from app.domain.entities import LoteProcessamento
from app.domain.enums import StatusDocumento, StatusLote


class IniciarProcessamentoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        lote_repo: LoteProcessamentoRepository,
        empresa_repo: EmpresaRepository,
    ):
        self._documento_repo = documento_repo
        self._lote_repo = lote_repo
        self._empresa_repo = empresa_repo

    def executar(self, empresa_id: int) -> tuple[LoteProcessamento, list[int]]:
        """Cria o lote e "reivindica" os documentos pendentes marcando-os como
        PROCESSANDO.

        A marcação acontece aqui (e não no worker em background) para fechar a
        janela de duplo clique no botão "Processar": assim que este use case
        retorna, os documentos já não aparecem mais em
        `listar_pendentes_por_empresa`, então uma segunda chamada não consegue
        reprocessar os mesmos documentos — o que causaria violação da constraint
        UNIQUE de `ocr_resultados.documento_id`.

        Retorna o lote e os ids dos documentos reivindicados (o chamador não
        pode mais consultar os pendentes depois, justamente porque a lista já
        foi esvaziada por esta reivindicação).
        """
        if self._empresa_repo.obter_por_id(empresa_id) is None:
            raise EmpresaNaoEncontrada(empresa_id)

        pendentes = self._documento_repo.listar_pendentes_por_empresa(empresa_id)
        if not pendentes:
            # Sem isso um lote com total_documentos=0 ficaria preso em
            # EM_ANDAMENTO para sempre (nada em background para concluí-lo).
            raise NenhumDocumentoPendente(empresa_id)

        lote = LoteProcessamento(id=None, empresa_id=empresa_id, total_documentos=len(pendentes))
        lote_criado = self._lote_repo.criar(lote)

        documento_ids = []
        for documento in pendentes:
            documento.status = StatusDocumento.PROCESSANDO
            self._documento_repo.atualizar(documento)
            documento_ids.append(documento.id)

        return lote_criado, documento_ids


class ObterStatusLoteUseCase:
    def __init__(self, repo: LoteProcessamentoRepository):
        self._repo = repo

    def executar(self, lote_id: int) -> LoteProcessamento:
        lote = self._repo.obter_por_id(lote_id)
        if lote is None:
            raise LoteNaoEncontrado(lote_id)
        return lote


class CancelarLoteUseCase:
    def __init__(self, repo: LoteProcessamentoRepository):
        self._repo = repo

    def executar(self, lote_id: int) -> LoteProcessamento:
        lote = ObterStatusLoteUseCase(self._repo).executar(lote_id)
        if lote.status != StatusLote.EM_ANDAMENTO:
            raise LoteNaoPodeSerCancelado(lote_id, lote.status.value)
        lote.status = StatusLote.CANCELADO
        return self._repo.atualizar(lote)
