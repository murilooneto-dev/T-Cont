from app.application.dto import AtualizarEmpresaDTO, CriarEmpresaDTO
from app.application.repositories import EmpresaRepository
from app.core.exceptions import CnpjJaCadastrado, EmpresaNaoEncontrada
from app.domain.entities import Empresa


class CriarEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, dto: CriarEmpresaDTO) -> Empresa:
        if self._repo.obter_por_cnpj(dto.cnpj) is not None:
            raise CnpjJaCadastrado(dto.cnpj)
        empresa = Empresa(
            id=None,
            razao_social=dto.razao_social,
            nome_fantasia=dto.nome_fantasia,
            cnpj=dto.cnpj,
        )
        return self._repo.criar(empresa)


class ListarEmpresasUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self) -> list[Empresa]:
        return self._repo.listar()


class ObterEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> Empresa:
        empresa = self._repo.obter_por_id(empresa_id)
        if empresa is None:
            raise EmpresaNaoEncontrada(empresa_id)
        return empresa


class AtualizarEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, empresa_id: int, dto: AtualizarEmpresaDTO) -> Empresa:
        empresa = ObterEmpresaUseCase(self._repo).executar(empresa_id)
        empresa.razao_social = dto.razao_social
        empresa.nome_fantasia = dto.nome_fantasia
        empresa.ativo = dto.ativo
        return self._repo.atualizar(empresa)


class DesativarEmpresaUseCase:
    def __init__(self, repo: EmpresaRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> None:
        empresa = ObterEmpresaUseCase(self._repo).executar(empresa_id)
        empresa.ativo = False
        self._repo.atualizar(empresa)
