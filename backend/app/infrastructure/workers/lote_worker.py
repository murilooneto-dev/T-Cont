"""Worker de background do processamento OCR de um lote.

Vive na camada de infraestrutura (e não em `application/use_cases`) porque é
código de composition root: ele constrói sessão de banco, repositórios
SQLAlchemy concretos e o serviço de storage local. Os use cases do lote
continuam em `app.application.use_cases.lote_use_cases`, dependendo apenas de
repositórios abstratos.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.domain.entities import OcrResultado
from app.domain.enums import StatusDocumento, StatusLote
from app.infrastructure.ocr.pipeline import processar_documento

logger = logging.getLogger(__name__)


def _resetar_documentos_processando_para_pendente(documento_repo, documento_ids: list[int]) -> None:
    """Devolve à fila (PENDENTE) documentos reivindicados (PROCESSANDO) que
    nunca chegaram a terminar.

    Sem isto, documentos de um lote que falha ou é cancelado ficam presos em
    PROCESSANDO para sempre: `listar_pendentes_por_empresa` filtra
    estritamente por PENDENTE, então nunca mais seriam selecionados em um
    lote futuro. Documentos que já chegaram a CONCLUIDO ou ERRO são
    preservados — só os que ainda estão PROCESSANDO (nunca processados) são
    revertidos.
    """
    for documento_id in documento_ids:
        documento = documento_repo.obter_por_id(documento_id)
        if documento is not None and documento.status == StatusDocumento.PROCESSANDO:
            documento.status = StatusDocumento.PENDENTE
            documento_repo.atualizar(documento)


def _marcar_lote_como_falhou(
    session_factory: Callable[[], object], lote_id: int, documento_ids: list[int]
) -> None:
    """Marca o lote como FALHOU usando uma sessão nova e curta.

    A sessão do processamento pode estar em estado inconsistente (transação
    abortada após um IntegrityError, por exemplo), então não dá para reusá-la
    para gravar o status final. Esta função nunca propaga exceção: é o último
    recurso de um background task que não tem chamador para receber o erro.
    """
    try:
        from app.infrastructure.repositories.sqlalchemy_documento_repository import (
            SqlAlchemyDocumentoRepository,
        )
        from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
            SqlAlchemyLoteProcessamentoRepository,
        )

        session = session_factory()
        try:
            lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
            lote = lote_repo.obter_por_id(lote_id)
            if lote is None:
                logger.error("Lote %s desapareceu; não foi possível marcá-lo como FALHOU.", lote_id)
                return
            lote.status = StatusLote.FALHOU
            lote.concluido_em = datetime.now(timezone.utc)
            lote_repo.atualizar(lote)

            documento_repo = SqlAlchemyDocumentoRepository(session)
            _resetar_documentos_processando_para_pendente(documento_repo, documento_ids)

            session.commit()
        finally:
            session.close()
    except Exception:  # pragma: no cover - último recurso
        logger.exception("Falha ao marcar o lote %s como FALHOU.", lote_id)


def processar_lote_em_background(
    lote_id: int,
    documento_ids: list[int],
    storage_root: str,
    session_factory: Callable[[], object] | None = None,
) -> None:
    """Roda depois que a resposta HTTP já retornou.

    Monta a própria sessão de banco e o storage porque não está mais dentro do
    escopo da request. Submete o OCR de cada documento a um pool de processos,
    atualizando o progresso a cada resultado, e para de submeter trabalho novo
    assim que o lote é marcado como CANCELADO.

    `session_factory` é injetável para permitir que testes passem sua própria
    fábrica de sessões em vez de monkeypatchar `SessionLocal`. Quando `None`,
    usa o `SessionLocal` real (import tardio para não carregar a engine da
    aplicação em quem só importa este módulo).
    """
    if session_factory is None:
        from app.infrastructure.db.session import SessionLocal

        session_factory = SessionLocal

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

    session = session_factory()
    try:
        documento_repo = SqlAlchemyDocumentoRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))

        with ProcessPoolExecutor(max_workers=settings.ocr_max_workers) as pool:
            futuros = {}
            for documento_id in documento_ids:
                # O cancelamento chega por outra sessão (a da request HTTP). Sem
                # expirar a identity map, `session.get` devolveria a cópia em
                # cache do lote e o worker nunca enxergaria o CANCELADO.
                session.expire_all()
                lote_atual = lote_repo.obter_por_id(lote_id)
                if lote_atual is None or lote_atual.status == StatusLote.CANCELADO:
                    break
                documento = documento_repo.obter_por_id(documento_id)
                if documento is None:
                    logger.warning(
                        "Documento %s não encontrado; ignorado no lote %s.",
                        documento_id, lote_id,
                    )
                    continue
                conteudo = storage.ler(documento.caminho_arquivo)
                futuro = pool.submit(processar_documento, conteudo, documento.extensao)
                futuros[futuro] = documento_id

            for futuro in as_completed(futuros):
                documento_id = futuros[futuro]
                documento = documento_repo.obter_por_id(documento_id)
                if documento is None:
                    logger.warning(
                        "Documento %s sumiu durante o processamento do lote %s; ignorado.",
                        documento_id, lote_id,
                    )
                    continue
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
                if lote_atual is None:
                    logger.warning("Lote %s desapareceu durante o processamento.", lote_id)
                    continue
                lote_atual.documentos_processados += 1
                lote_repo.atualizar(lote_atual)
                session.commit()

        session.expire_all()
        lote_final = lote_repo.obter_por_id(lote_id)
        if lote_final is None:
            logger.warning("Lote %s não encontrado ao finalizar o processamento.", lote_id)
        elif lote_final.status == StatusLote.CANCELADO:
            # Documentos ainda não submetidos ao pool no momento do cancelamento
            # continuam PROCESSANDO — sem isto ficariam presos para sempre, já
            # que `listar_pendentes_por_empresa` só enxerga PENDENTE.
            _resetar_documentos_processando_para_pendente(documento_repo, documento_ids)
            session.commit()
        else:
            lote_final.status = StatusLote.CONCLUIDO
            lote_final.concluido_em = datetime.now(timezone.utc)
            lote_repo.atualizar(lote_final)
            session.commit()
    except Exception:
        # Sem isto o lote ficaria preso em EM_ANDAMENTO para sempre e o
        # frontend faria polling infinito sem mostrar erro nenhum.
        logger.exception("Erro ao processar o lote %s em background.", lote_id)
        try:
            session.rollback()
        except Exception:  # pragma: no cover - sessão já inutilizável
            logger.exception("Falha no rollback da sessão do lote %s.", lote_id)
        _marcar_lote_como_falhou(session_factory, lote_id, documento_ids)
    finally:
        session.close()
