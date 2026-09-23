import pytest

from app.application.use_cases.conta_bancaria_use_cases import CorrigirContaBancariaUseCase
from app.core.exceptions import (
    ClassificacaoNaoEncontrada,
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
from app.domain.entities import Classificacao, Conta, Documento, PlanoContas
from app.domain.enums import DirecaoLancamento, NaturezaConta, OrigemClassificacao
from tests.fakes import (
    FakeClassificacaoRepository,
    FakeContaRepository,
    FakeDocumentoRepository,
    FakePlanoContasRepository,
)


def _ambiente():
    documento_repo = FakeDocumentoRepository()
    classificacao_repo = FakeClassificacaoRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano"))
    conta_contrapartida = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="3.2.01", descricao="Despesa",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    conta_banco = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1.1.01.002.00001",
            descricao="Banco do Brasil", natureza=NaturezaConta.ATIVO, conta_analitica=True,
        )
    )
    documento = documento_repo.criar(
        Documento(
            id=None, empresa_id=1, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    return {
        "documento_repo": documento_repo, "classificacao_repo": classificacao_repo,
        "conta_repo": conta_repo, "plano_repo": plano_repo, "documento": documento,
        "conta_contrapartida": conta_contrapartida, "conta_banco": conta_banco,
    }


def _use_case(ambiente):
    return CorrigirContaBancariaUseCase(
        ambiente["documento_repo"], ambiente["classificacao_repo"],
        ambiente["conta_repo"], ambiente["plano_repo"],
    )


def test_corrige_conta_bancaria_preservando_direcao_e_contrapartida():
    ambiente = _ambiente()
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=ambiente["documento"].id,
            conta_id=ambiente["conta_contrapartida"].id, origem=OrigemClassificacao.REGRA,
            direcao=DirecaoLancamento.PAGAMENTO, conta_bancaria_id=None,
        )
    )

    resultado = _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta_banco"].id)

    assert resultado.conta_bancaria_id == ambiente["conta_banco"].id
    assert resultado.direcao == DirecaoLancamento.PAGAMENTO
    assert resultado.conta_id == ambiente["conta_contrapartida"].id
    assert resultado.origem == OrigemClassificacao.REGRA


def test_documento_inexistente_leva_a_erro():
    ambiente = _ambiente()
    with pytest.raises(DocumentoNaoEncontrado):
        _use_case(ambiente).executar(999, ambiente["conta_banco"].id)


def test_sem_classificacao_existente_leva_a_erro():
    ambiente = _ambiente()
    with pytest.raises(ClassificacaoNaoEncontrada):
        _use_case(ambiente).executar(ambiente["documento"].id, ambiente["conta_banco"].id)


def test_conta_inexistente_leva_a_erro():
    ambiente = _ambiente()
    ambiente["classificacao_repo"].criar(
        Classificacao(
            id=None, empresa_id=1, documento_id=ambiente["documento"].id,
            conta_id=ambiente["conta_contrapartida"].id, origem=OrigemClassificacao.REGRA,
        )
    )
    with pytest.raises(ContaNaoEncontrada):
        _use_case(ambiente).executar(ambiente["documento"].id, 999)
