import re

from app.infrastructure.extracao.pipeline import extrair_dados_documento

_CODIGO_BARRAS_RE = re.compile(
    r"c[oó]digo\s+de\s+barras|cod\.?\s+(de\s+)?barras", re.IGNORECASE
)


def _pagina_tem_codigo_barras(texto: str) -> bool:
    return _CODIGO_BARRAS_RE.search(texto) is not None


def _pagina_inicia_novo_comprovante(texto: str) -> bool:
    dados = extrair_dados_documento(texto)
    if dados.valor is None:
        return False
    tem_documento_fiscal = dados.pagador_documento is not None or dados.recebedor_documento is not None
    return tem_documento_fiscal or _pagina_tem_codigo_barras(texto)


def agrupar_paginas_em_comprovantes(textos_por_pagina: list[str]) -> list[list[int]]:
    if not textos_por_pagina:
        return []

    segmentos: list[list[int]] = []
    segmento_atual: list[int] = [0]

    for indice in range(1, len(textos_por_pagina)):
        if _pagina_inicia_novo_comprovante(textos_por_pagina[indice]):
            segmentos.append(segmento_atual)
            segmento_atual = [indice]
        else:
            segmento_atual.append(indice)

    segmentos.append(segmento_atual)
    return segmentos
