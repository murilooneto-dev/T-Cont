from app.infrastructure.spreadsheet.column_detector import detectar_colunas


def test_detecta_colunas_com_nomes_exatos():
    mapeamento = detectar_colunas(["Código", "Descrição", "Natureza"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1
    assert mapeamento["natureza"] == 2


def test_detecta_colunas_com_sinonimos():
    mapeamento = detectar_colunas(["Cod. Conta", "Nome da Conta", "Tipo"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1
    assert mapeamento["natureza"] == 2


def test_detecta_colunas_em_ingles():
    mapeamento = detectar_colunas(["Account Code", "Account Name"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1


def test_coluna_nao_reconhecida_fica_none():
    mapeamento = detectar_colunas(["Código", "Descrição", "Coluna Aleatória XYZ"])
    assert mapeamento["natureza"] is None


def test_detecta_conta_analitica_e_conta_pai():
    mapeamento = detectar_colunas(["Código", "Descrição", "Conta Analítica", "Conta Pai"])
    assert mapeamento["conta_analitica"] == 2
    assert mapeamento["conta_pai"] == 3


def test_cota_nao_e_confundida_com_descricao():
    # Regressao: "Cota" (quota/share) e um header curto e generico que nao
    # deve ser confundido com "descricao" so por ter similaridade textual
    # com o sinonimo "conta".
    mapeamento = detectar_colunas(["Cota", "Descrição"])
    assert mapeamento["descricao"] == 1
    for campo, indice in mapeamento.items():
        assert indice != 0, f"'Cota' nao deveria ser selecionada para o campo '{campo}'"


def test_detecta_codigo_via_fuzzy_match_com_erro_de_digitacao():
    # "Codgo" e um near-miss de "codigo" (score ~0.909, acima do novo
    # limiar de 0.87) que deve continuar sendo detectado via fuzzy match.
    mapeamento = detectar_colunas(["Codgo", "Descrição"])
    assert mapeamento["codigo"] == 0
    assert mapeamento["descricao"] == 1
