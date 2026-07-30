from datetime import datetime, timezone
from decimal import Decimal

from app.domain.entities import Extracao, Regra
from app.domain.enums import LadoRegra, OrigemClassificacao, TipoDocumento
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


def test_classifica_por_regra_quando_bate():
    regra = Regra(
        id=1, empresa_id=1, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome=None, ativo=True,
    )
    resultado = classificar_documento(_extracao(), [regra], [])
    assert resultado.origem == OrigemClassificacao.REGRA
    assert resultado.conta_id == 10
    assert resultado.regra_id == 1
    assert resultado.score_similaridade is None


def test_cai_para_fuzzy_quando_nenhuma_regra_bate():
    historico = [("ENERGISA CEARA", 20, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    resultado = classificar_documento(_extracao(), [], historico)
    assert resultado.origem == OrigemClassificacao.FUZZY
    assert resultado.conta_id == 20
    assert resultado.regra_id is None
    assert resultado.score_similaridade is not None


def test_sem_regra_e_sem_historico_retorna_none():
    assert classificar_documento(_extracao(), [], []) is None


def test_usa_pagador_quando_recebedor_ausente_no_fuzzy():
    historico = [("JOAO", 30, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    resultado = classificar_documento(_extracao(recebedor_nome=None), [], historico)
    assert resultado.conta_id == 30
