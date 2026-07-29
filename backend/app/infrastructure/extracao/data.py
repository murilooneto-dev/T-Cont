import re
from datetime import date

_PADRAO_DATA = re.compile(r"(\d{2})[/-](\d{2})[/-](\d{4})")


def extrair_data(texto: str) -> date | None:
    match = _PADRAO_DATA.search(texto)
    if not match:
        return None
    dia, mes, ano = match.groups()
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None
