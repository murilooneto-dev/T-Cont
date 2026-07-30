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


class ArquivoInvalido(DomainError):
    def __init__(self, motivo: str):
        super().__init__(motivo)


class DocumentoNaoEncontrado(DomainError):
    def __init__(self, documento_id: int):
        super().__init__(f"Documento {documento_id} não encontrado.")


class LoteNaoEncontrado(DomainError):
    def __init__(self, lote_id: int):
        super().__init__(f"Lote de processamento {lote_id} não encontrado.")


class NenhumDocumentoPendente(DomainError):
    def __init__(self, empresa_id: int):
        super().__init__(
            f"A empresa {empresa_id} não possui documentos pendentes para processar."
        )


class LoteNaoPodeSerCancelado(DomainError):
    def __init__(self, lote_id: int, status: str):
        super().__init__(
            f"O lote {lote_id} não pode ser cancelado porque já está {status}."
        )


class ContaNaoPertenceAEmpresa(DomainError):
    def __init__(self, conta_id: int, empresa_id: int):
        super().__init__(
            f"A conta {conta_id} não pertence a um plano de contas da empresa {empresa_id}."
        )


class ContaNaoAnalitica(DomainError):
    def __init__(self, motivo: str):
        super().__init__(motivo)


class RegraNaoEncontrada(DomainError):
    def __init__(self, regra_id: int):
        super().__init__(f"Regra {regra_id} não encontrada.")


class RegraSemCondicoes(DomainError):
    def __init__(self):
        super().__init__(
            "A regra precisa de pelo menos uma condição preenchida "
            "(documento fiscal, tipo de documento, faixa de valor ou palavra-chave)."
        )


class RegraSemLadoAlvo(DomainError):
    def __init__(self):
        super().__init__(
            "É necessário informar o lado alvo (pagador/recebedor) quando a regra usa "
            "documento fiscal ou palavra-chave no nome."
        )
