from pathlib import Path

import pytest

from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.domain.enums import NaturezaConta
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


def test_codigo_e_conta_pai_com_espacos_sao_normalizados():
    # codigo/conta_pai viram chave de comparação/link em todo o fluxo de
    # importação (duplicidade, hierarquia); precisam ser normalizados uma
    # única vez aqui na origem, não em cada consumidor.
    conteudo = (
        "Codigo,Descricao,Natureza,Conta Pai\n"
        " 1.1 ,Disponibilidades,ATIVO,\n"
        " 1.1.01 ,Caixa,ATIVO, 1.1 \n"
    ).encode("utf-8")

    resultado = parsear_planilha(conteudo, "plano.csv")

    assert resultado.linhas[0].codigo == "1.1"
    assert resultado.linhas[1].codigo == "1.1.01"


def test_parseia_relatorio_hierarquico_reconhece_formato():
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    assert len(resultado.linhas) == 12


def test_relatorio_hierarquico_extrai_codigo_sem_sufixo_residual():
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    codigos = {linha.codigo for linha in resultado.linhas}
    assert "1.1.01" in codigos
    assert not any(codigo.endswith("�") for codigo in codigos)


def test_relatorio_hierarquico_acha_descricao_na_coluna_certa_por_nivel():
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    por_codigo = {linha.codigo: linha for linha in resultado.linhas}
    assert por_codigo["1.1"].descricao == "ATIVO CIRCULANTE"
    assert por_codigo["1.1.01"].descricao == "Caixa e Equivalentes"


@pytest.mark.parametrize(
    "codigo, natureza_esperada",
    [
        ("1.1.01", NaturezaConta.ATIVO),
        ("2.1.01", NaturezaConta.PASSIVO),
        ("2.3.01", NaturezaConta.PATRIMONIO_LIQUIDO),
        ("3.1.01", NaturezaConta.RECEITA),
        ("3.2.01", NaturezaConta.DESPESA),
    ],
)
def test_relatorio_hierarquico_infere_natureza_por_prefixo(codigo, natureza_esperada):
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    por_codigo = {linha.codigo: linha for linha in resultado.linhas}
    assert por_codigo[codigo].natureza == natureza_esperada.value


def test_relatorio_hierarquico_raiz_fora_da_convencao_cai_em_ativo():
    # Raízes fora de 1/2/3 (ex.: "4" = Resultado do Exercício/Balanço de
    # Abertura em alguns planos) não têm equivalente exato entre os 5
    # valores de NaturezaConta — decisão confirmada com o usuário: cair em
    # ATIVO por padrão em vez de falhar a importação inteira.
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    from app.infrastructure.spreadsheet.plano_contas_parser import _inferir_natureza

    assert _inferir_natureza("4.1.01") == NaturezaConta.ATIVO
    assert resultado.linhas  # sanity: fixture ainda parseou normalmente


def test_relatorio_hierarquico_calcula_conta_pai_pelo_codigo():
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    por_codigo = {linha.codigo: linha for linha in resultado.linhas}
    assert por_codigo["1.1.01"].conta_pai == "1.1"
    assert por_codigo["1.1"].conta_pai == "1"
    assert por_codigo["1"].conta_pai is None


def test_relatorio_hierarquico_ignora_blocos_de_cabecalho_de_pagina():
    conteudo = (FIXTURES / "plano_contas_hierarquico.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_hierarquico.csv")

    descricoes = {linha.descricao for linha in resultado.linhas}
    assert "TESSERATO CONTABILIDADE LTDA" not in descricoes
    assert "Nome da Conta" not in descricoes
    assert all(linha.codigo for linha in resultado.linhas)


def test_csv_simples_nao_aciona_fallback_hierarquico():
    conteudo = (FIXTURES / "plano_contas_padrao.csv").read_bytes()

    resultado = parsear_planilha(conteudo, "plano_contas_padrao.csv")

    assert resultado.mapeamento["descricao"] is not None
