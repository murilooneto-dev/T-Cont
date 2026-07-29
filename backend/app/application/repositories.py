from abc import ABC, abstractmethod

from app.domain.entities import (
    Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado, PlanoContas,
)


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


class DocumentoRepository(ABC):
    @abstractmethod
    def criar(self, documento: Documento) -> Documento: ...

    @abstractmethod
    def obter_por_id(self, documento_id: int) -> Documento | None: ...

    @abstractmethod
    def listar_por_empresa(self, empresa_id: int) -> list[Documento]: ...

    @abstractmethod
    def listar_pendentes_por_empresa(self, empresa_id: int) -> list[Documento]: ...

    @abstractmethod
    def atualizar(self, documento: Documento) -> Documento: ...


class OcrResultadoRepository(ABC):
    @abstractmethod
    def criar(self, resultado: OcrResultado) -> OcrResultado: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> OcrResultado | None: ...


class LoteProcessamentoRepository(ABC):
    @abstractmethod
    def criar(self, lote: LoteProcessamento) -> LoteProcessamento: ...

    @abstractmethod
    def obter_por_id(self, lote_id: int) -> LoteProcessamento | None: ...

    @abstractmethod
    def atualizar(self, lote: LoteProcessamento) -> LoteProcessamento: ...


class ExtracaoRepository(ABC):
    @abstractmethod
    def criar(self, extracao: Extracao) -> Extracao: ...

    @abstractmethod
    def obter_por_documento_id(self, documento_id: int) -> Extracao | None: ...
