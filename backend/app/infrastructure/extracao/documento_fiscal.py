import re

PADRAO_DOCUMENTO_FISCAL = re.compile(
    r"(?<!\d)(?:\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)"
)

_ROTULOS_PAGADOR = ["PAGADOR", "DE"]
_ROTULOS_RECEBEDOR = ["RECEBEDOR", "FAVORECIDO", "PARA", "BENEFICIARIO", "BENEFICIÁRIO"]
_TODOS_ROTULOS = sorted(set(_ROTULOS_PAGADOR + _ROTULOS_RECEBEDOR), key=len, reverse=True)
_PADRAO_ROTULO = re.compile(
    r"\b(?:" + "|".join(re.escape(r) for r in _TODOS_ROTULOS) + r")\s*:", re.IGNORECASE
)


def _normalizar_documento(bruto: str) -> str:
    return re.sub(r"\D", "", bruto)


def extrair_documentos(texto: str) -> list[str]:
    encontrados: list[str] = []
    for match in PADRAO_DOCUMENTO_FISCAL.finditer(texto):
        digitos = _normalizar_documento(match.group())
        if len(digitos) in (11, 14) and digitos not in encontrados:
            encontrados.append(digitos)
    return encontrados


def _extrair_documento_apos_rotulos(texto: str, rotulos: list[str]) -> str | None:
    padrao_alvo = re.compile(
        r"\b(?:" + "|".join(re.escape(r) for r in rotulos) + r")\s*:", re.IGNORECASE
    )
    for match_rotulo in padrao_alvo.finditer(texto):
        inicio = match_rotulo.end()
        proximo_rotulo = _PADRAO_ROTULO.search(texto, inicio)
        fim = proximo_rotulo.start() if proximo_rotulo else len(texto)
        documentos = extrair_documentos(texto[inicio:fim])
        if documentos:
            return documentos[0]
    return None


def extrair_documento_pagador(texto: str) -> str | None:
    return _extrair_documento_apos_rotulos(texto, _ROTULOS_PAGADOR)


def extrair_documento_recebedor(texto: str) -> str | None:
    return _extrair_documento_apos_rotulos(texto, _ROTULOS_RECEBEDOR)
