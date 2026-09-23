"""Worker de background do processamento OCR de um lote.

Vive na camada de infraestrutura (e não em `application/use_cases`) porque é
código de composition root: ele constrói sessão de banco, repositórios
SQLAlchemy concretos e o serviço de storage local. Os use cases do lote
continuam em `app.application.use_cases.lote_use_cases`, dependendo apenas de
repositórios abstratos.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.domain.entities import Classificacao, Documento, Extracao, OcrResultado
from app.domain.enums import DirecaoLancamento, NaturezaConta, StatusDocumento, StatusLote
from app.infrastructure.ocr.pipeline import processar_documento
from app.infrastructure.extracao.agrupamento import agrupar_paginas_em_comprovantes
from app.infrastructure.extracao.pipeline import extrair_dados_documento
from app.infrastructure.classificacao.pipeline import classificar_documento
from app.infrastructure.classificacao.lancamento_contabil import (
    resolver_conta_bancaria,
    resolver_direcao,
)
from app.infrastructure.ocr.recorte_pdf import recortar_paginas_pdf

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


def _listar_contas_analiticas(conta_repo, plano_repo, empresa_id: int) -> list:
    """Contas analíticas de todos os planos de contas da empresa — usadas como
    as opções oferecidas à IA (Fase 4) na classificação por fallback.
    """
    contas = []
    for plano in plano_repo.listar_por_empresa(empresa_id):
        contas.extend(c for c in conta_repo.listar_por_plano(plano.id) if c.conta_analitica)
    return contas


def _processar_comprovante(
    documento,
    texto: str,
    metodo,
    tempo_processamento_ms: int,
    resultado_repo,
    extracao_repo,
    classificacao_repo,
    regras: list,
    contas_disponiveis: list,
    historico_fuzzy: list[tuple[str, int, datetime]],
    empresa_cnpj: str,
) -> None:
    """Grava OcrResultado + Extracao + Classificacao de um comprovante.

    Compartilhado pelo caminho de 1 segmento (documento original) e pelo
    caminho de 2+ segmentos (cada filho) — é o que garante que os dois
    caminhos produzem exatamente o mesmo resultado para o mesmo texto.
    """
    resultado_repo.criar(
        OcrResultado(
            id=None, documento_id=documento.id,
            texto_extraido=texto,
            metodo=metodo,
            tempo_processamento_ms=tempo_processamento_ms,
        )
    )
    dados = extrair_dados_documento(texto)
    extracao_criada = extracao_repo.criar(
        Extracao(
            id=None, documento_id=documento.id,
            pagador_nome=dados.pagador_nome,
            pagador_documento=dados.pagador_documento,
            recebedor_nome=dados.recebedor_nome,
            recebedor_documento=dados.recebedor_documento,
            valor=dados.valor,
            data_pagamento=dados.data_pagamento,
            tipo_documento=dados.tipo_documento,
            banco_nome=dados.banco_nome,
        )
    )

    resultado_classificacao = classificar_documento(
        extracao_criada, regras, contas_disponiveis, historico_fuzzy
    )
    if resultado_classificacao is not None:
        direcao = resolver_direcao(empresa_cnpj, extracao_criada)
        conta_bancaria_id = None
        if extracao_criada.banco_nome is not None:
            contas_bancarias = [
                conta for conta in contas_disponiveis if conta.natureza == NaturezaConta.ATIVO
            ]
            conta_bancaria_id = resolver_conta_bancaria(extracao_criada.banco_nome, contas_bancarias)
        nova_classificacao = classificacao_repo.criar(
            Classificacao(
                id=None,
                empresa_id=documento.empresa_id,
                documento_id=documento.id,
                conta_id=resultado_classificacao.conta_id,
                origem=resultado_classificacao.origem,
                regra_id=resultado_classificacao.regra_id,
                score_similaridade=resultado_classificacao.score_similaridade,
                conta_bancaria_id=conta_bancaria_id,
                direcao=direcao,
            )
        )
        nome_para_historico = extracao_criada.recebedor_nome or extracao_criada.pagador_nome
        if nome_para_historico is not None:
            historico_fuzzy.append(
                (nome_para_historico, resultado_classificacao.conta_id, nova_classificacao.created_at)
            )


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
    from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
        SqlAlchemyEmpresaRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
        SqlAlchemyLoteProcessamentoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
        SqlAlchemyOcrResultadoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_extracao_repository import (
        SqlAlchemyExtracaoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_regra_repository import (
        SqlAlchemyRegraRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
        SqlAlchemyClassificacaoRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_conta_repository import (
        SqlAlchemyContaRepository,
    )
    from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
        SqlAlchemyPlanoContasRepository,
    )
    from app.infrastructure.storage.file_storage import LocalFileStorageService

    session = session_factory()
    try:
        documento_repo = SqlAlchemyDocumentoRepository(session)
        empresa_repo = SqlAlchemyEmpresaRepository(session)
        resultado_repo = SqlAlchemyOcrResultadoRepository(session)
        extracao_repo = SqlAlchemyExtracaoRepository(session)
        regra_repo = SqlAlchemyRegraRepository(session)
        classificacao_repo = SqlAlchemyClassificacaoRepository(session)
        conta_repo = SqlAlchemyContaRepository(session)
        plano_repo = SqlAlchemyPlanoContasRepository(session)
        lote_repo = SqlAlchemyLoteProcessamentoRepository(session)
        storage = LocalFileStorageService(Path(storage_root))

        with ProcessPoolExecutor(max_workers=settings.ocr_max_workers) as pool:
            futuros_por_documento = {}
            conteudo_por_documento: dict[int, bytes] = {}
            empresa_id_lote: int | None = None
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
                if empresa_id_lote is None:
                    empresa_id_lote = documento.empresa_id
                conteudo = storage.ler(documento.caminho_arquivo)
                # Guardado para o recorte de páginas de um documento unificado
                # (segunda etapa, depois que o OCR devolver o resultado) — sem
                # isto teríamos que reler o arquivo do disco outra vez.
                conteudo_por_documento[documento_id] = conteudo
                futuro = pool.submit(processar_documento, conteudo, documento.extensao)
                futuros_por_documento[documento_id] = futuro

            # Motor de regras e histórico fuzzy são carregados uma vez antes do
            # laço (não por documento) — regras não mudam durante o lote, e o
            # histórico é acrescido em memória conforme cada novo documento é
            # classificado, evitando N+1 consultas repetidas por documento.
            regras = regra_repo.listar_por_empresa(empresa_id_lote) if empresa_id_lote is not None else []
            contas_disponiveis = (
                _listar_contas_analiticas(conta_repo, plano_repo, empresa_id_lote)
                if empresa_id_lote is not None
                else []
            )
            historico_fuzzy: list[tuple[str, int, datetime]] = []
            if empresa_id_lote is not None:
                for classificacao_existente in classificacao_repo.listar_por_empresa(empresa_id_lote):
                    extracao_historica = extracao_repo.obter_por_documento_id(
                        classificacao_existente.documento_id
                    )
                    if extracao_historica is None:
                        continue
                    nome_historico = (
                        extracao_historica.recebedor_nome or extracao_historica.pagador_nome
                    )
                    if nome_historico is None:
                        continue
                    historico_fuzzy.append(
                        (
                            nome_historico,
                            classificacao_existente.conta_id,
                            classificacao_existente.created_at,
                        )
                    )

            # CNPJ da empresa resolvido uma vez por lote (não por documento) —
            # usado por resolver_direcao dentro de _processar_comprovante.
            # String vazia como padrão em vez de None: resolver_direcao espera
            # um str, e uma string vazia nunca bate com um CNPJ extraído de
            # verdade, então o comportamento seguro (direção não resolvida)
            # acontece naturalmente sem precisar de um `if` extra dentro de
            # _processar_comprovante.
            empresa_cnpj = ""
            if empresa_id_lote is not None:
                empresa = empresa_repo.obter_por_id(empresa_id_lote)
                if empresa is not None:
                    empresa_cnpj = empresa.cnpj

            # Itera na ordem de SUBMISSÃO (não na ordem de conclusão do OCR via
            # as_completed) para que a classificação de um lote seja
            # determinística e reprodutível — um documento nunca deveria deixar
            # de enxergar o histórico de um documento anterior no mesmo lote só
            # porque o OCR dele terminou depois.
            for documento_id in documento_ids:
                futuro = futuros_por_documento.get(documento_id)
                if futuro is None:
                    continue
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
                    documento_repo.atualizar(documento)
                else:
                    segmentos = agrupar_paginas_em_comprovantes(resultado_pipeline.textos_por_pagina)

                    if len(segmentos) <= 1:
                        # Caminho idêntico ao comportamento anterior a esta
                        # funcionalidade: junta todas as páginas (mesmo join
                        # já usado por extrair_texto_nativo) e extrai uma vez.
                        texto_completo = "\n".join(resultado_pipeline.textos_por_pagina)
                        documento.status = StatusDocumento.CONCLUIDO
                        documento_repo.atualizar(documento)
                        _processar_comprovante(
                            documento=documento,
                            texto=texto_completo,
                            metodo=resultado_pipeline.metodo,
                            tempo_processamento_ms=resultado_pipeline.tempo_processamento_ms,
                            resultado_repo=resultado_repo,
                            extracao_repo=extracao_repo,
                            classificacao_repo=classificacao_repo,
                            regras=regras,
                            contas_disponiveis=contas_disponiveis,
                            historico_fuzzy=historico_fuzzy,
                            empresa_cnpj=empresa_cnpj,
                        )
                    else:
                        documento.status = StatusDocumento.DIVIDIDO
                        documento_repo.atualizar(documento)
                        conteudo_original = conteudo_por_documento.get(documento_id)
                        for segmento in segmentos:
                            pagina_inicio, pagina_fim = segmento[0] + 1, segmento[-1] + 1
                            sufixo = (
                                f" — pág. {pagina_inicio}"
                                if pagina_inicio == pagina_fim
                                else f" — pág. {pagina_inicio}-{pagina_fim}"
                            )
                            nome_exibicao_filho = f"{documento.nome_exibicao}{sufixo}"
                            bytes_recortados = recortar_paginas_pdf(conteudo_original, segmento)
                            # Passa o nome ORIGINAL (sem o sufixo "— pág. N")
                            # para a validação de extensão — o sufixo tem um
                            # ponto em "pág.", que faria Path(...).suffix
                            # devolver algo como ". 1-2" em vez de ".pdf" e
                            # rejeitar o arquivo. O nome físico gravado em
                            # disco é sempre gerado pelo storage (timestamp +
                            # uuid), então isto não afeta o nome exibido.
                            nome_fisico, caminho_relativo, extensao_filho = storage.salvar(
                                documento.empresa_id, documento.nome_exibicao, bytes_recortados
                            )
                            filho = documento_repo.criar(
                                Documento(
                                    id=None,
                                    empresa_id=documento.empresa_id,
                                    nome_arquivo=nome_fisico,
                                    nome_exibicao=nome_exibicao_filho,
                                    caminho_arquivo=caminho_relativo,
                                    extensao=extensao_filho,
                                    tamanho_bytes=len(bytes_recortados),
                                    status=StatusDocumento.CONCLUIDO,
                                    documento_origem_id=documento.id,
                                )
                            )
                            texto_segmento = "\n".join(
                                resultado_pipeline.textos_por_pagina[i] for i in segmento
                            )
                            _processar_comprovante(
                                documento=filho,
                                texto=texto_segmento,
                                metodo=resultado_pipeline.metodo,
                                tempo_processamento_ms=resultado_pipeline.tempo_processamento_ms,
                                resultado_repo=resultado_repo,
                                extracao_repo=extracao_repo,
                                classificacao_repo=classificacao_repo,
                                regras=regras,
                                contas_disponiveis=contas_disponiveis,
                                historico_fuzzy=historico_fuzzy,
                                empresa_cnpj=empresa_cnpj,
                            )

                # Libera memória do conteúdo do PDF assim que não for mais
                # necessário — cobre tanto o caminho de 1-segmento (nunca foi
                # lido) quanto o de N-segmentos (já foi usado).
                conteudo_por_documento.pop(documento_id, None)

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
