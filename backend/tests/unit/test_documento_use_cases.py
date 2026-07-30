import pytest

from app.application.dto import ArquivoUploadDTO
from app.application.use_cases.documento_use_cases import (
    ListarDocumentosUseCase,
    ObterResultadoUseCase,
    UploadarDocumentosUseCase,
)
from app.core.exceptions import DocumentoNaoEncontrado, EmpresaNaoEncontrada
from app.domain.entities import Classificacao, Empresa, Extracao
from app.domain.enums import OrigemClassificacao, TipoDocumento
from tests.fakes import (
    FakeArmazenamentoArquivos,
    FakeClassificacaoRepository,
    FakeDocumentoRepository,
    FakeEmpresaRepository,
    FakeExtracaoRepository,
    FakeOcrResultadoRepository,
)


def _empresa(repo):
    return repo.criar(Empresa(id=None, razao_social="A", nome_fantasia=None, cnpj="11111111000191"))


def test_upload_cria_documentos_para_arquivos_validos():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()

    resultados = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="comprovante.pdf", conteudo=b"conteudo")]
    )

    assert len(resultados) == 1
    assert resultados[0].erro is None
    assert resultados[0].documento.nome_exibicao == "comprovante.pdf"
    assert resultados[0].documento.status.value == "PENDENTE"


def test_upload_com_extensao_invalida_reporta_erro_sem_criar_documento():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()

    resultados = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="virus.exe", conteudo=b"x")]
    )

    assert resultados[0].documento is None
    assert resultados[0].erro is not None
    assert documento_repo.listar_por_empresa(empresa.id) == []


def test_upload_para_empresa_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()
    empresa_repo = FakeEmpresaRepository()

    with pytest.raises(EmpresaNaoEncontrada):
        UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
            999, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
        )


def test_listar_documentos_por_empresa():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    storage = FakeArmazenamentoArquivos()
    UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )

    documentos = ListarDocumentosUseCase(documento_repo).executar(empresa.id)

    assert len(documentos) == 1


def test_obter_resultado_documento_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()

    with pytest.raises(DocumentoNaoEncontrado):
        ObterResultadoUseCase(
            documento_repo, resultado_repo, extracao_repo, classificacao_repo
        ).executar(999)


def test_obter_resultado_retorna_extracao_quando_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id
    extracao_repo.criar(
        Extracao(
            id=None, documento_id=documento_id, pagador_nome="JOAO", pagador_documento=None,
            recebedor_nome=None, recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    documento, resultado, extracao, _ = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo, classificacao_repo
    ).executar(documento_id)

    assert resultado is None
    assert extracao is not None
    assert extracao.pagador_nome == "JOAO"


def test_obter_resultado_extracao_none_quando_nao_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id

    _, _, extracao, _ = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo, classificacao_repo
    ).executar(documento_id)

    assert extracao is None


def test_obter_resultado_retorna_classificacao_quando_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id
    classificacao_repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento_id, conta_id=10,
            origem=OrigemClassificacao.REGRA, regra_id=1,
        )
    )

    _, _, _, classificacao = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo, classificacao_repo
    ).executar(documento_id)

    assert classificacao is not None
    assert classificacao.conta_id == 10


def test_obter_resultado_classificacao_none_quando_nao_existe():
    documento_repo = FakeDocumentoRepository()
    resultado_repo = FakeOcrResultadoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    storage = FakeArmazenamentoArquivos()
    resultados_upload = UploadarDocumentosUseCase(documento_repo, empresa_repo, storage).executar(
        empresa.id, [ArquivoUploadDTO(nome_original="a.pdf", conteudo=b"x")]
    )
    documento_id = resultados_upload[0].documento.id

    _, _, _, classificacao = ObterResultadoUseCase(
        documento_repo, resultado_repo, extracao_repo, classificacao_repo
    ).executar(documento_id)

    assert classificacao is None
