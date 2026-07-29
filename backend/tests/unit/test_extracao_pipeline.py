from datetime import date
from decimal import Decimal

from app.domain.enums import TipoDocumento
from app.infrastructure.extracao.pipeline import extrair_dados_documento


def test_extrai_todos_os_campos_de_um_comprovante_completo():
    texto = (
        "Comprovante de Transferência PIX\n"
        "Pagador: Joao da Silva Ltda\n"
        "CPF: 123.456.789-00\n"
        "Favorecido: Energisa S.A.\n"
        "CNPJ: 12.345.678/0001-95\n"
        "Valor: R$ 1.234,56\n"
        "Data do pagamento: 15/03/2026\n"
        "Banco Itaú Unibanco\n"
    )

    dados = extrair_dados_documento(texto)

    assert dados.tipo_documento == TipoDocumento.PIX
    assert dados.pagador_nome == "JOAO DA SILVA"
    assert dados.pagador_documento == "12345678900"
    assert dados.recebedor_nome == "ENERGISA"
    assert dados.recebedor_documento == "12345678000195"
    assert dados.valor == Decimal("1234.56")
    assert dados.data_pagamento == date(2026, 3, 15)
    assert dados.banco_nome == "Itaú"


def test_campos_ausentes_ficam_none_e_tipo_fica_outro():
    dados = extrair_dados_documento("Texto sem nenhum campo reconhecível.")

    assert dados.tipo_documento == TipoDocumento.OUTRO
    assert dados.pagador_nome is None
    assert dados.pagador_documento is None
    assert dados.recebedor_nome is None
    assert dados.recebedor_documento is None
    assert dados.valor is None
    assert dados.data_pagamento is None
    assert dados.banco_nome is None


def test_apenas_um_documento_no_texto_vira_pagador_recebedor_fica_none():
    texto = "Pagador: Joao da Silva\nCPF: 123.456.789-00\nValor: R$50,00"

    dados = extrair_dados_documento(texto)

    assert dados.pagador_documento == "12345678900"
    assert dados.recebedor_documento is None
