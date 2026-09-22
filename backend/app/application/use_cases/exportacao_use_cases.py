from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.application.repositories import (
    ClassificacaoRepository,
    ContaRepository,
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
)
from app.core.exceptions import EmpresaNaoEncontrada
from app.domain.enums import StatusDocumento


@dataclass
class LinhaExportacao:
    arquivo: str
    data_pagamento: date | None
    valor: Decimal | None
    tipo: str | None
    pagador_nome: str | None
    pagador_documento: str | None
    recebedor_nome: str | None
    recebedor_documento: str | None
    banco_nome: str | None
    conta_codigo: str | None
    conta_descricao: str | None
    origem: str | None


@dataclass
class ExportacaoDocumentos:
    cnpj_empresa: str
    linhas: list[LinhaExportacao]


def _texto(valor: str | None) -> str | None:
    return (valor or "").strip() or None


class ExportarDocumentosUseCase:
    def __init__(
        self,
        empresa_repo: EmpresaRepository,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
    ):
        self._empresa_repo = empresa_repo
        self._documento_repo = documento_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._conta_repo = conta_repo

    def executar(self, empresa_id: int) -> ExportacaoDocumentos:
        empresa = self._empresa_repo.obter_por_id(empresa_id)
        if empresa is None:
            raise EmpresaNaoEncontrada(empresa_id)

        linhas: list[LinhaExportacao] = []
        for documento in self._documento_repo.listar_por_empresa(empresa_id):
            if documento.status != StatusDocumento.CONCLUIDO:
                continue
            extracao = self._extracao_repo.obter_por_documento_id(documento.id)
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            conta = (
                self._conta_repo.obter_por_id(classificacao.conta_id)
                if classificacao is not None
                else None
            )
            linhas.append(
                LinhaExportacao(
                    arquivo=documento.nome_exibicao,
                    data_pagamento=extracao.data_pagamento if extracao else None,
                    valor=extracao.valor if extracao else None,
                    tipo=extracao.tipo_documento.value if extracao else None,
                    pagador_nome=_texto(extracao.pagador_nome) if extracao else None,
                    pagador_documento=_texto(extracao.pagador_documento) if extracao else None,
                    recebedor_nome=_texto(extracao.recebedor_nome) if extracao else None,
                    recebedor_documento=(
                        _texto(extracao.recebedor_documento) if extracao else None
                    ),
                    banco_nome=_texto(extracao.banco_nome) if extracao else None,
                    conta_codigo=conta.codigo if conta else None,
                    conta_descricao=conta.descricao if conta else None,
                    origem=classificacao.origem.value if classificacao else None,
                )
            )
        return ExportacaoDocumentos(cnpj_empresa=empresa.cnpj, linhas=linhas)
