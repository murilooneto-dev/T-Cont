import re

from app.infrastructure.extracao.documento_fiscal import PADRAO_DOCUMENTO_FISCAL

_ROTULOS_PAGADOR = ["PAGADOR", "DE"]
_ROTULOS_RECEBEDOR = ["RECEBEDOR", "FAVORECIDO", "PARA", "BENEFICIARIO", "BENEFICIÁRIO"]

_SUFIXOS_SOCIETARIOS = re.compile(
    r"\b(LTDA\.?|ME\.?|EIRELI\.?|S\.?A\.?|S/A)\b\.?", re.IGNORECASE
)

_TODOS_ROTULOS = sorted(set(_ROTULOS_PAGADOR + _ROTULOS_RECEBEDOR), key=len, reverse=True)
_PADRAO_PROXIMO_ROTULO = re.compile(
    r"\b(?:" + "|".join(re.escape(r) for r in _TODOS_ROTULOS) + r")\s*:", re.IGNORECASE
)

_MARCADORES_CAMPO = ["CPF", "CNPJ", "AGENCIA", "AGÊNCIA", "CONTA", "VALOR", "DATA", "BANCO"]
_PADRAO_MARCADOR_CAMPO = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in _MARCADORES_CAMPO) + r")\b", re.IGNORECASE
)


def _normalizar_nome(bruto: str) -> str:
    nome = bruto.strip()
    nome = re.sub(r"\s+", " ", nome)
    nome = _SUFIXOS_SOCIETARIOS.sub("", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome.upper()


def _truncar_no_proximo_rotulo(bruto: str) -> str:
    pontos_de_corte = []
    for padrao in (_PADRAO_PROXIMO_ROTULO, _PADRAO_MARCADOR_CAMPO, PADRAO_DOCUMENTO_FISCAL):
        match = padrao.search(bruto)
        if match:
            pontos_de_corte.append(match.start())
    if pontos_de_corte:
        return bruto[: min(pontos_de_corte)]
    return bruto


def _extrair_por_rotulos(texto: str, rotulos: list[str]) -> str | None:
    for rotulo in rotulos:
        padrao = re.compile(rf"\b{rotulo}\s*:\s*([^\n]+)", re.IGNORECASE)
        match = padrao.search(texto)
        if match:
            bruto = _truncar_no_proximo_rotulo(match.group(1))
            nome = _normalizar_nome(bruto)
            if nome:
                return nome
    return None


def extrair_pagador(texto: str) -> str | None:
    return _extrair_por_rotulos(texto, _ROTULOS_PAGADOR)


def extrair_recebedor(texto: str) -> str | None:
    return _extrair_por_rotulos(texto, _ROTULOS_RECEBEDOR)
