from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class OcrResultadoModel(Base):
    __tablename__ = "ocr_resultados"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ExtracaoModel(Base):
    __tablename__ = "extracoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ClassificacaoModel(Base):
    __tablename__ = "classificacoes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
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
