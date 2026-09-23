from datetime import date
from decimal import Decimal

import pytest

from app.application.use_cases.exportacao_use_cases import (
    ExportacaoDocumentos,
    ExportarDocumentosUseCase,
    LinhaExportacao,
)
from app.core.exceptions import EmpresaNaoEncontrada
from app.domain.entities import (
    Classificacao, Conta, Documento, Empresa, Extracao, PlanoContas,
)
from app.domain.enums import (
    DirecaoLancamento, NaturezaConta, OrigemClassificacao, StatusDocumento, TipoDocumento,
)
from tests.fakes import (
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakeEmpresaRepository,
    FakeExtracaoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    empresa_repo = FakeEmpresaRepository()
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    empresa = empresa_repo.criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=empresa.id, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    return {
        "empresa_repo": empresa_repo, "documento_repo": documento_repo,
        "extracao_repo": extracao_repo, "classificacao_repo": classificacao_repo,
        "conta_repo": conta_repo, "empresa": empresa, "conta": conta,
    }


def _documento(ambiente, nome="a.pdf", status=StatusDocumento.CONCLUIDO, empresa_id=None):
    return ambiente["documento_repo"].criar(
        Documento(
            id=None,
            empresa_id=empresa_id if empresa_id is not None else ambiente["empresa"].id,
            nome_arquivo=nome, nome_exibicao=nome, caminho_arquivo=f"x/{nome}",
            extensao=".pdf", tamanho_bytes=10, status=status,
        )
    )


def _use_case(ambiente):
    return ExportarDocumentosUseCase(
        ambiente["empresa_repo"], ambiente["documento_repo"], ambiente["extracao_repo"],
        ambiente["classificacao_repo"], ambiente["conta_repo"],
    )


def test_empresa_inexistente_levanta_erro():
    ambiente = _ambiente()

    with pytest.raises(EmpresaNaoEncontrada):
        _use_case(ambiente).executar(999)


def test_empresa_sem_documentos_devolve_cnpj_e_nenhuma_linha():
    ambiente = _ambiente()

    resultado = _use_case(ambiente).executar(ambiente["empresa"].id)

    assert isinstance(resultado, ExportacaoDocumentos)
    assert resultado.cnpj_empresa == "12345678000199"
    assert resultado.linhas == []


@pytest.mark.parametrize(
    "status",
    [StatusDocumento.PENDENTE, StatusDocumento.PROCESSANDO, StatusDocumento.ERRO],
)
def test_documento_nao_concluido_nao_entra(status):
    ambiente = _ambiente()
    _documento(ambiente, status=status)

    resultado = _use_case(ambiente).executar(ambiente["empresa"].id)

    assert resultado.linhas == []


def test_linha_completa_traz_extracao_e_classificacao():
    ambiente = _ambiente()
    documento = _documento(ambiente, nome="comprovante.pdf")
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome="Tesserato",
            pagador_documento="12345678000199", recebedor_nome="Energisa",
            recebedor_documento="11222333000199", valor=Decimal("150.00"),
            data_pagamento=date(2026, 9, 18), tipo_documento=TipoDocumento.PIX,
            banco_nome="Itau",
        )
    )
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=ambiente["empresa"].id, documento_id=documento.id,
            conta_id=ambiente["conta"].id, origem=OrigemClassificacao.REGRA,
        )
    )

    linhas = _use_case(ambiente).executar(ambiente["empresa"].id).linhas

    assert linhas == [
        LinhaExportacao(
            arquivo="comprovante.pdf", data_pagamento=date(2026, 9, 18),
            valor=Decimal("150.00"), tipo="PIX", pagador_nome="Tesserato",
            pagador_documento="12345678000199", recebedor_nome="Energisa",
            recebedor_documento="11222333000199", banco_nome="Itau",
            debito_codigo=None, debito_descricao=None,
            credito_codigo=None, credito_descricao=None, origem="REGRA",
        )
    ]


def test_campos_none_ou_em_branco_viram_none():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None,
            pagador_documento="", recebedor_nome="   ", recebedor_documento=None,
            valor=None, data_pagamento=None, tipo_documento=TipoDocumento.OUTRO,
            banco_nome=None,
        )
    )

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha.pagador_nome is None
    assert linha.pagador_documento is None
    assert linha.recebedor_nome is None
    assert linha.recebedor_documento is None
    assert linha.banco_nome is None
    assert linha.valor is None
    assert linha.data_pagamento is None
    assert linha.tipo == "OUTRO"


def test_documento_sem_extracao_nem_classificacao_so_traz_o_arquivo():
    ambiente = _ambiente()
    _documento(ambiente, nome="solto.pdf")

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha == LinhaExportacao(
        arquivo="solto.pdf", data_pagamento=None, valor=None, tipo=None,
        pagador_nome=None, pagador_documento=None, recebedor_nome=None,
        recebedor_documento=None, banco_nome=None, debito_codigo=None,
        debito_descricao=None, credito_codigo=None, credito_descricao=None, origem=None,
    )


def test_conta_deletada_deixa_colunas_de_conta_vazias_mas_mantem_a_origem():
    ambiente = _ambiente()
    documento = _documento(ambiente)
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=ambiente["empresa"].id, documento_id=documento.id,
            conta_id=9999, origem=OrigemClassificacao.MANUAL,
        )
    )

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha.debito_codigo is None
    assert linha.debito_descricao is None
    assert linha.credito_codigo is None
    assert linha.credito_descricao is None
    assert linha.origem == "MANUAL"


def test_debito_e_credito_resolvidos_a_partir_da_direcao_e_conta_bancaria():
    ambiente = _ambiente()
    conta_bancaria = ambiente["conta_repo"].criar(
        Conta(
            id=None, plano_conta_id=ambiente["conta"].plano_conta_id, codigo="2",
            descricao="Banco Itau", natureza=NaturezaConta.ATIVO, conta_analitica=True,
        )
    )
    documento = _documento(ambiente, nome="comprovante.pdf")
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome="Tesserato",
            pagador_documento="12345678000199", recebedor_nome="Energisa",
            recebedor_documento="11222333000199", valor=Decimal("150.00"),
            data_pagamento=date(2026, 9, 18), tipo_documento=TipoDocumento.PIX,
            banco_nome="Itau",
        )
    )
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=ambiente["empresa"].id, documento_id=documento.id,
            conta_id=ambiente["conta"].id, origem=OrigemClassificacao.REGRA,
            conta_bancaria_id=conta_bancaria.id, direcao=DirecaoLancamento.PAGAMENTO,
        )
    )

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha.debito_codigo == ambiente["conta"].codigo
    assert linha.debito_descricao == ambiente["conta"].descricao
    assert linha.credito_codigo == conta_bancaria.codigo
    assert linha.credito_descricao == conta_bancaria.descricao


def test_documento_concluido_sem_classificacao_traz_colunas_de_conta_vazias():
    ambiente = _ambiente()
    documento = _documento(ambiente, nome="sem_classificacao.pdf")
    ambiente["extracao_repo"].criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome="Tesserato",
            pagador_documento="12345678000199", recebedor_nome="Energisa",
            recebedor_documento="11222333000199", valor=Decimal("150.00"),
            data_pagamento=date(2026, 9, 18), tipo_documento=TipoDocumento.PIX,
            banco_nome="Itau",
        )
    )

    linha = _use_case(ambiente).executar(ambiente["empresa"].id).linhas[0]

    assert linha.debito_codigo is None
    assert linha.debito_descricao is None
    assert linha.credito_codigo is None
    assert linha.credito_descricao is None


def test_nao_inclui_documentos_de_outra_empresa():
    ambiente = _ambiente()
    _documento(ambiente, nome="outra.pdf", empresa_id=999)

    resultado = _use_case(ambiente).executar(ambiente["empresa"].id)

    assert resultado.linhas == []


def test_preserva_a_ordem_de_listagem_dos_documentos():
    ambiente = _ambiente()
    _documento(ambiente, nome="primeiro.pdf")
    _documento(ambiente, nome="segundo.pdf")

    linhas = _use_case(ambiente).executar(ambiente["empresa"].id).linhas

    assert [linha.arquivo for linha in linhas] == ["primeiro.pdf", "segundo.pdf"]
