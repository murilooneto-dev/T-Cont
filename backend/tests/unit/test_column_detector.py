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
