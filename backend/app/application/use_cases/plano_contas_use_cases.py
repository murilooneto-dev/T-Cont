from app.application.dto import CriarPlanoContasDTO
from app.application.repositories import EmpresaRepository, PlanoContasRepository
from app.core.exceptions import EmpresaNaoEncontrada
from app.domain.entities import PlanoContas


class CriarPlanoContasUseCase:
    def __init__(self, repo: PlanoContasRepository, empresa_repo: EmpresaRepository):
        self._repo = repo
        self._empresa_repo = empresa_repo

    def executar(self, empresa_id: int, dto: CriarPlanoContasDTO) -> PlanoContas:
        if self._empresa_repo.obter_por_id(empresa_id) is None:
            raise EmpresaNaoEncontrada(empresa_id)
        plano = PlanoContas(id=None, empresa_id=empresa_id, nome=dto.nome)
        return self._repo.criar(plano)


class ListarPlanosContasUseCase:
    def __init__(self, repo: PlanoContasRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> list[PlanoContas]:
        return self._repo.listar_por_empresa(empresa_id)
