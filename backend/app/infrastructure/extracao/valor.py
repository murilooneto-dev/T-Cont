import re
from decimal import Decimal, InvalidOperation

_PADRAO_VALOR = re.compile(r"R\$\s*([\d.]+,\d{2})")
_PADRAO_VALOR_SEM_RS = re.compile(
    r"\b(?:total|cobrado)\b.*?([\d.]+,\d{2})\s*$", re.IGNORECASE | re.MULTILINE
)
_PALAVRA_TOTAL = re.compile(r"\btotal\b", re.IGNORECASE)
_JANELA_TOTAL = 30  # caracteres a considerar antes do valor, para checar se "total" aparece perto


def _normalizar(bruto: str) -> Decimal | None:
    normalizado = bruto.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalizado)
    except InvalidOperation:
        return None


def extrair_valor(texto: str) -> Decimal | None:
    matches = list(_PADRAO_VALOR.finditer(texto))
    if matches:
        for match in matches:
            inicio_janela = max(0, match.start() - _JANELA_TOTAL)
            trecho_anterior = texto[inicio_janela:match.start()]
            if _PALAVRA_TOTAL.search(trecho_anterior):
                valor = _normalizar(match.group(1))
                if valor is not None:
                    return valor

        return _normalizar(matches[0].group(1))

    # Alguns comprovantes de boleto imprimem o valor sem o prefixo "R$",
    # rotulado como "Valor Total" ou "Valor Cobrado" — fallback só usado
    # quando nenhum valor com "R$" foi encontrado no texto inteiro.
    match_sem_rs = _PADRAO_VALOR_SEM_RS.search(texto)
    if match_sem_rs is not None:
        return _normalizar(match_sem_rs.group(1))

    return None
