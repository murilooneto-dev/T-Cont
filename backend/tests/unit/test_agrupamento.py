from app.infrastructure.extracao.agrupamento import agrupar_paginas_em_comprovantes

_COMPLETA = "Favorecido: Empresa Teste\nCNPJ: 11.222.333/0001-99\nValor: R$ 100,00"
_INCOMPLETA = "Texto solto sem CNPJ nem valor reconhecivel."


def test_uma_pagina_um_segmento():
    assert agrupar_paginas_em_comprovantes([_COMPLETA]) == [[0]]


def test_duas_paginas_ambas_completas_dois_segmentos():
    assert agrupar_paginas_em_comprovantes([_COMPLETA, _COMPLETA]) == [[0], [1]]


def test_segunda_pagina_incompleta_e_continuacao_da_primeira():
    assert agrupar_paginas_em_comprovantes([_COMPLETA, _INCOMPLETA]) == [[0, 1]]


def test_primeira_pagina_incompleta_ainda_inicia_o_primeiro_segmento():
    assert agrupar_paginas_em_comprovantes([_INCOMPLETA]) == [[0]]


def test_primeira_incompleta_segunda_completa_terceira_incompleta():
    # Página 0 sempre inicia o segmento 1 (mesmo sem extração completa).
    # Página 1, completa, inicia um novo segmento (2). Página 2, incompleta,
    # é continuação do segmento 2.
    resultado = agrupar_paginas_em_comprovantes([_INCOMPLETA, _COMPLETA, _INCOMPLETA])
    assert resultado == [[0], [1, 2]]


def test_lista_vazia_devolve_lista_vazia():
    assert agrupar_paginas_em_comprovantes([]) == []


def test_muitas_paginas_completas_seguidas_um_segmento_por_pagina():
    textos = [_COMPLETA] * 5
    resultado = agrupar_paginas_em_comprovantes(textos)
    assert resultado == [[0], [1], [2], [3], [4]]
