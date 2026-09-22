import pytest

from app.application.use_cases.importar_plano_contas_use_cases import (
    ConfirmarImportacaoUseCase,
    PreviewImportacaoUseCase,
)
from app.core.exceptions import (
    ImportacaoPlanoContasInvalida,
    PlanoContasNaoEncontrado,
)
from app.domain.entities import PlanoContas
from app.infrastructure.spreadsheet.plano_contas_parser import LinhaPlanoContas
from tests.fakes import FakeContaRepository, FakePlanoContasRepository


@pytest.fixture
def plano_repo():
    repo = FakePlanoContasRepository()
    repo.criar(PlanoContas(id=None, empresa_id=1, nome="Plano Padrão"))
    return repo


def test_preview_retorna_mapeamento_e_linhas():
    conteudo = b"Codigo,Descricao,Natureza\n1.1.01,Caixa,ATIVO\n"

    resultado = PreviewImportacaoUseCase().executar(conteudo, "arquivo.csv")

    assert resultado.mapeamento["codigo"] == 0
    assert len(resultado.linhas) == 1


def test_preview_planilha_invalida_propaga_erro():
    conteudo = b"A,B\nx,y\n"

    with pytest.raises(ImportacaoPlanoContasInvalida):
        PreviewImportacaoUseCase().executar(conteudo, "arquivo.csv")


def test_preview_aceita_csv_latin1_sem_estourar():
    # Exportações de ERP brasileiro frequentemente vêm em cp1252/latin-1.
    conteudo = "Codigo,Descrição,Natureza\n1.1.01,Manutenção,ATIVO\n".encode("latin-1")

    resultado = PreviewImportacaoUseCase().executar(conteudo, "plano.csv")

    assert len(resultado.linhas) == 1
    assert resultado.linhas[0].codigo == "1.1.01"


def test_preview_sem_nome_de_arquivo_nao_estoura():
    conteudo = b"Codigo,Descricao,Natureza\n1.1.01,Caixa,ATIVO\n"

    resultado = PreviewImportacaoUseCase().executar(conteudo, None)

    assert len(resultado.linhas) == 1


def test_confirmar_importacao_cria_contas_com_hierarquia(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=False, conta_pai=None),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True, conta_pai="1.1"),
    ]

    contas = ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert len(contas) == 2
    pai = next(c for c in contas if c.codigo == "1.1")
    filha = next(c for c in contas if c.codigo == "1.1.01")
    assert filha.conta_pai_id == pai.id


def test_confirmar_importacao_resolve_hierarquia_com_ordem_embaralhada_e_codigos_mesmo_tamanho(plano_repo):
    # Regressão: código do pai ("100") e do filho ("101") têm o mesmo
    # comprimento, e as linhas chegam fora de ordem (neta antes da filha
    # antes da mãe). Um sort por len(codigo) não reordenaria essas linhas
    # (chaves iguais, sort estável), então o filho seria criado como conta
    # raiz. A resolução correta deve montar a cadeia completa.
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="102", descricao="Neta", natureza="ATIVO", conta_analitica=True, conta_pai="101"),
        LinhaPlanoContas(codigo="101", descricao="Filha", natureza="ATIVO", conta_analitica=False, conta_pai="100"),
        LinhaPlanoContas(codigo="100", descricao="Mae", natureza="ATIVO", conta_analitica=False, conta_pai=None),
    ]

    contas = ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert len(contas) == 3
    mae = next(c for c in contas if c.codigo == "100")
    filha = next(c for c in contas if c.codigo == "101")
    neta = next(c for c in contas if c.codigo == "102")

    assert mae.conta_pai_id is None
    assert filha.conta_pai_id == mae.id
    assert neta.conta_pai_id == filha.id


def test_confirmar_importacao_em_plano_inexistente_falha(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=True, conta_pai=None),
    ]

    with pytest.raises(PlanoContasNaoEncontrado):
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=999, linhas=linhas)

    assert repo.listar_por_plano(999) == []


def test_confirmar_importacao_falha_quando_natureza_ausente(plano_repo):
    # Antes esta importação aplicava DESPESA silenciosamente. A planilha não
    # pode adivinhar: sem natureza, a importação precisa falhar com erro claro.
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="3.1", descricao="Despesas Gerais", natureza=None, conta_analitica=None, conta_pai=None),
    ]

    with pytest.raises(ImportacaoPlanoContasInvalida) as exc:
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert "3.1" in str(exc.value)
    assert repo.listar_por_plano(1) == []


def test_confirmar_importacao_normaliza_natureza_com_caixa_e_acento(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Caixa", natureza="Ativo", conta_analitica=True, conta_pai=None),
        LinhaPlanoContas(codigo="2.1", descricao="Fornecedores", natureza=" passivo ", conta_analitica=True, conta_pai=None),
        LinhaPlanoContas(codigo="5.1", descricao="Capital Social", natureza="Patrimônio Líquido", conta_analitica=True, conta_pai=None),
    ]

    contas = ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    naturezas = {c.codigo: c.natureza.value for c in contas}
    assert naturezas == {
        "1.1": "ATIVO",
        "2.1": "PASSIVO",
        "5.1": "PATRIMONIO_LIQUIDO",
    }


def test_confirmar_importacao_falha_com_natureza_desconhecida(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="9.9", descricao="Conta Estranha", natureza="Resultado", conta_analitica=True, conta_pai=None),
    ]

    with pytest.raises(ImportacaoPlanoContasInvalida) as exc:
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert "Resultado" in str(exc.value)
    assert "9.9" in str(exc.value)
    assert repo.listar_por_plano(1) == []


def test_confirmar_importacao_deriva_conta_analitica_do_grafo(plano_repo):
    # Sem coluna de conta_analitica: a conta referenciada como conta_pai de
    # outra é sintética; a folha é analítica.
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=None, conta_pai=None),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=None, conta_pai="1.1"),
    ]

    contas = ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    analiticas = {c.codigo: c.conta_analitica for c in contas}
    assert analiticas == {"1.1": False, "1.1.01": True}


def test_confirmar_importacao_prefere_conta_analitica_explicita(plano_repo):
    # O valor explícito da planilha vence a derivação, mesmo contradizendo-a.
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=True, conta_pai=None),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=False, conta_pai="1.1"),
    ]

    contas = ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    analiticas = {c.codigo: c.conta_analitica for c in contas}
    assert analiticas == {"1.1": True, "1.1.01": False}


def test_confirmar_importacao_falha_com_codigo_em_branco(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="", descricao="SemCodigo", natureza="ATIVO", conta_analitica=True, conta_pai=None),
    ]

    with pytest.raises(ImportacaoPlanoContasInvalida) as exc:
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert "SemCodigo" in str(exc.value)
    assert repo.listar_por_plano(1) == []


def test_confirmar_importacao_falha_com_descricao_em_branco(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="   ", natureza="ATIVO", conta_analitica=True, conta_pai=None),
    ]

    with pytest.raises(ImportacaoPlanoContasInvalida) as exc:
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert "1.1" in str(exc.value)
    assert repo.listar_por_plano(1) == []


def test_confirmar_importacao_repetida_e_rejeitada(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=False, conta_pai=None),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=True, conta_pai="1.1"),
    ]

    ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)
    assert len(repo.listar_por_plano(1)) == 2

    with pytest.raises(ImportacaoPlanoContasInvalida) as exc:
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert "1.1" in str(exc.value)
    assert len(repo.listar_por_plano(1)) == 2


def test_confirmar_importacao_com_linhas_do_parser_hierarquico(plano_repo):
    # Simula exatamente a saída de _parsear_relatorio_hierarquico: natureza já
    # resolvida como string do enum, conta_analitica sempre None (derivada
    # pelo grafo pai/filho), conta_pai calculado truncando o código.
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1", descricao="ATIVO", natureza="ATIVO", conta_analitica=None, conta_pai=None),
        LinhaPlanoContas(codigo="1.1", descricao="ATIVO CIRCULANTE", natureza="ATIVO", conta_analitica=None, conta_pai="1"),
        LinhaPlanoContas(codigo="1.1.01", descricao="Caixa", natureza="ATIVO", conta_analitica=None, conta_pai="1.1"),
    ]

    contas = ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    por_codigo = {c.codigo: c for c in contas}
    assert por_codigo["1"].conta_pai_id is None
    assert por_codigo["1.1"].conta_pai_id == por_codigo["1"].id
    assert por_codigo["1.1.01"].conta_pai_id == por_codigo["1.1"].id
    assert por_codigo["1"].conta_analitica is False
    assert por_codigo["1.1"].conta_analitica is False
    assert por_codigo["1.1.01"].conta_analitica is True
    assert all(c.natureza.value == "ATIVO" for c in contas)


def test_confirmar_importacao_rejeita_codigos_repetidos_no_arquivo(plano_repo):
    repo = FakeContaRepository()
    linhas = [
        LinhaPlanoContas(codigo="1.1", descricao="Disponibilidades", natureza="ATIVO", conta_analitica=True, conta_pai=None),
        LinhaPlanoContas(codigo="1.1", descricao="Duplicada", natureza="ATIVO", conta_analitica=True, conta_pai=None),
    ]

    with pytest.raises(ImportacaoPlanoContasInvalida):
        ConfirmarImportacaoUseCase(repo, plano_repo).executar(plano_conta_id=1, linhas=linhas)

    assert repo.listar_por_plano(1) == []
