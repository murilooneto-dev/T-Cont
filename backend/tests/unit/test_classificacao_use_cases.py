import pytest

from app.application.use_cases.classificacao_use_cases import CorrigirClassificacaoUseCase
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, PlanoContas, Regra,
)
from app.domain.enums import (
    DirecaoLancamento, LadoRegra, NaturezaConta, OrigemClassificacao, TipoDocumento,
)
from tests.fakes import (
    FakeAprendizadoRepository,
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeEmpresaRepository,
    FakeExtracaoRepository,
    FakePlanoContasRepository,
    FakeRegraRepository,
)


def _ambiente(conta_analitica=True):
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    regra_repo = FakeRegraRepository()
    aprendizado_repo = FakeAprendizadoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    empresa_repo = FakeEmpresaRepository()

    empresa_repo.criar(
        Empresa(id=None, razao_social="Empresa Teste", nome_fantasia=None, cnpj="00000000000000")
    )
    documento = documento_repo.criar(
        Documento(
            id=None, empresa_id=1, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=conta_analitica,
        )
    )
    return {
        "documento_repo": documento_repo, "extracao_repo": extracao_repo,
        "classificacao_repo": classificacao_repo, "regra_repo": regra_repo,
        "aprendizado_repo": aprendizado_repo, "conta_repo": conta_repo,
        "plano_repo": plano_repo, "empresa_repo": empresa_repo,
        "documento": documento, "conta": conta,
    }


def _use_case(ambiente):
    return CorrigirClassificacaoUseCase(
        ambiente["documento_repo"], ambiente["extracao_repo"], ambiente["classificacao_repo"],
        ambiente["regra_repo"], ambiente["aprendizado_repo"], ambiente["conta_repo"],
        ambiente["plano_repo"], ambiente["empresa_repo"],
    )


def test_corrigir_cria_regra_nova_pelo_recebedor():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome="ENERGISA",
            recebedor_documento="12345678000195", valor=None, data_pagamento=None,
            tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.origem == OrigemClassificacao.MANUAL
    assert classificacao.conta_id == ambiente["conta"].id
    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert len(regras) == 1
    assert regras[0].documento_fiscal == "12345678000195"
    assert regras[0].lado_alvo == LadoRegra.RECEBEDOR
    assert regras[0].conta_id == ambiente["conta"].id


def test_corrigir_usa_pagador_quando_recebedor_ausente():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome="JOAO",
            pagador_documento="12345678900", recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert regras[0].documento_fiscal == "12345678900"
    assert regras[0].lado_alvo == LadoRegra.PAGADOR


def test_corrigir_atualiza_regra_existente_em_vez_de_duplicar():
    ambiente = _ambiente()
    outra_conta = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=1, codigo="2", descricao="Outra",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    regra_antiga = ambiente["regra_repo"].criar(
        Regra(
            id=None, empresa_id=1, conta_id=outra_conta.id, lado_alvo=LadoRegra.RECEBEDOR,
            documento_fiscal="12345678000195", tipo_documento=None, valor_min=None,
            valor_max=None, palavra_chave_nome=None, ativo=True,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome="ENERGISA",
            recebedor_documento="12345678000195", valor=None, data_pagamento=None,
            tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert len(regras) == 1
    assert regras[0].id == regra_antiga.id
    assert regras[0].conta_id == ambiente["conta"].id


def test_corrigir_reativa_regra_desativada():
    ambiente = _ambiente()
    outra_conta = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=1, codigo="2", descricao="Outra",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    regra_desativada = ambiente["regra_repo"].criar(
        Regra(
            id=None, empresa_id=1, conta_id=outra_conta.id, lado_alvo=LadoRegra.RECEBEDOR,
            documento_fiscal="12345678000195", tipo_documento=None, valor_min=None,
            valor_max=None, palavra_chave_nome=None, ativo=False,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome="ENERGISA",
            recebedor_documento="12345678000195", valor=None, data_pagamento=None,
            tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    regras = ambiente["regra_repo"].listar_por_empresa(1)
    assert len(regras) == 1
    assert regras[0].id == regra_desativada.id
    assert regras[0].ativo is True
    assert regras[0].conta_id == ambiente["conta"].id


def test_corrigir_sem_documento_fiscal_nao_cria_regra():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.regra_id is None
    assert ambiente["regra_repo"].listar_por_empresa(1) == []


def test_corrigir_documento_ja_classificado_atualiza_e_registra_aprendizado():
    ambiente = _ambiente()
    outra_conta = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=1, codigo="2", descricao="Outra",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    classificacao_existente = ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=ambiente["documento"].id,
            conta_id=outra_conta.id, origem=OrigemClassificacao.FUZZY,
            score_similaridade=0.6,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.id == classificacao_existente.id
    assert classificacao.origem == OrigemClassificacao.MANUAL
    assert classificacao.score_similaridade is None

    aprendizados = ambiente["aprendizado_repo"].listar_por_empresa(1)
    assert len(aprendizados) == 1
    assert aprendizados[0].conta_anterior_id == outra_conta.id
    assert aprendizados[0].origem_anterior == OrigemClassificacao.FUZZY
    assert aprendizados[0].conta_corrigida_id == ambiente["conta"].id


def test_corrigir_documento_sem_classificacao_anterior_cria():
    ambiente = _ambiente()
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome=None,
            pagador_documento=None, recebedor_nome=None, recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.id is not None
    aprendizados = ambiente["aprendizado_repo"].listar_por_empresa(1)
    assert aprendizados[0].conta_anterior_id is None
    assert aprendizados[0].origem_anterior is None


def test_corrigir_documento_sem_classificacao_anterior_resolve_direcao_e_conta_bancaria():
    ambiente = _ambiente()
    conta_bancaria = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=1, codigo="1.1.1", descricao="Banco do Brasil C/C",
            natureza=NaturezaConta.ATIVO, conta_analitica=True,
        )
    )
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=ambiente["documento"].id, pagador_nome="Empresa Teste",
            pagador_documento="00000000000000", recebedor_nome="ENERGISA",
            recebedor_documento="12345678000195", valor=None, data_pagamento=None,
            tipo_documento=TipoDocumento.OUTRO, banco_nome="Banco do Brasil",
        )
    )

    classificacao = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)

    assert classificacao.direcao == DirecaoLancamento.PAGAMENTO
    assert classificacao.conta_bancaria_id == conta_bancaria.id


def test_corrigir_documento_inexistente_falha():
    ambiente = _ambiente()
    with pytest.raises(DocumentoNaoEncontrado):
        _use_case(ambiente).executar(999, ambiente["conta"].id)


def test_corrigir_com_conta_inexistente_falha():
    ambiente = _ambiente()
    with pytest.raises(ContaNaoEncontrada):
        _use_case(ambiente).executar(ambiente["documento"].id, 999)


def test_corrigir_com_conta_sintetica_falha():
    ambiente = _ambiente(conta_analitica=False)
    with pytest.raises(ContaNaoAnalitica):
        _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta"].id)
