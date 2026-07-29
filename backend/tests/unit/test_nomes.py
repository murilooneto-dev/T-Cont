from app.infrastructure.extracao.nomes import extrair_pagador, extrair_recebedor


def test_extrai_pagador_por_rotulo():
    texto = "Pagador: Joao da Silva Ltda\nValor: R$100,00"
    assert extrair_pagador(texto) == "JOAO DA SILVA"


def test_extrai_pagador_por_rotulo_de():
    texto = "De: Maria Souza ME\nData: 01/01/2026"
    assert extrair_pagador(texto) == "MARIA SOUZA"


def test_extrai_recebedor_por_rotulo_favorecido():
    texto = "Favorecido: Energisa S.A.\nBanco: Itaú"
    assert extrair_recebedor(texto) == "ENERGISA"


def test_extrai_recebedor_por_rotulo_para():
    texto = "Para: Claro S/A\nValor pago"
    assert extrair_recebedor(texto) == "CLARO"


def test_normaliza_espacos_multiplos():
    texto = "Pagador:   Joao    da   Silva\nOutro campo"
    assert extrair_pagador(texto) == "JOAO DA SILVA"


def test_sem_rotulo_retorna_none():
    assert extrair_pagador("Nenhum rótulo de pagador aqui.") is None
    assert extrair_recebedor("Nenhum rótulo de recebedor aqui.") is None


def test_rotulo_de_nao_confunde_com_finalidade():
    texto = "Finalidade: Pagamento do boleto\nValor: R$50,00"
    assert extrair_pagador(texto) is None


def test_rotulos_na_mesma_linha_nao_vazam():
    texto = "De: Maria Silva Para: Joao Santos"
    assert extrair_pagador(texto) == "MARIA SILVA"
    assert extrair_recebedor(texto) == "JOAO SANTOS"


def test_nome_nao_inclui_cpf_na_mesma_linha():
    texto = "Pagador: JOAO DA SILVA CPF 123.456.789-00"
    assert extrair_pagador(texto) == "JOAO DA SILVA"


def test_nome_nao_inclui_agencia_e_conta_na_mesma_linha():
    texto = "Favorecido: ENERGISA S.A. Agencia 0001 Conta 12345-6"
    assert extrair_recebedor(texto) == "ENERGISA"
