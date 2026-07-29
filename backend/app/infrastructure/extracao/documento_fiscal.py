import re

_PADRAO_DOCUMENTO = re.compile(
    r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2}"
)


def _normalizar_documento(bruto: str) -> str:
    return re.sub(r"\D", "", bruto)


def extrair_documentos(texto: str) -> list[str]:
    encontrados: list[str] = []
    for match in _PADRAO_DOCUMENTO.finditer(texto):
        digitos = _normalizar_documento(match.group())
        if len(digitos) in (11, 14) and digitos not in encontrados:
            encontrados.append(digitos)
    return encontrados
