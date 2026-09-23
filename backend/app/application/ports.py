from abc import ABC, abstractmethod


class ArmazenamentoArquivos(ABC):
    @abstractmethod
    def salvar(
        self, empresa_id: int, nome_original: str, conteudo: bytes
    ) -> tuple[str, str, str]:
        """Retorna (nome_fisico, caminho_relativo, extensao)."""

    @abstractmethod
    def ler(self, caminho_relativo: str) -> bytes: ...

    @abstractmethod
    def apagar(self, caminho_relativo: str) -> None:
        """Remove o arquivo físico. Não lança exceção se ele já não existir."""


class OcrEngine(ABC):
    @abstractmethod
    def extrair_texto(self, imagem_bytes: bytes) -> str: ...
