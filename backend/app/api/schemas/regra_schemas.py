from decimal import Decimal

from pydantic import BaseModel

from app.domain.enums import LadoRegra, TipoDocumento


class RegraCreateIn(BaseModel):
    conta_id: int
    lado_alvo: LadoRegra | None = None
    documento_fiscal: str | None = None
    tipo_documento: TipoDocumento | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    palavra_chave_nome: str | None = None


class RegraUpdateIn(RegraCreateIn):
    ativo: bool = True


class RegraOut(BaseModel):
    id: int
    empresa_id: int
    conta_id: int
    lado_alvo: LadoRegra | None
    documento_fiscal: str | None
    tipo_documento: TipoDocumento | None
    valor_min: str | None
    valor_max: str | None
    palavra_chave_nome: str | None
    ativo: bool

    @classmethod
    def from_regra(cls, regra) -> "RegraOut":
        return cls(
            id=regra.id,
            empresa_id=regra.empresa_id,
            conta_id=regra.conta_id,
            lado_alvo=regra.lado_alvo,
            documento_fiscal=regra.documento_fiscal,
            tipo_documento=regra.tipo_documento,
            valor_min=str(regra.valor_min) if regra.valor_min is not None else None,
            valor_max=str(regra.valor_max) if regra.valor_max is not None else None,
            palavra_chave_nome=regra.palavra_chave_nome,
            ativo=regra.ativo,
        )
