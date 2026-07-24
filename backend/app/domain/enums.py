from enum import Enum


class NaturezaConta(str, Enum):
    ATIVO = "ATIVO"
    PASSIVO = "PASSIVO"
    RECEITA = "RECEITA"
    DESPESA = "DESPESA"
    PATRIMONIO_LIQUIDO = "PATRIMONIO_LIQUIDO"
