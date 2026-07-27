import pytest

from app.application.dto import CriarEmpresaDTO, CriarPlanoContasDTO
from app.application.use_cases.empresa_use_cases import CriarEmpresaUseCase
from app.application.use_cases.plano_contas_use_cases import (
    CriarPlanoContasUseCase,
    ListarPlanosContasUseCase,
)
from app.core.exceptions import EmpresaNaoEncontrada
from tests.fakes import FakeEmpresaRepository, FakePlanoContasRepository


@pytest.fixture
def empresa_repo():
    repo = FakeEmpresaRepository()
    CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("Empresa 1", None, "12345678000199"))
    CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("Empresa 2", None, "12345678000198"))
    return repo


def test_criar_plano_contas(empresa_repo):
    repo = FakePlanoContasRepository()
    plano = CriarPlanoContasUseCase(repo, empresa_repo).executar(
        1, CriarPlanoContasDTO(nome="Plano Padrão")
    )

    assert plano.id == 1
    assert plano.empresa_id == 1
    assert plano.nome == "Plano Padrão"


def test_criar_plano_contas_para_empresa_inexistente_falha(empresa_repo):
    repo = FakePlanoContasRepository()

    with pytest.raises(EmpresaNaoEncontrada):
        CriarPlanoContasUseCase(repo, empresa_repo).executar(
            999, CriarPlanoContasDTO(nome="Plano Órfão")
        )

    assert repo.listar_por_empresa(999) == []


def test_listar_planos_por_empresa(empresa_repo):
    repo = FakePlanoContasRepository()
    CriarPlanoContasUseCase(repo, empresa_repo).executar(1, CriarPlanoContasDTO(nome="Plano A"))
    CriarPlanoContasUseCase(repo, empresa_repo).executar(2, CriarPlanoContasDTO(nome="Plano B"))

    planos = ListarPlanosContasUseCase(repo).executar(1)

    assert len(planos) == 1
    assert planos[0].nome == "Plano A"
