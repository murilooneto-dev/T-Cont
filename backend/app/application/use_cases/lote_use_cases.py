from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    LoteProcessamentoRepository,
    OcrResultadoRepository,
)
from app.core.exceptions import EmpresaNaoEncontrada, LoteNaoEncontrado
from app.domain.entities import LoteProcessamento, OcrResultado
from app.domain.enums import StatusDocumento, StatusLote
from app.infrastructure.ocr.pipeline import processar_documento


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

    def executar(self, empresa_id: int) -> LoteProcessamento:
        if self._empresa_repo.obter_por_id(empresa_id) is None:
            raise EmpresaNaoEncontrada(empresa_id)

        pendentes = self._documento_repo.listar_pendentes_por_empresa(empresa_id)
        lote = LoteProcessamento(id=None, empresa_id=empresa_id, total_documentos=len(pendentes))
        return self._lote_repo.criar(lote)


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
        lote.status = StatusLote.CANCELADO
        return self._repo.atualizar(lote)


def processar_lote_em_background(lote_id: int, documento_ids: list[int], storage_root: str) -> None:
    """Runs after the HTTP response returns. Builds its own DB session and file
    storage instance since it's no longer inside a request scope. Submits each
    document's OCR work to a process pool, updating progress after each result,
    and stops submitting new work once the batch is marked CANCELADO."""
    from app.infrastructure.db.session import SessionLocal
    from app.infrastructure.repositories.sqlalchemy_documento_repository import (
        SqlAlchemyDocumentoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
        SqlAlchemyLoteProcessamentoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
        SqlAlchemyOcrResultadoRepository,
    )
    from app.infrastructure.storage.file_storage import LocalFileStorageService

    session = SessionLocal()
    try:
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))

        with ProcessPoolExecutor() as pool:
            futuros = {}
            for documento_id in documento_ids:
                lote_atual = lote_repo.obter_por_id(lote_id)
                if lote_atual is None or lote_atual.status == StatusLote.CANCELADO:
                    break
                documento = documento_repo.obter_por_id(documento_id)
                conteudo = storage.ler(documento.caminho_arquivo)
                futuro = pool.submit(processar_documento, conteudo, documento.extensao)
                futuros[futuro] = documento_id

            for futuro in as_completed(futuros):
                documento_id = futuros[futuro]
                documento = documento_repo.obter_por_id(documento_id)
                resultado_pipeline = futuro.result()

                if resultado_pipeline.erro:
                    documento.status = StatusDocumento.ERRO
                    documento.mensagem_erro = resultado_pipeline.erro
                else:
                    documento.status = StatusDocumento.CONCLUIDO
                    resultado_repo.criar(
                        OcrResultado(
                            id=None, documento_id=documento_id,
                            texto_extraido=resultado_pipeline.texto,
                            metodo=resultado_pipeline.metodo,
                            tempo_processamento_ms=resultado_pipeline.tempo_processamento_ms,
                        )
                    )
                documento_repo.atualizar(documento)

                lote_atual = lote_repo.obter_por_id(lote_id)
                lote_atual.documentos_processados += 1
                lote_repo.atualizar(lote_atual)
                session.commit()

        lote_final = lote_repo.obter_por_id(lote_id)
        if lote_final.status != StatusLote.CANCELADO:
            lote_final.status = StatusLote.CONCLUIDO
            lote_final.concluido_em = datetime.now(timezone.utc)
            lote_repo.atualizar(lote_final)
            session.commit()
    finally:
        session.close()
