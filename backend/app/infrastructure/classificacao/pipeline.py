from dataclasses import dataclass
from datetime import datetime

from app.domain.entities import Conta, Extracao, Regra
from app.domain.enums import OrigemClassificacao
from app.infrastructure.classificacao.busca_fuzzy import buscar_conta_por_similaridade
from app.infrastructure.classificacao.motor_regras import encontrar_regra_mais_especifica
from app.infrastructure.ia.ollama_classificador import classificar_por_ia


@dataclass
class ResultadoClassificacao:
    conta_id: int
    origem: OrigemClassificacao
    regra_id: int | None
    score_similaridade: float | None


def classificar_documento(
    extracao: Extracao,
    regras: list[Regra],
    contas_disponiveis: list[Conta],
    historico_fuzzy: list[tuple[str, int, datetime]],
) -> ResultadoClassificacao | None:
    regra = encontrar_regra_mais_especifica(extracao, regras)
    if regra is not None:
        return ResultadoClassificacao(
            conta_id=regra.conta_id,
            origem=OrigemClassificacao.REGRA,
            regra_id=regra.id,
            score_similaridade=None,
        )

    conta_id_ia = classificar_por_ia(extracao, contas_disponiveis)
    if conta_id_ia is not None:
        return ResultadoClassificacao(
            conta_id=conta_id_ia,
            origem=OrigemClassificacao.IA,
            regra_id=None,
            score_similaridade=None,
        )

    nome_alvo = extracao.recebedor_nome or extracao.pagador_nome
    resultado_fuzzy = buscar_conta_por_similaridade(nome_alvo, historico_fuzzy)
    if resultado_fuzzy is None:
        return None
    conta_id, score = resultado_fuzzy
    return ResultadoClassificacao(
        conta_id=conta_id,
        origem=OrigemClassificacao.FUZZY,
        regra_id=None,
        score_similaridade=score,
    )
