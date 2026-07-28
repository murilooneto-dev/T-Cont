import pytest

from app.application.use_cases.lote_use_cases import (
    CancelarLoteUseCase,
    IniciarProcessamentoUseCase,
    ObterStatusLoteUseCase,
)
from app.core.exceptions import (
    EmpresaNaoEncontrada,
    LoteNaoEncontrado,
    LoteNaoPodeSerCancelado,
    NenhumDocumentoPendente,
)
from app.domain.entities import Documento, Empresa
from app.domain.enums import StatusDocumento, StatusLote
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

    lote, documento_ids = IniciarProcessamentoUseCase(
        documento_repo, lote_repo, empresa_repo
    ).executar(empresa.id)

    assert lote.total_documentos == 2
    assert lote.status == StatusLote.EM_ANDAMENTO
    assert sorted(documento_ids) == [1, 2]


def test_iniciar_processamento_marca_documentos_como_processando():
    """Sem a reivindicação, um duplo clique em "Processar" criava um segundo
    lote sobre os mesmos documentos e estourava a UNIQUE de ocr_resultados."""
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    documento = _documento_pendente(documento_repo, empresa.id)
    lote_repo = FakeLoteProcessamentoRepository()

    IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa.id)

    assert documento_repo.obter_por_id(documento.id).status == StatusDocumento.PROCESSANDO
    assert documento_repo.listar_pendentes_por_empresa(empresa.id) == []


def test_segunda_chamada_de_iniciar_processamento_nao_cria_lote_duplicado():
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    _documento_pendente(documento_repo, empresa.id)
    lote_repo = FakeLoteProcessamentoRepository()
    use_case = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo)
    use_case.executar(empresa.id)

    with pytest.raises(NenhumDocumentoPendente):
        use_case.executar(empresa.id)


def test_iniciar_processamento_sem_documentos_pendentes_nao_cria_lote():
    """Antes, criava um lote com total_documentos=0 que ficava preso em
    EM_ANDAMENTO para sempre (o router só pulava o agendamento do worker)."""
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    lote_repo = FakeLoteProcessamentoRepository()

    with pytest.raises(NenhumDocumentoPendente):
        IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(empresa.id)

    assert lote_repo.obter_por_id(1) is None


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


def _lote_em_andamento(lote_repo):
    empresa_repo = FakeEmpresaRepository()
    empresa = _empresa(empresa_repo)
    documento_repo = FakeDocumentoRepository()
    _documento_pendente(documento_repo, empresa.id)
    lote, _ = IniciarProcessamentoUseCase(documento_repo, lote_repo, empresa_repo).executar(
        empresa.id
    )
    return lote


def test_cancelar_lote_muda_status_para_cancelado():
    lote_repo = FakeLoteProcessamentoRepository()
    lote = _lote_em_andamento(lote_repo)

    cancelado = CancelarLoteUseCase(lote_repo).executar(lote.id)

    assert cancelado.status == StatusLote.CANCELADO


@pytest.mark.parametrize("status", [StatusLote.CONCLUIDO, StatusLote.CANCELADO, StatusLote.FALHOU])
def test_cancelar_lote_em_estado_terminal_falha(status):
    lote_repo = FakeLoteProcessamentoRepository()
    lote = _lote_em_andamento(lote_repo)
    lote.status = status
    lote_repo.atualizar(lote)

    with pytest.raises(LoteNaoPodeSerCancelado):
        CancelarLoteUseCase(lote_repo).executar(lote.id)

    assert lote_repo.obter_por_id(lote.id).status == status
