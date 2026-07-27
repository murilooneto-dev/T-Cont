import pytest

from app.core.exceptions import ArquivoInvalido
from app.infrastructure.storage.file_storage import (
    LocalFileStorageService,
    validar_extensao_e_tamanho,
)


def test_validar_extensao_permitida():
    assert validar_extensao_e_tamanho("comprovante.PDF", 1000) == ".pdf"


def test_validar_extensao_nao_permitida_falha():
    with pytest.raises(ArquivoInvalido, match="não permitida"):
        validar_extensao_e_tamanho("virus.exe", 1000)


def test_validar_tamanho_excedido_falha():
    with pytest.raises(ArquivoInvalido, match="tamanho máximo"):
        validar_extensao_e_tamanho("comprovante.pdf", 21 * 1024 * 1024)


def test_salvar_gera_nome_fisico_diferente_do_original_e_grava_arquivo(tmp_path):
    storage = LocalFileStorageService(tmp_path)

    nome_fisico, caminho_relativo, extensao = storage.salvar(
        empresa_id=1, nome_original="../../etc/passwd.pdf", conteudo=b"conteudo-teste"
    )

    assert extensao == ".pdf"
    assert nome_fisico != "../../etc/passwd.pdf"
    assert ".." not in caminho_relativo
    caminho_absoluto = tmp_path / caminho_relativo
    assert caminho_absoluto.exists()
    assert caminho_absoluto.read_bytes() == b"conteudo-teste"


def test_salvar_com_arquivo_invalido_nao_grava_nada(tmp_path):
    storage = LocalFileStorageService(tmp_path)

    with pytest.raises(ArquivoInvalido):
        storage.salvar(empresa_id=1, nome_original="malware.exe", conteudo=b"x")

    assert list(tmp_path.rglob("*")) == []


def test_ler_retorna_conteudo_salvo(tmp_path):
    storage = LocalFileStorageService(tmp_path)
    _, caminho_relativo, _ = storage.salvar(1, "a.pdf", "olá".encode("utf-8"))

    assert storage.ler(caminho_relativo) == "olá".encode("utf-8")
