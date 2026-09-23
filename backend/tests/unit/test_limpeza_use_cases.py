from app.application.use_cases.limpeza_use_cases import (
    LimparDocumentosProcessadosUseCase,
    LimparFilaRevisaoUseCase,
)
from app.domain.entities import (
    Aprendizado, Classificacao, Conta, Documento, Extracao, OcrResultado, PlanoContas,
)
from app.domain.enums import (
    DirecaoLancamento, MetodoOcr, NaturezaConta, OrigemClassificacao, StatusDocumento,
    TipoDocumento,
)
from tests.fakes import (
    FakeAprendizadoRepository,
    FakeArmazenamentoArquivos,
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeExtracaoRepository,
    FakeOcrResultadoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    ocr_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    aprendizado_repo = FakeAprendizadoRepository()
    storage = FakeArmazenamentoArquivos()
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    return {
        "documento_repo": documento_repo, "ocr_repo": ocr_repo, "extracao_repo": extracao_repo,
        "classificacao_repo": classificacao_repo, "conta_repo": conta_repo, "conta": conta,
        "aprendizado_repo": aprendizado_repo, "storage": storage,
    }


def _documento(ambiente, status=StatusDocumento.CONCLUIDO, documento_origem_id=None, empresa_id=1):
    caminho = f"empresa_{empresa_id}/documentos/x.pdf"
    ambiente["storage"]._arquivos[caminho] = b"conteudo"
    return ambiente["documento_repo"].criar(
        Documento(
            id=None, empresa_id=empresa_id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo=caminho, extensao=".pdf", tamanho_bytes=10, status=status,
            documento_origem_id=documento_origem_id,
        )
    )


def _com_dados_completos(ambiente, documento):
    ambiente["ocr_repo"].criar(
        OcrResultado(
            id=None, documento_id=documento.id, texto_extraido="x",
            metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=1,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None, pagador_documento=None,
            recebedor_nome="Loja X", recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=documento.empresa_id, documento_id=documento.id,
            conta_id=ambiente["conta"].id, origem=OrigemClassificacao.REGRA,
            conta_bancaria_id=99, direcao=DirecaoLancamento.PAGAMENTO,
        )
    )
    ambiente["aprendizado_repo"].criar(
        Aprendizado(
            id=None, empresa_id=documento.empresa_id, documento_id=documento.id,
            conta_anterior_id=None, origem_anterior=None,
            conta_corrigida_id=ambiente["conta"].id,
        )
    )


def _use_case_fila(ambiente):
    return LimparFilaRevisaoUseCase(
        ambiente["documento_repo"], ambiente["extracao_repo"], ambiente["classificacao_repo"],
        ambiente["conta_repo"], ambiente["aprendizado_repo"], ambiente["ocr_repo"],
        ambiente["storage"],
    )


def _use_case_processados(ambiente):
    return LimparDocumentosProcessadosUseCase(
        ambiente["documento_repo"], ambiente["ocr_repo"], ambiente["extracao_repo"],
        ambiente["classificacao_repo"], ambiente["aprendizado_repo"], ambiente["storage"],
    )


def test_limpar_fila_apaga_documento_sem_classificacao():
    ambiente = _ambiente()
    documento = _documento(ambiente)

    quantidade = _use_case_fila(ambiente).executar(1)

    assert quantidade == 1
    assert ambiente["documento_repo"].obter_por_id(documento.id) is None


def test_limpar_fila_nao_toca_documento_com_lancamento_completo():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    _com_dados_completos(ambiente, documento)

    quantidade = _use_case_fila(ambiente).executar(1)

    assert quantidade == 0
    assert ambiente["documento_repo"].obter_por_id(documento.id) is not None


def test_limpar_fila_apaga_dados_ligados_ao_documento():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None, pagador_documento=None,
            recebedor_nome="Loja X", recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )
    ambiente["ocr_repo"].criar(
        OcrResultado(
            id=None, documento_id=documento.id, texto_extraido="x",
            metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=1,
        )
    )
    caminho = documento.caminho_arquivo

    _use_case_fila(ambiente).executar(1)

    assert ambiente["extracao_repo"].obter_por_documento_id(documento.id) is None
    assert ambiente["ocr_repo"].obter_por_documento_id(documento.id) is None
    assert caminho not in ambiente["storage"]._arquivos


def test_limpar_documentos_processados_apaga_concluido_e_dividido():
    ambiente = _ambiente()
    concluido = _documento(ambiente, status=StatusDocumento.CONCLUIDO)
    dividido = _documento(ambiente, status=StatusDocumento.DIVIDIDO)
    erro = _documento(ambiente, status=StatusDocumento.ERRO)

    quantidade = _use_case_processados(ambiente).executar(1)

    assert quantidade == 3
    assert ambiente["documento_repo"].obter_por_id(concluido.id) is None
    assert ambiente["documento_repo"].obter_por_id(dividido.id) is None
    assert ambiente["documento_repo"].obter_por_id(erro.id) is None


def test_limpar_documentos_processados_nao_toca_pendente_ou_processando():
    ambiente = _ambiente()
    pendente = _documento(ambiente, status=StatusDocumento.PENDENTE)
    processando = _documento(ambiente, status=StatusDocumento.PROCESSANDO)

    quantidade = _use_case_processados(ambiente).executar(1)

    assert quantidade == 0
    assert ambiente["documento_repo"].obter_por_id(pendente.id) is not None
    assert ambiente["documento_repo"].obter_por_id(processando.id) is not None


def test_limpar_documentos_processados_apaga_filho_antes_do_pai_sem_quebrar():
    ambiente = _ambiente()
    pai = _documento(ambiente, status=StatusDocumento.DIVIDIDO)
    filho = _documento(ambiente, status=StatusDocumento.CONCLUIDO, documento_origem_id=pai.id)

    quantidade = _use_case_processados(ambiente).executar(1)

    assert quantidade == 2
    assert ambiente["documento_repo"].obter_por_id(pai.id) is None
    assert ambiente["documento_repo"].obter_por_id(filho.id) is None


def test_limpar_documentos_processados_filtra_por_empresa():
    ambiente = _ambiente()
    outra_empresa = _documento(ambiente, status=StatusDocumento.CONCLUIDO, empresa_id=2)

    quantidade = _use_case_processados(ambiente).executar(1)

    assert quantidade == 0
    assert ambiente["documento_repo"].obter_por_id(outra_empresa.id) is not None
