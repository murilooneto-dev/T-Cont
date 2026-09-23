from enum import Enum


class NaturezaConta(str, Enum):
    ATIVO = "ATIVO"
    PASSIVO = "PASSIVO"
    RECEITA = "RECEITA"
    DESPESA = "DESPESA"
    PATRIMONIO_LIQUIDO = "PATRIMONIO_LIQUIDO"


class StatusDocumento(str, Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    ERRO = "ERRO"
    DIVIDIDO = "DIVIDIDO"


class MetodoOcr(str, Enum):
    PDF_NATIVO = "PDF_NATIVO"
    PADDLEOCR = "PADDLEOCR"
    TESSERACT = "TESSERACT"


class StatusLote(str, Enum):
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
    FALHOU = "FALHOU"


class TipoDocumento(str, Enum):
    PIX = "PIX"
    TED = "TED"
    DOC = "DOC"
    BOLETO = "BOLETO"
    OUTRO = "OUTRO"


class LadoRegra(str, Enum):
    PAGADOR = "PAGADOR"
    RECEBEDOR = "RECEBEDOR"


class OrigemClassificacao(str, Enum):
    REGRA = "REGRA"
    FUZZY = "FUZZY"
    IA = "IA"
    MANUAL = "MANUAL"


class DirecaoLancamento(str, Enum):
    PAGAMENTO = "PAGAMENTO"
    RECEBIMENTO = "RECEBIMENTO"
