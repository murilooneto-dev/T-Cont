import re

from app.domain.enums import TipoDocumento

_PADROES = [
    (TipoDocumento.PIX, re.compile(r"\bPIX\b", re.IGNORECASE)),
    (TipoDocumento.TED, re.compile(r"\bTED\b", re.IGNORECASE)),
    (TipoDocumento.DOC, re.compile(r"\bDOC\b", re.IGNORECASE)),
    (TipoDocumento.BOLETO, re.compile(r"\bBOLETO\b", re.IGNORECASE)),
]


def extrair_tipo_documento(texto: str) -> TipoDocumento:
    for tipo, padrao in _PADROES:
        if padrao.search(texto):
            return tipo
    return TipoDocumento.OUTRO
