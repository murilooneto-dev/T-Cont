import re
from datetime import date

_PADRAO_DATA = re.compile(r"(?<!\d)(\d{2})[/-](\d{2})[/-](\d{4})(?!\d)")
_PALAVRA_PAGAMENTO = re.compile(r"\bpag(?:amento|o)\b", re.IGNORECASE)
_JANELA_PAGAMENTO = 30


def _parse_data(dia: str, mes: str, ano: str) -> date | None:
    """Parse dia, mes, ano strings to a date object, returning None if invalid."""
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


def extrair_data(texto: str) -> date | None:
    matches = list(_PADRAO_DATA.finditer(texto))
    if not matches:
        return None

    # Try to find a date with "pagamento" or "pago" nearby
    for match in matches:
        inicio_janela = max(0, match.start() - _JANELA_PAGAMENTO)
        trecho_anterior = texto[inicio_janela:match.start()]
        if _PALAVRA_PAGAMENTO.search(trecho_anterior):
            dia, mes, ano = match.groups()
            parsed_data = _parse_data(dia, mes, ano)
            if parsed_data is not None:
                return parsed_data

    # Fall back to the first match that parses successfully
    for match in matches:
        dia, mes, ano = match.groups()
        parsed_data = _parse_data(dia, mes, ano)
        if parsed_data is not None:
            return parsed_data
    return None
