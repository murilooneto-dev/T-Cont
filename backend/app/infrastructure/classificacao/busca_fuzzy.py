from datetime import datetime

from rapidfuzz import fuzz


def _sem_fuso(momento: datetime) -> datetime:
    """Remove o timezone para permitir comparação.

    `historico` mistura instâncias criadas nesta mesma sessão (timezone-aware,
    default Python) com instâncias recém-lidas do SQLite (naive, já que o
    SQLite não preserva timezone) — comparar as duas formas diretamente
    levanta `TypeError`. Ambas representam o mesmo instante em UTC, então
    remover o timezone antes de comparar preserva a ordenação corretamente.
    """
    return momento.replace(tzinfo=None) if momento.tzinfo is not None else momento


def buscar_conta_por_similaridade(
    nome_alvo: str | None, historico: list[tuple[str, int, datetime]]
) -> tuple[int, float] | None:
    if nome_alvo is None or not historico:
        return None

    melhor: tuple[int, float, datetime] | None = None
    for nome_historico, conta_id, created_at in historico:
        score = fuzz.ratio(nome_alvo.upper(), nome_historico.upper()) / 100.0
        if melhor is None:
            melhor = (conta_id, score, created_at)
            continue
        _, melhor_score, melhor_created_at = melhor
        if score > melhor_score or (
            score == melhor_score and _sem_fuso(created_at) > _sem_fuso(melhor_created_at)
        ):
            melhor = (conta_id, score, created_at)

    if melhor is None:
        return None
    conta_id, score, _ = melhor
    return conta_id, score
