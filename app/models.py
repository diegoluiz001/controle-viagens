"""Modelos ORM: descrição das tabelas empresa, linha e viagem.

Este arquivo é a fonte usada pelo Alembic (autogenerate) para gerar as migrations.
Regras que o autogenerate não enxerga (sequence avulsa e trigger de updated_at)
são escritas manualmente na migration.
"""
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    MetaData,
    Sequence,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.enums import MotivoNaoRealizacao, StatusViagem

# Nomes previsíveis para constraints e índices (ck_, uq_, fk_, ix_, pk_).
# Sem isso o Postgres gera nomes automáticos, difíceis de alterar em migrations futuras.
CONVENCAO_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


def _valores_sql(enum) -> str:
    """Converte um Enum em lista SQL: 'REALIZADA', 'NAO_REALIZADA'."""
    return ", ".join(f"'{item.value}'" for item in enum)


# Sequence exclusiva do identificador de negócio (VG0181, VG0182...).
# É independente da sequence implícita do SERIAL de viagem.id (chave primária interna).
viagem_codigo_seq = Sequence("viagem_codigo_seq", metadata=Base.metadata)


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("codigo ~ '^[0-9]{3}$'", name="codigo_formato"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(3), unique=True)
    nome: Mapped[str] = mapped_column(String(100))

    linhas: Mapped[list["Linha"]] = relationship(back_populates="empresa")


class Linha(Base):
    __tablename__ = "linha"
    __table_args__ = (
        UniqueConstraint("empresa_id", "codigo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="RESTRICT"))
    codigo: Mapped[str] = mapped_column(String(10))
    descricao: Mapped[str] = mapped_column(String(120))

    empresa: Mapped[Empresa] = relationship(back_populates="linhas")
    viagens: Mapped[list["Viagem"]] = relationship(back_populates="linha")


class Viagem(Base):
    __tablename__ = "viagem"
    __table_args__ = (
        CheckConstraint("id_viagem ~ '^VG[0-9]{4,}$'", name="id_viagem_formato"),
        CheckConstraint(f"status IN ({_valores_sql(StatusViagem)})", name="status_valido"),
        CheckConstraint(
            f"motivo_nao_realizacao IN ({_valores_sql(MotivoNaoRealizacao)})",
            name="motivo_valido",
        ),
        CheckConstraint(
            "(status = 'REALIZADA' AND motivo_nao_realizacao IS NULL)"
            " OR (status = 'NAO_REALIZADA' AND motivo_nao_realizacao IS NOT NULL)",
            name="status_motivo_coerente",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    id_viagem: Mapped[str] = mapped_column(String(20), unique=True)
    linha_id: Mapped[int] = mapped_column(
        ForeignKey("linha.id", ondelete="RESTRICT"), index=True
    )
    data_viagem: Mapped[date] = mapped_column(Date, index=True)
    horario_programado: Mapped[time] = mapped_column(Time)
    veiculo: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(13))
    motivo_nao_realizacao: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # O valor é mantido pelo trigger trg_viagem_updated_at (criado na migration).
    # FetchedValue avisa o SQLAlchemy para reler o campo após um UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )

    linha: Mapped[Linha] = relationship(back_populates="viagens")
