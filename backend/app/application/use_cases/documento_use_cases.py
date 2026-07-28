from app.application.dto import ArquivoUploadDTO, ResultadoUploadDTO
from app.application.ports import ArmazenamentoArquivos
from app.application.repositories import (
    DocumentoRepository,
    EmpresaRepository,
    OcrResultadoRepository,
)
from app.core.exceptions import ArquivoInvalido, DocumentoNaoEncontrado, EmpresaNaoEncontrada
from app.domain.entities import Documento, OcrResultado


class UploadarDocumentosUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        empresa_repo: EmpresaRepository,
        storage: ArmazenamentoArquivos,
    ):
        self._documento_repo = documento_repo
        self._empresa_repo = empresa_repo
        self._storage = storage

    def executar(
        self, empresa_id: int, arquivos: list[ArquivoUploadDTO]
    ) -> list[ResultadoUploadDTO]:
        if self._empresa_repo.obter_por_id(empresa_id) is None:
            raise EmpresaNaoEncontrada(empresa_id)

        resultados: list[ResultadoUploadDTO] = []
        for arquivo in arquivos:
            if arquivo.erro_previo:
                resultados.append(
                    ResultadoUploadDTO(
                        documento=None,
                        nome_original=arquivo.nome_original,
                        erro=arquivo.erro_previo,
                    )
                )
                continue
            try:
                nome_fisico, caminho_relativo, extensao = self._storage.salvar(
                    empresa_id, arquivo.nome_original, arquivo.conteudo
                )
            except ArquivoInvalido as exc:
                resultados.append(
                    ResultadoUploadDTO(documento=None, nome_original=arquivo.nome_original, erro=str(exc))
                )
                continue

            documento = Documento(
                id=None,
                empresa_id=empresa_id,
                nome_arquivo=nome_fisico,
                nome_exibicao=arquivo.nome_original,
                caminho_arquivo=caminho_relativo,
                extensao=extensao,
                tamanho_bytes=len(arquivo.conteudo),
            )
            criado = self._documento_repo.criar(documento)
            resultados.append(
                ResultadoUploadDTO(documento=criado, nome_original=arquivo.nome_original, erro=None)
            )
        return resultados


class ListarDocumentosUseCase:
    def __init__(self, repo: DocumentoRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> list[Documento]:
        return self._repo.listar_por_empresa(empresa_id)


class ObterResultadoUseCase:
    def __init__(self, documento_repo: DocumentoRepository, resultado_repo: OcrResultadoRepository):
        self._documento_repo = documento_repo
        self._resultado_repo = resultado_repo

    def executar(self, documento_id: int) -> tuple[Documento, OcrResultado | None]:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        resultado = self._resultado_repo.obter_por_documento_id(documento_id)
        return documento, resultado
