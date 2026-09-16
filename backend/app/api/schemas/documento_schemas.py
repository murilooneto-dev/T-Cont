from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import MetodoOcr, OrigemClassificacao, StatusDocumento, TipoDocumento


class DocumentoOut(BaseModel):
    id: int
    empresa_id: int
    nome_arquivo: str
    nome_exibicao: str
    extensao: str
    tamanho_bytes: int
    status: StatusDocumento
    mensagem_erro: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadItemOut(BaseModel):
    nome_original: str
    documento: DocumentoOut | None
    erro: str | None


class OcrResultadoOut(BaseModel):
    texto_extraido: str
    metodo: MetodoOcr
    tempo_processamento_ms: int


_NAO_IDENTIFICADO = "NÃO IDENTIFICADO"


class ExtracaoOut(BaseModel):
    pagador_nome: str
    pagador_documento: str
    recebedor_nome: str
    recebedor_documento: str
    valor: str
    data_pagamento: str
    tipo_documento: TipoDocumento
    banco_nome: str

    @classmethod
    def from_extracao(cls, extracao) -> "ExtracaoOut":
        return cls(
            pagador_nome=extracao.pagador_nome or _NAO_IDENTIFICADO,
            pagador_documento=extracao.pagador_documento or _NAO_IDENTIFICADO,
            recebedor_nome=extracao.recebedor_nome or _NAO_IDENTIFICADO,
            recebedor_documento=extracao.recebedor_documento or _NAO_IDENTIFICADO,
            valor=str(extracao.valor) if extracao.valor is not None else _NAO_IDENTIFICADO,
            data_pagamento=(
                extracao.data_pagamento.isoformat()
                if extracao.data_pagamento is not None
                else _NAO_IDENTIFICADO
            ),
            tipo_documento=extracao.tipo_documento,
            banco_nome=extracao.banco_nome or _NAO_IDENTIFICADO,
        )


class ClassificacaoOut(BaseModel):
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    origem: OrigemClassificacao
    regra_id: int | None
    score_similaridade: float | None

    @classmethod
    def from_classificacao(cls, classificacao, conta) -> "ClassificacaoOut":
        return cls(
            conta_id=classificacao.conta_id,
            conta_codigo=conta.codigo,
            conta_descricao=conta.descricao,
            origem=classificacao.origem,
            regra_id=classificacao.regra_id,
            score_similaridade=classificacao.score_similaridade,
        )


class DocumentoResultadoOut(BaseModel):
    documento: DocumentoOut
    resultado: OcrResultadoOut | None
    extracao: ExtracaoOut | None
    classificacao: ClassificacaoOut | None


class CorrigirClassificacaoIn(BaseModel):
    conta_id: int
