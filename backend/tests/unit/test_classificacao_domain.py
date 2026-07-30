from app.domain.entities import Classificacao
from app.domain.enums import OrigemClassificacao


def test_classificacao_por_regra_nao_tem_score():
    classificacao = Classificacao(
        id=None, empresa_id=1, documento_id=1, conta_id=10,
        origem=OrigemClassificacao.REGRA, regra_id=5,
    )
    assert classificacao.score_similaridade is None
    assert classificacao.regra_id == 5


def test_classificacao_por_fuzzy_tem_score_e_sem_regra():
    classificacao = Classificacao(
        id=None, empresa_id=1, documento_id=1, conta_id=10,
        origem=OrigemClassificacao.FUZZY, score_similaridade=0.87,
    )
    assert classificacao.regra_id is None
    assert classificacao.score_similaridade == 0.87
