import re

from app.domain.enums import TipoDocumento

_PADROES = [
    (TipoDocumento.PIX, re.compile(r"\bPIXS?\b", re.IGNORECASE)),
    (TipoDocumento.TED, re.compile(r"\bTEDS?\b", re.IGNORECASE)),
    (TipoDocumento.DOC, re.compile(r"\bDOCS?\b", re.IGNORECASE)),
    (TipoDocumento.BOLETO, re.compile(r"\bBOLETOS?\b", re.IGNORECASE)),
]


def extrair_tipo_documento(texto: str) -> TipoDocumento:
    for tipo, padrao in _PADROES:
        if padrao.search(texto):
            return tipo
    return TipoDocumento.OUTRO
