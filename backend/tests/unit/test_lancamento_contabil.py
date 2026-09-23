from app.domain.entities import Conta, Extracao
from app.domain.enums import DirecaoLancamento, NaturezaConta, TipoDocumento
from app.infrastructure.classificacao.lancamento_contabil import (
    resolver_conta_bancaria,
    resolver_direcao,
    resolver_lados_lancamento,
)

_CNPJ_EMPRESA = "12.345.678/0001-99"


def _extracao(pagador_documento=None, recebedor_documento=None) -> Extracao:
    return Extracao(
        id=None, documento_id=1, pagador_nome=None, pagador_documento=pagador_documento,
        recebedor_nome=None, recebedor_documento=recebedor_documento, valor=None,
        data_pagamento=None, tipo_documento=TipoDocumento.PIX, banco_nome=None,
    )


def test_empresa_e_pagador_direcao_pagamento():
    extracao = _extracao(pagador_documento="12345678000199", recebedor_documento="99988877000166")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) == DirecaoLancamento.PAGAMENTO


def test_empresa_e_recebedor_direcao_recebimento():
    extracao = _extracao(pagador_documento="99988877000166", recebedor_documento="12345678000199")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) == DirecaoLancamento.RECEBIMENTO


def test_nenhum_documento_bate_com_cnpj_da_empresa_direcao_none():
    extracao = _extracao(pagador_documento="11111111000100", recebedor_documento="22222222000100")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) is None


def test_ambos_documentos_batem_com_cnpj_da_empresa_e_ambiguo():
    extracao = _extracao(pagador_documento="12345678000199", recebedor_documento="12.345.678/0001-99")
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) is None


def test_nenhum_documento_extraido_direcao_none():
    extracao = _extracao(pagador_documento=None, recebedor_documento=None)
    assert resolver_direcao(_CNPJ_EMPRESA, extracao) is None


def _conta_banco(descricao: str, id_: int = 1) -> Conta:
    return Conta(
        id=id_, plano_conta_id=1, codigo=f"1.1.01.002.{id_:05d}", descricao=descricao,
        natureza=NaturezaConta.ATIVO, conta_analitica=True,
    )


def test_uma_correspondencia_de_banco_resolve():
    contas = [_conta_banco("Banco do Brasil S.A. AG 94-9", id_=1)]
    assert resolver_conta_bancaria("Banco do Brasil", contas) == 1


def test_banco_nome_none_nao_resolve():
    contas = [_conta_banco("Banco do Brasil S.A.", id_=1)]
    assert resolver_conta_bancaria(None, contas) is None


def test_zero_correspondencias_nao_resolve():
    contas = [_conta_banco("Banco Itaú S.A.", id_=1)]
    assert resolver_conta_bancaria("Banco do Brasil", contas) is None


def test_multiplas_correspondencias_nao_resolve():
    contas = [
        _conta_banco("Banco Santander AG 1054 C/C 13.000844-0", id_=1),
        _conta_banco("Banco Santander AG 1054 C/C 13.000990-8 - Filial", id_=2),
    ]
    assert resolver_conta_bancaria("Santander", contas) is None


def test_match_ignora_acento_e_maiuscula():
    contas = [_conta_banco("Banco Itaú S.A.", id_=1)]
    assert resolver_conta_bancaria("ITAU", contas) == 1


def _conta_contrapartida() -> Conta:
    return Conta(
        id=10, plano_conta_id=1, codigo="3.2.01", descricao="Despesa Teste",
        natureza=NaturezaConta.DESPESA, conta_analitica=True,
    )


def test_lados_lancamento_pagamento_debita_contrapartida_credita_banco():
    contrapartida = _conta_contrapartida()
    banco = _conta_banco("Banco do Brasil")
    debito, credito = resolver_lados_lancamento(DirecaoLancamento.PAGAMENTO, contrapartida, banco)
    assert debito is contrapartida
    assert credito is banco


def test_lados_lancamento_recebimento_debita_banco_credita_contrapartida():
    contrapartida = _conta_contrapartida()
    banco = _conta_banco("Banco do Brasil")
    debito, credito = resolver_lados_lancamento(DirecaoLancamento.RECEBIMENTO, contrapartida, banco)
    assert debito is banco
    assert credito is contrapartida


def test_lados_lancamento_direcao_none_ambos_none():
    contrapartida = _conta_contrapartida()
    banco = _conta_banco("Banco do Brasil")
    debito, credito = resolver_lados_lancamento(None, contrapartida, banco)
    assert debito is None
    assert credito is None


def test_lados_lancamento_banco_none_mas_direcao_conhecida_mostra_contrapartida():
    contrapartida = _conta_contrapartida()
    debito, credito = resolver_lados_lancamento(DirecaoLancamento.PAGAMENTO, contrapartida, None)
    assert debito is contrapartida
    assert credito is None
