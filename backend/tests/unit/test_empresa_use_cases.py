import pytest

from app.application.dto import AtualizarEmpresaDTO, CriarEmpresaDTO
from app.application.use_cases.empresa_use_cases import (
    AtualizarEmpresaUseCase,
    CriarEmpresaUseCase,
    DesativarEmpresaUseCase,
    ListarEmpresasUseCase,
    ObterEmpresaUseCase,
)
from app.core.exceptions import CnpjJaCadastrado, EmpresaNaoEncontrada
from tests.fakes import FakeEmpresaRepository


def test_criar_empresa():
    repo = FakeEmpresaRepository()
    dto = CriarEmpresaDTO(razao_social="Tesserato Contabilidade", nome_fantasia="Tesserato", cnpj="12345678000199")

    empresa = CriarEmpresaUseCase(repo).executar(dto)

    assert empresa.id == 1
    assert empresa.razao_social == "Tesserato Contabilidade"
    assert empresa.ativo is True


def test_criar_empresa_com_cnpj_duplicado_falha():
    repo = FakeEmpresaRepository()
    dto = CriarEmpresaDTO(razao_social="A", nome_fantasia=None, cnpj="12345678000199")
    CriarEmpresaUseCase(repo).executar(dto)

    with pytest.raises(CnpjJaCadastrado):
        CriarEmpresaUseCase(repo).executar(dto)


def test_listar_empresas():
    repo = FakeEmpresaRepository()
    CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("A", None, "11111111000191"))
    CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("B", None, "22222222000192"))

    empresas = ListarEmpresasUseCase(repo).executar()

    assert len(empresas) == 2


def test_obter_empresa_inexistente_falha():
    repo = FakeEmpresaRepository()
    with pytest.raises(EmpresaNaoEncontrada):
        ObterEmpresaUseCase(repo).executar(999)


def test_atualizar_empresa():
    repo = FakeEmpresaRepository()
    empresa = CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("A", None, "11111111000191"))

    atualizada = AtualizarEmpresaUseCase(repo).executar(
        empresa.id, AtualizarEmpresaDTO(razao_social="A Ltda", nome_fantasia="A", ativo=True)
    )

    assert atualizada.razao_social == "A Ltda"
    assert atualizada.nome_fantasia == "A"


def test_desativar_empresa():
    repo = FakeEmpresaRepository()
    empresa = CriarEmpresaUseCase(repo).executar(CriarEmpresaDTO("A", None, "11111111000191"))

    DesativarEmpresaUseCase(repo).executar(empresa.id)

    assert repo.obter_por_id(empresa.id).ativo is False
