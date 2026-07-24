from abc import ABC, abstractmethod

from app.domain.entities import Conta, Empresa, PlanoContas


class EmpresaRepository(ABC):
    @abstractmethod
    def criar(self, empresa: Empresa) -> Empresa: ...

    @abstractmethod
    def obter_por_id(self, empresa_id: int) -> Empresa | None: ...

    @abstractmethod
    def obter_por_cnpj(self, cnpj: str) -> Empresa | None: ...

    @abstractmethod
    def listar(self) -> list[Empresa]: ...

    @abstractmethod
    def atualizar(self, empresa: Empresa) -> Empresa: ...


class PlanoContasRepository(ABC):
    @abstractmethod
    def criar(self, plano: PlanoContas) -> PlanoContas: ...

    @abstractmethod
    def obter_por_id(self, plano_id: int) -> PlanoContas | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]: ...


class ContaRepository(ABC):
    @abstractmethod
    def criar(self, conta: Conta) -> Conta: ...

    @abstractmethod
    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]: ...

    @abstractmethod
    def obter_por_id(self, conta_id: int) -> Conta | None: ...

    @abstractmethod
    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]: ...

    @abstractmethod
    def atualizar(self, conta: Conta) -> Conta: ...

    @abstractmethod
    def deletar(self, conta_id: int) -> None: ...
