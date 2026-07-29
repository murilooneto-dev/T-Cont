import re

_ROTULOS_PAGADOR = ["PAGADOR", "DE"]
_ROTULOS_RECEBEDOR = ["RECEBEDOR", "FAVORECIDO", "PARA", "BENEFICIARIO", "BENEFICIÁRIO"]

_SUFIXOS_SOCIETARIOS = re.compile(
    r"\b(LTDA\.?|ME\.?|EIRELI\.?|S\.?A\.?|S/A)\b\.?", re.IGNORECASE
)


def _normalizar_nome(bruto: str) -> str:
    nome = bruto.strip()
    nome = re.sub(r"\s+", " ", nome)
    nome = _SUFIXOS_SOCIETARIOS.sub("", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome.upper()


def _extrair_por_rotulos(texto: str, rotulos: list[str]) -> str | None:
    for rotulo in rotulos:
        padrao = re.compile(rf"{rotulo}\s*:\s*([^\n]+)", re.IGNORECASE)
        match = padrao.search(texto)
        if match:
            nome = _normalizar_nome(match.group(1))
            if nome:
                return nome
    return None


def extrair_pagador(texto: str) -> str | None:
    return _extrair_por_rotulos(texto, _ROTULOS_PAGADOR)


def extrair_recebedor(texto: str) -> str | None:
    return _extrair_por_rotulos(texto, _ROTULOS_RECEBEDOR)
