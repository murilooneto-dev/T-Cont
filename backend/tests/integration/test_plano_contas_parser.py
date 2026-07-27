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
