import pytest

from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.use_cases.conta_use_cases import (
    AtualizarContaUseCase,
    CriarContaUseCase,
    DeletarContaUseCase,
    ListarContasUseCase,
)
from app.core.exceptions import (
    ContaJaCadastrada,
    ContaNaoEncontrada,
    PlanoContasNaoEncontrado,
)
from app.domain.entities import PlanoContas
from tests.fakes import FakeContaRepository, FakePlanoContasRepository


@pytest.fixture
def plano_repo():
    repo = FakePlanoContasRepository()
    repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano 1"))
    repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano 2"))
    return repo


def test_criar_conta(plano_repo):
    repo = FakeContaRepository()
    dto = CriarContaDTO(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True)

    conta = CriarContaUseCase(repo, plano_repo).executar(1, dto)

    assert conta.id == 1
    assert conta.codigo == "1.1.01"
    assert conta.natureza.value == "ATIVO"


def test_listar_contas_por_plano(plano_repo):
    repo = FakeContaRepository()
    CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1", "Disponibilidades", "ATIVO", False))
    CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))
    CriarContaUseCase(repo, plano_repo).executar(2, CriarContaDTO("2.1", "Fornecedores", "PASSIVO", True))

    contas = ListarContasUseCase(repo).executar(1)

    assert len(contas) == 2


def test_atualizar_conta(plano_repo):
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    atualizada = AtualizarContaUseCase(repo).executar(
        conta.id, AtualizarContaDTO("1.1.01", "Caixa e Equivalentes", "ATIVO", True)
    )

    assert atualizada.descricao == "Caixa e Equivalentes"


def test_deletar_conta(plano_repo):
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    DeletarContaUseCase(repo).executar(conta.id)

    assert repo.obter_por_id(conta.id) is None


def test_atualizar_conta_inexistente_falha():
    repo = FakeContaRepository()
    with pytest.raises(ContaNaoEncontrada):
        AtualizarContaUseCase(repo).executar(999, AtualizarContaDTO("1", "x", "ATIVO", True))


def test_criar_conta_em_plano_inexistente_falha(plano_repo):
    repo = FakeContaRepository()
    dto = CriarContaDTO(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True)

    with pytest.raises(PlanoContasNaoEncontrado):
        CriarContaUseCase(repo, plano_repo).executar(999, dto)

    assert repo.listar_por_plano(999) == []


def test_criar_conta_com_codigo_duplicado_no_mesmo_plano_falha(plano_repo):
    repo = FakeContaRepository()
    dto = CriarContaDTO(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True)

    CriarContaUseCase(repo, plano_repo).executar(1, dto)

    with pytest.raises(ContaJaCadastrada):
        CriarContaUseCase(repo, plano_repo).executar(1, dto)

    assert len(repo.listar_por_plano(1)) == 1
    # O mesmo código em outro plano continua permitido.
    CriarContaUseCase(repo, plano_repo).executar(2, dto)
    assert len(repo.listar_por_plano(2)) == 1


def test_criar_conta_com_conta_pai_inexistente_falha(plano_repo):
    repo = FakeContaRepository()
    dto = CriarContaDTO(
        codigo="1.1.01", descricao="Caixa", natureza="ATIVO",
        conta_analitica=True, conta_pai_id=999,
    )

    with pytest.raises(ContaNaoEncontrada):
        CriarContaUseCase(repo, plano_repo).executar(1, dto)

    assert repo.listar_por_plano(1) == []


def test_criar_conta_com_conta_pai_de_outro_plano_falha(plano_repo):
    repo = FakeContaRepository()
    pai = CriarContaUseCase(repo, plano_repo).executar(
        2, CriarContaDTO(codigo="1", descricao="Ativo", natureza="ATIVO", conta_analitica=False)
    )
    dto = CriarContaDTO(
        codigo="1.1.01", descricao="Caixa", natureza="ATIVO",
        conta_analitica=True, conta_pai_id=pai.id,
    )

    with pytest.raises(ContaNaoEncontrada):
        CriarContaUseCase(repo, plano_repo).executar(1, dto)

    assert repo.listar_por_plano(1) == []


def test_atualizar_conta_com_codigo_duplicado_no_mesmo_plano_falha(plano_repo):
    repo = FakeContaRepository()
    CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1", "Disponibilidades", "ATIVO", False))
    conta2 = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.2", "Bancos", "ATIVO", True))

    with pytest.raises(ContaJaCadastrada):
        AtualizarContaUseCase(repo).executar(
            conta2.id, AtualizarContaDTO("1.1", "Bancos", "ATIVO", True)
        )

    assert repo.obter_por_id(conta2.id).codigo == "1.2"


def test_atualizar_conta_mantendo_o_proprio_codigo_nao_autocolide(plano_repo):
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    atualizada = AtualizarContaUseCase(repo).executar(
        conta.id, AtualizarContaDTO("1.1.01", "Caixa Atualizado", "ATIVO", True)
    )

    assert atualizada.codigo == "1.1.01"
    assert atualizada.descricao == "Caixa Atualizado"


def test_atualizar_conta_com_conta_pai_inexistente_falha(plano_repo):
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    with pytest.raises(ContaNaoEncontrada):
        AtualizarContaUseCase(repo).executar(
            conta.id, AtualizarContaDTO("1.1.01", "Caixa", "ATIVO", True, conta_pai_id=999)
        )

    assert repo.obter_por_id(conta.id).conta_pai_id is None


def test_atualizar_conta_com_conta_pai_de_outro_plano_falha(plano_repo):
    repo = FakeContaRepository()
    pai = CriarContaUseCase(repo, plano_repo).executar(
        2, CriarContaDTO(codigo="1", descricao="Ativo", natureza="ATIVO", conta_analitica=False)
    )
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    with pytest.raises(ContaNaoEncontrada):
        AtualizarContaUseCase(repo).executar(
            conta.id, AtualizarContaDTO("1.1.01", "Caixa", "ATIVO", True, conta_pai_id=pai.id)
        )

    assert repo.obter_por_id(conta.id).conta_pai_id is None


def test_atualizar_conta_com_conta_pai_igual_a_propria_conta_falha(plano_repo):
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    with pytest.raises(ContaNaoEncontrada):
        AtualizarContaUseCase(repo).executar(
            conta.id, AtualizarContaDTO("1.1.01", "Caixa", "ATIVO", True, conta_pai_id=conta.id)
        )

    assert repo.obter_por_id(conta.id).conta_pai_id is None


def test_atualizar_conta_com_conta_pai_valida_no_mesmo_plano_funciona(plano_repo):
    repo = FakeContaRepository()
    pai = CriarContaUseCase(repo, plano_repo).executar(
        1, CriarContaDTO(codigo="1", descricao="Ativo", natureza="ATIVO", conta_analitica=False)
    )
    conta = CriarContaUseCase(repo, plano_repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    atualizada = AtualizarContaUseCase(repo).executar(
        conta.id, AtualizarContaDTO("1.1.01", "Caixa", "ATIVO", True, conta_pai_id=pai.id)
    )

    assert atualizada.conta_pai_id == pai.id
