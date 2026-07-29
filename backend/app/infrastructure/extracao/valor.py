import re
from decimal import Decimal, InvalidOperation

_PADRAO_VALOR = re.compile(r"R\$\s*([\d.]+,\d{2})")


def extrair_valor(texto: str) -> Decimal | None:
    match = _PADRAO_VALOR.search(texto)
    if not match:
        return None
    bruto = match.group(1)
    normalizado = bruto.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalizado)
    except InvalidOperation:
        return None
