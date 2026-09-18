from app.application.use_cases.classificacao_use_cases import (
    CorrigirClassificacaoEmLoteUseCase, CorrigirClassificacaoUseCase,
)
from app.domain.entities import Conta, Documento, NaturezaConta, PlanoContas
from app.domain.enums import OrigemClassificacao
from tests.fakes import (
    FakeAprendizadoRepository, FakeClassificacaoRepository, FakeContaRepository,
    FakeDocumentoRepository, FakeExtracaoRepository, FakePlanoContasRepository,
    FakeRegraRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    extracao_repo = FakeExtracaoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    regra_repo = FakeRegraRepository()
    aprendizado_repo = FakeAprendizadoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    documentos = [
        documento_repo.criar(
            Documento(
                id=None, empresa_id=1, nome_arquivo=f"{i}.pdf", nome_exibicao=f"{i}.pdf",
                caminho_arquivo=f"x/{i}.pdf", extensao=".pdf", tamanho_bytes=10,
            )
        )
        for i in range(3)
    ]
    corrigir_use_case = CorrigirClassificacaoUseCase(
        documento_repo, extracao_repo, classificacao_repo, regra_repo,
        aprendizado_repo, conta_repo, plano_repo,
    )
    return {"corrigir_use_case": corrigir_use_case, "conta": conta, "documentos": documentos}


def test_lote_com_todos_sucesso():
    ambiente = _ambiente()
    ids = [d.id for d in ambiente["documentos"]]

    resultados = CorrigirClassificacaoEmLoteUseCase(ambiente["corrigir_use_case"]).executar(
        ids, ambiente["conta"].id
    )

    assert len(resultados) == 3
    assert all(r.sucesso for r in resultados)
    assert all(r.classificacao.origem == OrigemClassificacao.MANUAL for r in resultados)
    assert all(r.erro is None for r in resultados)


def test_lote_com_falha_parcial_nao_interrompe_os_outros():
    ambiente = _ambiente()
    ids = [ambiente["documentos"][0].id, 9999, ambiente["documentos"][1].id]

    resultados = CorrigirClassificacaoEmLoteUseCase(ambiente["corrigir_use_case"]).executar(
        ids, ambiente["conta"].id
    )

    assert len(resultados) == 3
    assert resultados[0].sucesso is True
    assert resultados[1].sucesso is False
    assert resultados[1].erro is not None
    assert resultados[1].classificacao is None
    assert resultados[2].sucesso is True


def test_lote_vazio_retorna_lista_vazia():
    ambiente = _ambiente()

    resultados = CorrigirClassificacaoEmLoteUseCase(ambiente["corrigir_use_case"]).executar(
        [], ambiente["conta"].id
    )

    assert resultados == []
