from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import TipoDocumento
from app.infrastructure.extracao.banco import extrair_banco
from app.infrastructure.extracao.data import extrair_data
from app.infrastructure.extracao.documento_fiscal import extrair_documentos
from app.infrastructure.extracao.nomes import extrair_pagador, extrair_recebedor
from app.infrastructure.extracao.tipo_documento import extrair_tipo_documento
from app.infrastructure.extracao.valor import extrair_valor


@dataclass
class DadosExtraidos:
    pagador_nome: str | None
    pagador_documento: str | None
    recebedor_nome: str | None
    recebedor_documento: str | None
    valor: Decimal | None
    data_pagamento: date | None
    tipo_documento: TipoDocumento
    banco_nome: str | None


def extrair_dados_documento(texto: str) -> DadosExtraidos:
    documentos = extrair_documentos(texto)
    return DadosExtraidos(
        pagador_nome=extrair_pagador(texto),
        pagador_documento=documentos[0] if documentos else None,
        recebedor_nome=extrair_recebedor(texto),
        recebedor_documento=documentos[1] if len(documentos) > 1 else None,
        valor=extrair_valor(texto),
        data_pagamento=extrair_data(texto),
        tipo_documento=extrair_tipo_documento(texto),
        banco_nome=extrair_banco(texto),
    )
