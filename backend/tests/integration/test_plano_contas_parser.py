from pathlib import Path

import pytest

from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.spreadsheet.plano_contas_parser import parsear_planilha

FIXTURES = Path(__file__).parent / "fixtures"


def test_parseia_planilha_padrao():
    conteudo = (FIXTURES / "plano_contas_padrao.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_padrao.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert resultado.mapeamento["descricao"] == 1
    assert len(resultado.linhas) == 4
    assert resultado.linhas[2].codigo == "1.1.01"
    assert resultado.linhas[2].descricao == "Caixa"
    assert resultado.linhas[2].conta_analitica is True


def test_parseia_planilha_com_colunas_variantes():
    conteudo = (FIXTURES / "plano_contas_variante.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_variante.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert resultado.mapeamento["descricao"] == 1
    assert len(resultado.linhas) == 2
    assert resultado.linhas[0].codigo == "2"


def test_planilha_sem_colunas_obrigatorias_falha():
    conteudo = b"Coluna A,Coluna B\nx,y\n"

    with pytest.raises(ImportacaoPlanoContasInvalida):
        parsear_planilha(conteudo, "invalida.csv")


def test_parseia_csv_em_latin1():
    # Exportações de ERP brasileiro costumam vir em cp1252/latin-1, que
    # antes estouravam UnicodeDecodeError (HTTP 500).
    texto = (
        "Código,Descrição,Natureza\n"
        "1.1.01,Caixa,ATIVO\n"
        "3.1.02,Manutenção Predial,DESPESA\n"
    )
    conteudo = texto.encode("latin-1")

    resultado = parsear_planilha(conteudo, "plano_latin1.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert len(resultado.linhas) == 2
    assert resultado.linhas[1].descricao == "Manutenção Predial"


def test_conteudo_binario_nao_estoura_excecao_crua():
    # Bytes arbitrários (ex.: um PDF renomeado) devem virar erro de
    # importação, nunca UnicodeDecodeError/csv.Error sem tratamento.
    conteudo = bytes(range(256)) * 4

    with pytest.raises(ImportacaoPlanoContasInvalida):
        parsear_planilha(conteudo, "lixo.csv")


def test_nome_de_arquivo_ausente_nao_estoura():
    conteudo = b"Codigo,Descricao,Natureza\n1.1.01,Caixa,ATIVO\n"

    resultado = parsear_planilha(conteudo, None)

    assert len(resultado.linhas) == 1


def test_xlsx_invalido_vira_erro_de_importacao():
    with pytest.raises(ImportacaoPlanoContasInvalida):
        parsear_planilha(b"isto nao e um xlsx", "plano.xlsx")
