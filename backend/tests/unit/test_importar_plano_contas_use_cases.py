from app.application.use_cases.importar_plano_contas_use_cases import (
    ConfirmarImportacaoUseCase,
    PreviewImportacaoUseCase,
)
from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.spreadsheet.plano_contas_parser import LinhaPlanoContas
from tests.fakes import FakeContaRepository

import pytest


def test_preview_retorna_mapeamento_e_linhas():
    conteudo = b"Codigo,Descricao,Natureza\n1.1.01,Caixa,ATIVO\n"

    resultado = PreviewImportacaoUseCase().executar(conteudo, "arquivo.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert len(resultado.linhas) == 1


def test_preview_planilha_invalida_propaga_erro():
    conteudo = b"A,B\nx,y\n"

    with pytest.raises(ImportacaoPlanoContasInvalida):
        PreviewImportacaoUseCase().executar(conteudo, "arquivo.csv")


def test_confirmar_importacao_cria_contas_com_hierarquia():
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=False, conta_pai=None),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True, conta_pai="1.1"),
    ]

    contas = ConfirmarImportacaoUseCase(repo).executar(plano_conta_id=1, linhas=linhas)

    assert len(contas) == 2
    pai = next(c for c in contas if c.codigo == "1.1")
    filha = next(c for c in contas if c.codigo == "1.1.01")
    assert filha.conta_pai_id == pai.id


def test_confirmar_importacao_resolve_hierarquia_com_ordem_embaralhada_e_codigos_mesmo_tamanho():
    # Regressão: código do pai ("100") e do filho ("101") têm o mesmo
    # comprimento, e as linhas chegam fora de ordem (neta antes da filha
    # antes da mãe). Um sort por len(codigo) não reordenaria essas linhas
    # (chaves iguais, sort estável), então o filho seria criado como conta
    # raiz. A resolução correta deve montar a cadeia completa.
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="102", descricao="Neta", natureza="ATIVO", conta_analitica=True, conta_pai="101"),
        LinhaPlanoContas(codigo="101", descricao="Filha", natureza="ATIVO", conta_analitica=False, conta_pai="100"),
        LinhaPlanoContas(codigo="100", descricao="Mae", natureza="ATIVO", conta_analitica=False, conta_pai=None),
    ]

    contas = ConfirmarImportacaoUseCase(repo).executar(plano_conta_id=1, linhas=linhas)

    assert len(contas) == 3
    mae = next(c for c in contas if c.codigo == "100")
    filha = next(c for c in contas if c.codigo == "101")
    neta = next(c for c in contas if c.codigo == "102")

    assert mae.conta_pai_id is None
    assert filha.conta_pai_id == mae.id
    assert neta.conta_pai_id == filha.id


def test_confirmar_importacao_aplica_defaults_quando_natureza_ausente():
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="3.1", descricao="Despesas Gerais", natureza=None, conta_analitica=None, conta_pai=None),
    ]

    contas = ConfirmarImportacaoUseCase(repo).executar(plano_conta_id=1, linhas=linhas)

    assert contas[0].natureza.value == "DESPESA"
    assert contas[0].conta_analitica is True
