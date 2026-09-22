from datetime import datetime, timezone

from app.infrastructure.classificacao.busca_fuzzy import buscar_conta_por_similaridade


def test_retorna_conta_do_nome_mais_similar():
    historico = [
        ("ENERGISA CEARA", 10, datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("CLARO SA", 20, datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    resultado = buscar_conta_por_similaridade("ENERGISA CE", historico)
    assert resultado is not None
    conta_id, score = resultado
    assert conta_id == 10
    assert 0.0 < score <= 1.0


def test_sem_historico_retorna_none():
    assert buscar_conta_por_similaridade("ENERGISA", []) is None


def test_nome_alvo_none_retorna_none():
    historico = [("ENERGISA", 10, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    assert buscar_conta_por_similaridade(None, historico) is None


def test_empate_de_score_usa_candidato_mais_recente():
    historico = [
        ("ENERGISA", 10, datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("ENERGISA", 20, datetime(2026, 1, 5, tzinfo=timezone.utc)),
    ]
    conta_id, _ = buscar_conta_por_similaridade("ENERGISA", historico)
    assert conta_id == 20


def test_empate_de_score_com_datas_naive_e_aware_misturadas_nao_estoura():
    # Reproduz o histórico real de um lote: candidatos lidos do banco (SQLite
    # não preserva timezone, viram naive) misturados com candidatos criados
    # na mesma sessão (timezone-aware, default Python).
    historico = [
        ("ENERGISA", 10, datetime(2026, 1, 1)),
        ("ENERGISA", 20, datetime(2026, 1, 5, tzinfo=timezone.utc)),
    ]
    conta_id, _ = buscar_conta_por_similaridade("ENERGISA", historico)
    assert conta_id == 20
