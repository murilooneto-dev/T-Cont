from app.infrastructure.extracao.documento_fiscal import extrair_documentos


def test_extrai_cnpj_com_pontuacao():
    resultado = extrair_documentos("CNPJ: 12.345.678/0001-95")
    assert resultado == ["12345678000195"]


def test_extrai_cpf_com_pontuacao():
    resultado = extrair_documentos("CPF: 123.456.789-00")
    assert resultado == ["12345678900"]


def test_extrai_multiplos_documentos_na_ordem():
    texto = "Pagador CPF: 123.456.789-00\nRecebedor CNPJ: 12.345.678/0001-95"
    resultado = extrair_documentos(texto)
    assert resultado == ["12345678900", "12345678000195"]


def test_nao_duplica_o_mesmo_documento():
    texto = "CPF 123.456.789-00 repetido: 123.456.789-00"
    resultado = extrair_documentos(texto)
    assert resultado == ["12345678900"]


def test_texto_sem_documento_retorna_lista_vazia():
    assert extrair_documentos("Nenhum documento fiscal aqui.") == []


def test_nao_extrai_de_sequencia_numerica_longa_sem_pontuacao():
    # NF-e access key: 44 continuous digits (simulating a boleto or invoice number)
    # Should NOT extract any CPF/CNPJ from within this continuous run
    nfe_chave = "35230512345678000195550010000012345678901234"
    texto = f"Chave de acesso: {nfe_chave} do arquivo"
    resultado = extrair_documentos(texto)
    assert resultado == []


def test_extrai_cpf_sem_pontuacao_com_limites():
    # Isolated unpunctuated CPF (11 digits) bounded by non-digit characters
    # Should still extract correctly when surrounded by spaces or text
    resultado = extrair_documentos("Doc: 12345678900 fim")
    assert resultado == ["12345678900"]
