from app.application.repositories import (
    ClassificacaoRepository, ContaRepository, DocumentoRepository, PlanoContasRepository,
)
from app.application.use_cases.classificacao_use_cases import _validar_conta
from app.core.exceptions import ClassificacaoNaoEncontrada, DocumentoNaoEncontrado
from app.domain.entities import Classificacao


class CorrigirContaBancariaUseCase:
    """Corrige só o lado bancário do lançamento (conta_bancaria_id), sem tocar
    na conta de contrapartida nem na direção já resolvida — é o caminho de
    revisão manual para quando `resolver_conta_bancaria` não conseguiu decidir
    sozinho (banco não identificado, ou múltiplas contas do mesmo banco).
    """

    def __init__(
        self,
        documento_repo: DocumentoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
        plano_repo: PlanoContasRepository,
    ):
        self._documento_repo = documento_repo
        self._classificacao_repo = classificacao_repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, documento_id: int, conta_bancaria_id: int) -> Classificacao:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        _validar_conta(self._conta_repo, self._plano_repo, conta_bancaria_id, documento.empresa_id)

        classificacao_existente = self._classificacao_repo.obter_por_documento_id(documento_id)
        if classificacao_existente is None:
            raise ClassificacaoNaoEncontrada(documento_id)

        classificacao_existente.conta_bancaria_id = conta_bancaria_id
        return self._classificacao_repo.atualizar(classificacao_existente)
