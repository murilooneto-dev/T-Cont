from app.domain.entities import Aprendizado
from app.domain.enums import OrigemClassificacao


def test_aprendizado_sem_classificacao_anterior():
    aprendizado = Aprendizado(
        id=None, empresa_id=1, documento_id=1, conta_anterior_id=None,
        origem_anterior=None, conta_corrigida_id=10,
    )
    assert aprendizado.conta_anterior_id is None
    assert aprendizado.regra_id is None


def test_aprendizado_com_classificacao_anterior_e_regra():
    aprendizado = Aprendizado(
        id=None, empresa_id=1, documento_id=1, conta_anterior_id=5,
        origem_anterior=OrigemClassificacao.FUZZY, conta_corrigida_id=10, regra_id=3,
    )
    assert aprendizado.conta_anterior_id == 5
    assert aprendizado.origem_anterior == OrigemClassificacao.FUZZY
    assert aprendizado.regra_id == 3
