import pytest

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


_BOLETO_SEM_CNPJ_COM_BARRAS = (
    "COMPROVANTE DE PAGAMENTO\nConvenio VIVO FIXO/BRASIL\n"
    "Codigo de Barras   84670000000-9   92620082089-8\n"
    "Data do pagamento   17/08/2026\nValor Total   R$ 92,62"
)
_BOLETO_SEM_CNPJ_SEM_BARRAS = (
    "COMPROVANTE DE PAGAMENTO\nData do pagamento   17/08/2026\nValor Total   R$ 92,62"
)


def test_pagina_com_codigo_barras_mas_sem_cnpj_inicia_novo_segmento():
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, _BOLETO_SEM_CNPJ_COM_BARRAS])
    assert resultado == [[0], [1]]


def test_pagina_sem_codigo_barras_e_sem_cnpj_continua_fundida():
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, _BOLETO_SEM_CNPJ_SEM_BARRAS])
    assert resultado == [[0, 1]]


@pytest.mark.parametrize(
    "grafia",
    [
        "Codigo de Barras   84670000000-9",
        "Código de Barras   84670000000-9",
        "CODIGO DE BARRAS   84670000000-9",
        "Cod. de Barras   84670000000-9",
        "cod. barras   84670000000-9",
    ],
)
def test_variacoes_de_grafia_do_codigo_de_barras_sao_reconhecidas(grafia):
    texto = f"COMPROVANTE DE PAGAMENTO\n{grafia}\nData do pagamento   17/08/2026\nValor Total   R$ 92,62"
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, texto])
    assert resultado == [[0], [1]]


def test_pagina_com_codigo_barras_mas_sem_valor_nao_inicia_segmento():
    texto_sem_valor = "COMPROVANTE DE PAGAMENTO\nCodigo de Barras   84670000000-9"
    resultado = agrupar_paginas_em_comprovantes([_COMPLETA, texto_sem_valor])
    assert resultado == [[0, 1]]
