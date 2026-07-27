class DomainError(Exception):
    """Base class for domain/application errors."""


class EmpresaNaoEncontrada(DomainError):
    def __init__(self, empresa_id: int):
        super().__init__(f"Empresa {empresa_id} não encontrada.")


class CnpjJaCadastrado(DomainError):
    def __init__(self, cnpj: str):
        super().__init__(f"CNPJ {cnpj} já cadastrado.")


class PlanoContasNaoEncontrado(DomainError):
    def __init__(self, plano_id: int):
        super().__init__(f"Plano de Contas {plano_id} não encontrado.")


class ContaJaCadastrada(DomainError):
    def __init__(self, codigo: str, plano_id: int):
        super().__init__(
            f"A conta {codigo} já existe no plano de contas {plano_id}."
        )


class ContaNaoEncontrada(DomainError):
    def __init__(self, conta_id: int, contexto: str = "Conta"):
        super().__init__(f"{contexto} {conta_id} não encontrada.")


class ImportacaoPlanoContasInvalida(DomainError):
    def __init__(self, motivo: str):
        super().__init__(motivo)
