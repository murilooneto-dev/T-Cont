import pytest

from app.application.dto import AtualizarRegraDTO, CriarRegraDTO
from app.application.use_cases.regra_use_cases import (
    AtualizarRegraUseCase,
    CriarRegraUseCase,
    DeletarRegraUseCase,
    ListarRegrasUseCase,
)
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    RegraDocumentoFiscalInvalido,
    RegraNaoEncontrada,
    RegraSemCondicoes,
    RegraSemLadoAlvo,
)
from app.domain.entities import Conta, PlanoContas
from app.domain.enums import NaturezaConta
from tests.fakes import FakeContaRepository, FakePlanoContasRepository, FakeRegraRepository


def _plano_e_conta(plano_repo, conta_repo, empresa_id=1, conta_analitica=True):
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=empresa_id, nome="Plano"))
    conta = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=conta_analitica,
        )
    )
    return plano, conta


def _dto(conta_id, **overrides):
    base = dict(
        conta_id=conta_id, lado_alvo="RECEBEDOR", documento_fiscal="12345678000195",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
    )
    base.update(overrides)
    return CriarRegraDTO(**base)


def test_criar_regra_com_sucesso():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)

    regra = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    assert regra.id is not None
    assert regra.empresa_id == 1
    assert regra.conta_id == conta.id


def test_criar_regra_com_conta_inexistente_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()

    with pytest.raises(ContaNaoEncontrada):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(999))


def test_criar_regra_com_conta_de_outra_empresa_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=2)

    with pytest.raises(ContaNaoPertenceAEmpresa):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))


def test_criar_regra_com_conta_sintetica_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1, conta_analitica=False)

    with pytest.raises(ContaNaoAnalitica):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))


def test_criar_regra_sem_nenhuma_condicao_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(
        conta.id, lado_alvo=None, documento_fiscal=None, tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome=None,
    )

    with pytest.raises(RegraSemCondicoes):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)


def test_criar_regra_com_palavra_chave_sem_lado_alvo_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(
        conta.id, lado_alvo=None, documento_fiscal=None, tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome="ENERGISA",
    )

    with pytest.raises(RegraSemLadoAlvo):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)


def test_criar_regra_normaliza_cnpj_pontuado():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(conta.id, documento_fiscal="12.345.678/0001-95")

    regra = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)

    assert regra.documento_fiscal == "12345678000195"


def test_criar_regra_com_documento_fiscal_invalido_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(conta.id, documento_fiscal="123")

    with pytest.raises(RegraDocumentoFiscalInvalido):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)


def test_criar_regra_com_palavra_chave_so_espaco_falha_como_sem_condicoes():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto = _dto(
        conta.id, lado_alvo="RECEBEDOR", documento_fiscal=None, tipo_documento=None,
        valor_min=None, valor_max=None, palavra_chave_nome="   ",
    )

    with pytest.raises(RegraSemCondicoes):
        CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, dto)


def test_listar_regras_por_empresa():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    regras = ListarRegrasUseCase(regra_repo).executar(1)

    assert len(regras) == 1


def test_atualizar_regra_com_sucesso():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    dto_update = AtualizarRegraDTO(
        conta_id=conta.id, lado_alvo="RECEBEDOR", documento_fiscal="99999999000191",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=False,
    )
    atualizada = AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(
        1, criada.id, dto_update
    )

    assert atualizada.documento_fiscal == "99999999000191"
    assert atualizada.ativo is False


def test_atualizar_regra_inexistente_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    dto_update = AtualizarRegraDTO(
        conta_id=conta.id, lado_alvo="RECEBEDOR", documento_fiscal="99999999000191",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=True,
    )

    with pytest.raises(RegraNaoEncontrada):
        AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, 999, dto_update)


def test_atualizar_regra_de_outra_empresa_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))
    dto_update = AtualizarRegraDTO(
        conta_id=conta.id, lado_alvo="RECEBEDOR", documento_fiscal="99999999000191",
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=True,
    )

    with pytest.raises(RegraNaoEncontrada):
        AtualizarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(2, criada.id, dto_update)


def test_deletar_regra():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    DeletarRegraUseCase(regra_repo).executar(1, criada.id)

    assert regra_repo.obter_por_id(criada.id) is None


def test_deletar_regra_de_outra_empresa_falha():
    regra_repo = FakeRegraRepository()
    conta_repo = FakeContaRepository()
    plano_repo = FakePlanoContasRepository()
    _, conta = _plano_e_conta(plano_repo, conta_repo, empresa_id=1)
    criada = CriarRegraUseCase(regra_repo, conta_repo, plano_repo).executar(1, _dto(conta.id))

    with pytest.raises(RegraNaoEncontrada):
        DeletarRegraUseCase(regra_repo).executar(2, criada.id)
