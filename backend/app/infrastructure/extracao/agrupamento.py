from app.infrastructure.extracao.pipeline import extrair_dados_documento


def _pagina_inicia_novo_comprovante(texto: str) -> bool:
    dados = extrair_dados_documento(texto)
    tem_documento_fiscal = dados.pagador_documento is not None or dados.recebedor_documento is not None
    return dados.valor is not None and tem_documento_fiscal


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
