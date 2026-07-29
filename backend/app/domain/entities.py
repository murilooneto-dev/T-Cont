from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.enums import MetodoOcr, NaturezaConta, StatusDocumento, StatusLote, TipoDocumento


@dataclass
class Empresa:
    id: int | None
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    ativo: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PlanoContas:
    id: int | None
    empresa_id: int
    nome: str
    versao: int = 1
    ativo: bool = True
    created_at: datetime | None = None


@dataclass
class Conta:
    id: int | None
    plano_conta_id: int
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None

    def validar_uso_em_lancamento(self) -> None:
        if not self.conta_analitica:
            raise ValueError(
                f"Conta {self.codigo} é uma conta sintética e não pode ser usada em lançamentos."
            )


@dataclass
class Documento:
    id: int | None
    empresa_id: int
    nome_arquivo: str
    nome_exibicao: str
    caminho_arquivo: str
    extensao: str
    tamanho_bytes: int
    status: StatusDocumento = StatusDocumento.PENDENTE
    mensagem_erro: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OcrResultado:
    id: int | None
    documento_id: int
    texto_extraido: str
    metodo: MetodoOcr
    tempo_processamento_ms: int
    created_at: datetime | None = None


@dataclass
class LoteProcessamento:
    id: int | None
    empresa_id: int
    total_documentos: int
    documentos_processados: int = 0
    status: StatusLote = StatusLote.EM_ANDAMENTO
    created_at: datetime | None = None
    concluido_em: datetime | None = None


@dataclass
class Extracao:
    id: int | None
    documento_id: int
    pagador_nome: str | None
    pagador_documento: str | None
    recebedor_nome: str | None
    recebedor_documento: str | None
    valor: Decimal | None
    data_pagamento: date | None
    tipo_documento: TipoDocumento
    banco_nome: str | None
    created_at: datetime | None = None
