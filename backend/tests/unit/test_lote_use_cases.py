import pytest

from app.application.use_cases.lote_use_cases import (
    CancelarLoteUseCase,
    IniciarProcessamentoUseCase,
    ObterStatusLoteUseCase,
)
from app.core.exceptions import EmpresaNaoEncontrada, LoteNaoEncontrado
from app.domain.entities import Documento, Empresa
from app.domain.enums import StatusLote
from tests.fakes import FakeDocumentoRepository, FakeEmpresaRepository, FakeLoteProcessamentoRepository


def _empresa(repo):
    return repo.criar(Empresa(id=None, razao_social="A", nome_fantasia=None, cnpj="11111111000191"))


def _documento_pendente(repo, empresa_id):
    return repo.criar(
        Documento(
            id=None, empresa_id=empresa_id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )


def test_iniciar_processamento_cria_lote_com_total_de_documentos_pendentes():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    _documento_pendente(documento_repo, empresa.id)
    _documento_pendente(documento_repo, empresa.id)
    lote_repo = FakeLoteProcessamentoRepository()

    lote = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa.id)

    assert lote.total_documentos == 2
    assert lote.status == StatusLote.EM_ANDAMENTO


def test_iniciar_processamento_empresa_inexistente_falha():
    documento_repo = FakeDocumentoRepository()
    lote_repo = FakeLoteProcessamentoRepository()
    empresa_repo = FakeEmpresaRepository()

    with pytest.raises(EmpresaNaoEncontrada):
        IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(999)


def test_obter_status_lote_inexistente_falha():
    lote_repo = FakeLoteProcessamentoRepository()

    with pytest.raises(LoteNaoEncontrado):
        ObterStatusLoteUseCase(lote_repo).executar(999)


def test_cancelar_lote_muda_status_para_cancelado():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    _documento_pendente(documento_repo, empresa.id)
    lote_repo = FakeLoteProcessamentoRepository()
    lote = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa.id)

    cancelado = CancelarLoteUseCase(lote_repo).executar(lote.id)

    assert cancelado.status == StatusLote.CANCELADO
