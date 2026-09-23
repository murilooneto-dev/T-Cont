import pytest

from app.application.use_cases.fila_revisao_use_cases import ListarFilaRevisaoUseCase
from app.domain.entities import Classificacao, Conta, Documento, Extracao, PlanoContas
from app.domain.enums import (
    DirecaoLancamento, NaturezaConta, OrigemClassificacao, StatusDocumento, TipoDocumento,
)
from tests.fakes import (
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeExtracaoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    return {
        "documento_repo": documento_repo, "extracao_repo": extracao_repo,
        "classificacao_repo": classificacao_repo, "conta_repo": conta_repo, "conta": conta,
    }


def _documento(ambiente, status=StatusDocumento.CONCLUIDO):
    return ambiente["documento_repo"].criar(
        Documento(
            id=None, empresa_id=1, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10, status=status,
        )
    )


def _use_case(ambiente):
    return ListarFilaRevisaoUseCase(
        ambiente["documento_repo"], ambiente["extracao_repo"],
        ambiente["classificacao_repo"], ambiente["conta_repo"],
    )


def test_documento_concluido_sem_classificacao_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    assert itens[0].documento.id == documento.id
    assert itens[0].sugestao is None


def test_documento_pendente_sem_classificacao_nao_entra_na_fila():
    ambiente = _ambiente()
    _documento(ambiente, status=StatusDocumento.PENDENTE)

    itens = _use_case(ambiente).executar(1)

    assert itens == []


def test_documento_com_erro_nao_entra_na_fila():
    ambiente = _ambiente()
    _documento(ambiente, status=StatusDocumento.ERRO)

    itens = _use_case(ambiente).executar(1)

    assert itens == []


@pytest.mark.parametrize("origem", [OrigemClassificacao.REGRA, OrigemClassificacao.IA, OrigemClassificacao.MANUAL])
def test_classificacao_por_regra_ia_ou_manual_com_lancamento_completo_nao_entra_na_fila(origem):
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=origem, conta_bancaria_id=99, direcao=DirecaoLancamento.PAGAMENTO,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert itens == []


def test_classificacao_fuzzy_entra_na_fila_com_sugestao():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None, pagador_documento=None,
            recebedor_nome="Loja X", recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.FUZZY, score_similaridade=0.42,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    item = itens[0]
    assert item.extracao is not None
    assert item.extracao.recebedor_nome == "Loja X"
    assert item.sugestao is not None
    assert item.sugestao.conta_id == ambiente["conta"].id
    assert item.sugestao.conta_codigo == "1"
    assert item.sugestao.conta_descricao == "Energia"
    assert item.sugestao.score_similaridade == 0.42
    assert item.sugestao.origem == OrigemClassificacao.FUZZY


def test_filtra_apenas_pela_empresa_informada():
    ambiente = _ambiente()
    ambiente["documento_repo"].criar(
        Documento(
            id=None, empresa_id=2, nome_arquivo="b.pdf", nome_exibicao="b.pdf",
            caminho_arquivo="x/b.pdf", extensao=".pdf", tamanho_bytes=10,
            status=StatusDocumento.CONCLUIDO,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert itens == []


def test_classificacao_por_regra_com_direcao_e_conta_bancaria_faltando_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.REGRA,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    assert itens[0].documento.id == documento.id
    sugestao = itens[0].sugestao
    assert sugestao is not None
    assert sugestao.origem == OrigemClassificacao.REGRA
    assert sugestao.direcao is None
    assert sugestao.debito_codigo is None
    assert sugestao.credito_codigo is None


def test_classificacao_por_regra_com_direcao_resolvida_mas_banco_faltando_expoe_lado_da_contrapartida():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.REGRA, direcao=DirecaoLancamento.PAGAMENTO,
            conta_bancaria_id=None,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1
    sugestao = itens[0].sugestao
    assert sugestao is not None
    assert sugestao.origem == OrigemClassificacao.REGRA
    assert sugestao.direcao == DirecaoLancamento.PAGAMENTO
    # Direção PAGAMENTO: contrapartida (conta) entra no débito, o crédito
    # (conta bancária) ainda não foi resolvido.
    assert sugestao.debito_codigo == ambiente["conta"].codigo
    assert sugestao.credito_codigo is None


def test_classificacao_por_ia_com_conta_bancaria_resolvida_mas_direcao_faltando_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.IA, conta_bancaria_id=99, direcao=None,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert len(itens) == 1


def test_classificacao_manual_com_lancamento_completo_nao_entra_na_fila():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=documento.id, conta_id=ambiente["conta"].id,
            origem=OrigemClassificacao.MANUAL, conta_bancaria_id=99,
            direcao=DirecaoLancamento.PAGAMENTO,
        )
    )

    itens = _use_case(ambiente).executar(1)

    assert itens == []
