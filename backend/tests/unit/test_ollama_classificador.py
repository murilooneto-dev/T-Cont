from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.domain.entities import Conta, Extracao
from app.domain.enums import NaturezaConta, TipoDocumento
from app.infrastructure.ia.ollama_classificador import classificar_por_ia


def _extracao(**overrides):
    base = dict(
        id=1, documento_id=1, pagador_nome="JOAO", pagador_documento="12345678900",
        recebedor_nome="ENERGISA", recebedor_documento="12345678000195",
        valor=Decimal("150.00"), data_pagamento=None, tipo_documento=TipoDocumento.PIX,
        banco_nome=None,
    )
    base.update(overrides)
    return Extracao(**base)


def _conta(id_, codigo, descricao="Conta Teste"):
    return Conta(
        id=id_, plano_conta_id=1, codigo=codigo, descricao=descricao,
        natureza=NaturezaConta.DESPESA, conta_analitica=True,
    )


def test_classifica_com_resposta_valida():
    contas = [_conta(1, "1"), _conta(2, "2")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "2"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) == 2


def test_resposta_nenhuma_retorna_none():
    contas = [_conta(1, "1")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "NENHUMA"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) is None


def test_resposta_com_codigo_inexistente_retorna_none():
    contas = [_conta(1, "1")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "99"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) is None


def test_falha_de_conexao_retorna_none_sem_lancar():
    contas = [_conta(1, "1")]
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post",
        side_effect=Exception("conexão recusada"),
    ):
        assert classificar_por_ia(_extracao(), contas) is None


def test_sem_contas_disponiveis_retorna_none():
    assert classificar_por_ia(_extracao(), []) is None


def test_resposta_com_espacos_e_case_diferente_ainda_casa():
    contas = [_conta(1, "10")]
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "  10  \n"}
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.infrastructure.ia.ollama_classificador.httpx.post", return_value=mock_response
    ):
        assert classificar_por_ia(_extracao(), contas) == 1
