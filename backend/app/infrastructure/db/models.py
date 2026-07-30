from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import NaturezaConta
from app.infrastructure.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmpresaModel(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    planos_contas: Mapped[list["PlanoContasModel"]] = relationship(
        back_populates="empresa"
    )


class PlanoContasModel(Base):
    __tablename__ = "planos_contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    empresa: Mapped["EmpresaModel"] = relationship(back_populates="planos_contas")
    contas: Mapped[list["ContaModel"]] = relationship(back_populates="plano_contas")


class ContaModel(Base):
    __tablename__ = "contas"
    __table_args__ = (
        UniqueConstraint("plano_conta_id", "codigo", name="uq_contas_plano_codigo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plano_conta_id: Mapped[int] = mapped_column(
        ForeignKey("planos_contas.id"), nullable=False, index=True
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    natureza: Mapped[NaturezaConta] = mapped_column(
        String(20), nullable=False
    )
    conta_analitica: Mapped[bool] = mapped_column(Boolean, nullable=False)
    conta_pai_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id"), nullable=True, index=True
    )

    plano_contas: Mapped["PlanoContasModel"] = relationship(back_populates="contas")


class DocumentoModel(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    extensao: Mapped[str] = mapped_column(String(10), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE")
    mensagem_erro: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class OcrResultadoModel(Base):
    __tablename__ = "ocr_resultados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id"), nullable=False, unique=True
    )
    texto_extraido: Mapped[str] = mapped_column(Text, nullable=False)
    metodo: Mapped[str] = mapped_column(String(20), nullable=False)
    tempo_processamento_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class LoteProcessamentoModel(Base):
    __tablename__ = "lotes_processamento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    total_documentos: Mapped[int] = mapped_column(Integer, nullable=False)
    documentos_processados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="EM_ANDAMENTO")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtracaoModel(Base):
    __tablename__ = "extracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id"), nullable=False, unique=True
    )
    pagador_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pagador_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    recebedor_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recebedor_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_documento: Mapped[str] = mapped_column(String(20), nullable=False, default="OUTRO")
    banco_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class RegraModel(Base):
    __tablename__ = "regras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), nullable=False)
    lado_alvo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    documento_fiscal: Mapped[str | None] = mapped_column(String(14), nullable=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    valor_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    valor_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    palavra_chave_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ClassificacaoModel(Base):
    __tablename__ = "classificacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True
    )
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id"), nullable=False, unique=True
    )
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), nullable=False)
    origem: Mapped[str] = mapped_column(String(20), nullable=False)
    regra_id: Mapped[int | None] = mapped_column(ForeignKey("regras.id"), nullable=True)
    score_similaridade: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AprendizadoModel(Base):
    __tablename__ = "aprendizado"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class HistoricoAlteracaoModel(Base):
    __tablename__ = "historico_alteracoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class UsuarioModel(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class LogModel(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ConfiguracaoModel(Base):
    __tablename__ = "configuracoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
