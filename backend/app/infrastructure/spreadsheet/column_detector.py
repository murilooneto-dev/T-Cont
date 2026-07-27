import unicodedata
from difflib import SequenceMatcher

CAMPOS_OBRIGATORIOS = {"codigo", "descricao"}

_SINONIMOS: dict[str, list[str]] = {
    "codigo": ["codigo", "cod", "cod conta", "codigo conta", "account code", "code"],
    "descricao": [
        "descricao", "descricao da conta", "nome", "nome da conta", "historico",
        "account name", "name",
    ],
    "natureza": ["natureza", "tipo", "tipo de conta", "account type", "type"],
    "conta_analitica": [
        "conta analitica", "analitica", "analytic account", "e analitica",
    ],
    "conta_pai": ["conta pai", "conta superior", "parent account", "parent"],
}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower().replace(".", "").replace("_", " ")


def _similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def detectar_colunas(cabecalhos: list[str]) -> dict[str, int | None]:
    normalizados = [_normalizar(h) for h in cabecalhos]
    resultado: dict[str, int | None] = {}

    for campo, sinonimos in _SINONIMOS.items():
        melhor_indice: int | None = None
        melhor_score = 0.0

        for indice, cabecalho in enumerate(normalizados):
            if cabecalho in sinonimos:
                melhor_indice = indice
                melhor_score = 1.0
                break
            for sinonimo in sinonimos:
                score = _similaridade(cabecalho, sinonimo)
                if score > melhor_score:
                    melhor_score = score
                    melhor_indice = indice

        resultado[campo] = melhor_indice if melhor_score >= 0.87 else None

    return resultado
