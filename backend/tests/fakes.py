from app.application.repositories import (
    ContaRepository,
    EmpresaRepository,
    PlanoContasRepository,
)
from app.domain.entities import Conta, Empresa, PlanoContas


class FakeEmpresaRepository(EmpresaRepository):
    def __init__(self):
        self._items: dict[int, Empresa] = {}
        self._next_id = 1

    def criar(self, empresa: Empresa) -> Empresa:
        empresa.id = self._next_id
        self._items[self._next_id] = empresa
        self._next_id += 1
        return empresa

    def obter_por_id(self, empresa_id: int) -> Empresa | None:
        return self._items.get(empresa_id)

    def obter_por_cnpj(self, cnpj: str) -> Empresa | None:
        return next((e for e in self._items.values() if e.cnpj == cnpj), None)

    def listar(self) -> list[Empresa]:
        return list(self._items.values())

    def atualizar(self, empresa: Empresa) -> Empresa:
        self._items[empresa.id] = empresa
        return empresa


class FakePlanoContasRepository(PlanoContasRepository):
    def __init__(self):
        self._items: dict[int, PlanoContas] = {}
        self._next_id = 1

    def criar(self, plano: PlanoContas) -> PlanoContas:
        plano.id = self._next_id
        self._items[self._next_id] = plano
        self._next_id += 1
        return plano

    def obter_por_id(self, plano_id: int) -> PlanoContas | None:
        return self._items.get(plano_id)

    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]:
        return [p for p in self._items.values() if p.empresa_id == empresa_id]


class FakeContaRepository(ContaRepository):
    def __init__(self):
        self._items: dict[int, Conta] = {}
        self._next_id = 1

    def criar(self, conta: Conta) -> Conta:
        conta.id = self._next_id
        self._items[self._next_id] = conta
        self._next_id += 1
        return conta

    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]:
        return [self.criar(c) for c in contas]

    def obter_por_id(self, conta_id: int) -> Conta | None:
        return self._items.get(conta_id)

    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]:
        return [c for c in self._items.values() if c.plano_conta_id == plano_conta_id]

    def atualizar(self, conta: Conta) -> Conta:
        self._items[conta.id] = conta
        return conta

    def deletar(self, conta_id: int) -> None:
        self._items.pop(conta_id, None)
