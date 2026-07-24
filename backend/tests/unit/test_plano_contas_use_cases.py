from app.application.dto import CriarPlanoContasDTO
from app.application.use_cases.plano_contas_use_cases import (
    CriarPlanoContasUseCase,
    ListarPlanosContasUseCase,
)
from tests.fakes import FakePlanoContasRepository


def test_criar_plano_contas():
    repo = FakePlanoContasRepository()
    plano = CriarPlanoContasUseCase(repo).executar(1, CriarPlanoContasDTO(nome="Plano Padrão"))

    assert plano.id == 1
    assert plano.empresa_id == 1
    assert plano.nome == "Plano Padrão"


def test_listar_planos_por_empresa():
    repo = FakePlanoContasRepository()
    CriarPlanoContasUseCase(repo).executar(1, CriarPlanoContasDTO(nome="Plano A"))
    CriarPlanoContasUseCase(repo).executar(2, CriarPlanoContasDTO(nome="Plano B"))

    planos = ListarPlanosContasUseCase(repo).executar(1)

    assert len(planos) == 1
    assert planos[0].nome == "Plano A"
