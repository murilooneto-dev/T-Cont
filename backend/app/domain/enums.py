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


class MetodoOcr(str, Enum):
    PDF_NATIVO = "PDF_NATIVO"
    PADDLEOCR = "PADDLEOCR"
    TESSERACT = "TESSERACT"


class StatusLote(str, Enum):
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
