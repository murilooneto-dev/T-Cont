import pytest

from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.use_cases.conta_use_cases import (
    AtualizarContaUseCase,
    CriarContaUseCase,
    DeletarContaUseCase,
    ListarContasUseCase,
)
from app.core.exceptions import ContaNaoEncontrada
from tests.fakes import FakeContaRepository


def test_criar_conta():
    repo = FakeContaRepository()
    dto = CriarContaDTO(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True)

    conta = CriarContaUseCase(repo).executar(1, dto)

    assert conta.id == 1
    assert conta.codigo == "1.1.01"
    assert conta.natureza.value == "ATIVO"


def test_listar_contas_por_plano():
    repo = FakeContaRepository()
    CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1", "Disponibilidades", "ATIVO", False))
    CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))
    CriarContaUseCase(repo).executar(2, CriarContaDTO("2.1", "Fornecedores", "PASSIVO", True))

    contas = ListarContasUseCase(repo).executar(1)

    assert len(contas) == 2


def test_atualizar_conta():
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    atualizada = AtualizarContaUseCase(repo).executar(
        conta.id, AtualizarContaDTO("1.1.01", "Caixa e Equivalentes", "ATIVO", True)
    )

    assert atualizada.descricao == "Caixa e Equivalentes"


def test_deletar_conta():
    repo = FakeContaRepository()
    conta = CriarContaUseCase(repo).executar(1, CriarContaDTO("1.1.01", "Caixa", "ATIVO", True))

    DeletarContaUseCase(repo).executar(conta.id)

    assert repo.obter_por_id(conta.id) is None


def test_atualizar_conta_inexistente_falha():
    repo = FakeContaRepository()
    with pytest.raises(ContaNaoEncontrada):
        AtualizarContaUseCase(repo).executar(999, AtualizarContaDTO("1", "x", "ATIVO", True))
