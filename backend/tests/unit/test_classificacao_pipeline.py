from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.domain.entities import Conta, Extracao, Regra
from app.domain.enums import LadoRegra, NaturezaConta, OrigemClassificacao, TipoDocumento
from app.infrastructure.classificacao.pipeline import classificar_documento


def _extracao(**overrides):
    base = dict(
        id=1, documento_id=1, pagador_nome="JOAO", pagador_documento="12345678900",
        recebedor_nome="ENERGISA", recebedor_documento="12345678000195",
        valor=Decimal("150.00"), data_pagamento=None, tipo_documento=TipoDocumento.PIX,
        banco_nome=None,
    )
    base.update(overrides)
    return Extracao(**base)


def _conta(id_=1, codigo="1"):
    return Conta(
        id=id_, plano_conta_id=1, codigo=codigo, descricao="Conta",
        natureza=NaturezaConta.DESPESA, conta_analitica=True,
    )


def test_classifica_por_regra_quando_bate():
    regra = Regra(
        id=1, empresa_id=1, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome=None, ativo=True,
    )
    resultado = classificar_documento(_extracao(), [regra], [_conta()], [])
    assert resultado.origem == OrigemClassificacao.REGRA
    assert resultado.conta_id == 10
    assert resultado.regra_id == 1
    assert resultado.score_similaridade is None


def test_classifica_por_ia_quando_nenhuma_regra_bate_e_ia_responde():
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=20
    ):
        resultado = classificar_documento(_extracao(), [], [_conta(20, "2")], [])
    assert resultado.origem == OrigemClassificacao.IA
    assert resultado.conta_id == 20
    assert resultado.regra_id is None
    assert resultado.score_similaridade is None


def test_cai_para_fuzzy_quando_nenhuma_regra_e_ia_nao_responde():
    historico = [("ENERGISA CEARA", 20, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None
    ):
        resultado = classificar_documento(_extracao(), [], [_conta()], historico)
    assert resultado.origem == OrigemClassificacao.FUZZY
    assert resultado.conta_id == 20
    assert resultado.regra_id is None
    assert resultado.score_similaridade is not None


def test_sem_regra_ia_e_historico_retorna_none():
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None
    ):
        assert classificar_documento(_extracao(), [], [_conta()], []) is None


def test_usa_pagador_quando_recebedor_ausente_no_fuzzy():
    historico = [("JOAO", 30, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    with patch(
        "app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None
    ):
        resultado = classificar_documento(
            _extracao(recebedor_nome=None), [], [_conta()], historico
        )
    assert resultado.conta_id == 30
