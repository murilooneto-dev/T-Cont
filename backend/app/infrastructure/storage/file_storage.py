import uuid
from datetime import datetime
from pathlib import Path

from app.application.ports import ArmazenamentoArquivos
from app.core.exceptions import ArquivoInvalido

EXTENSOES_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg"}
TAMANHO_MAXIMO_BYTES = 20 * 1024 * 1024


def validar_extensao_e_tamanho(nome_original: str, tamanho_bytes: int) -> str:
    extensao = Path(nome_original).suffix.lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        permitidas = ", ".join(sorted(EXTENSOES_PERMITIDAS))
        raise ArquivoInvalido(
            f"Extensão '{extensao or '(sem extensão)'}' não permitida. Use: {permitidas}"
        )
    if tamanho_bytes > TAMANHO_MAXIMO_BYTES:
        limite_mb = TAMANHO_MAXIMO_BYTES // (1024 * 1024)
        raise ArquivoInvalido(f"Arquivo excede o tamanho máximo de {limite_mb}MB.")
    return extensao


class LocalFileStorageService(ArmazenamentoArquivos):
    def __init__(self, storage_root: Path):
        self._storage_root = Path(storage_root)

    def salvar(
        self, empresa_id: int, nome_original: str, conteudo: bytes
    ) -> tuple[str, str, str]:
        extensao = validar_extensao_e_tamanho(nome_original, len(conteudo))
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nome_fisico = f"{timestamp}_{uuid.uuid4().hex[:8]}{extensao}"

        pasta_empresa = self._storage_root / f"empresa_{empresa_id}" / "documentos"
        pasta_empresa.mkdir(parents=True, exist_ok=True)

        caminho_absoluto = pasta_empresa / nome_fisico
        caminho_absoluto.write_bytes(conteudo)

        caminho_relativo = f"empresa_{empresa_id}/documentos/{nome_fisico}"
        return nome_fisico, caminho_relativo, extensao

    def ler(self, caminho_relativo: str) -> bytes:
        return (self._storage_root / caminho_relativo).read_bytes()

    def apagar(self, caminho_relativo: str) -> None:
        caminho_absoluto = self._storage_root / caminho_relativo
        caminho_absoluto.unlink(missing_ok=True)
