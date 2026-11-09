import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Valores fixos permitidos ----------
class Perfil(str, enum.Enum):
    colaborador = "colaborador"
    gestor = "gestor"
    financeiro = "financeiro"


class Categoria(str, enum.Enum):
    alimentacao = "alimentacao"
    transporte = "transporte"
    hospedagem = "hospedagem"
    material = "material"


class Situacao(str, enum.Enum):
    rascunho = "rascunho"
    aguardando_gestor = "aguardando_gestor"
    aguardando_financeiro = "aguardando_financeiro"
    aprovada = "aprovada"
    paga = "paga"
    recusada = "recusada"


class Etapa(str, enum.Enum):
    gestor = "gestor"
    financeiro = "financeiro"
    pagamento = "pagamento"


class Decisao(str, enum.Enum):
    aprovada = "aprovada"
    recusada = "recusada"
    paga = "paga"


# ---------- Tabelas ----------
class Departamento(Base):
    __tablename__ = "departamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="departamento")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))  # nunca guardamos a senha em texto
    perfil: Mapped[Perfil] = mapped_column(Enum(Perfil))
    departamento_id: Mapped[int] = mapped_column(ForeignKey("departamentos.id"))

    departamento: Mapped["Departamento"] = relationship(back_populates="usuarios")
    reembolsos: Mapped[list["Reembolso"]] = relationship(back_populates="solicitante")


class Reembolso(Base):
    __tablename__ = "reembolsos"
    __table_args__ = (
        # RN05: o mesmo colaborador não repete a referência do comprovante
        UniqueConstraint("solicitante_id", "comprovante_ref", name="uq_solicitante_comprovante"),
        # RN04: valor sempre maior que zero (segunda barreira, dentro do banco)
        CheckConstraint("valor_centavos > 0", name="ck_valor_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    categoria: Mapped[Categoria] = mapped_column(Enum(Categoria))
    valor_centavos: Mapped[int]  # dinheiro em centavos (R$ 180,00 = 18000)
    data_despesa: Mapped[date] = mapped_column(Date)
    justificativa: Mapped[str] = mapped_column(Text)
    comprovante_ref: Mapped[str] = mapped_column(String(100))
    situacao: Mapped[Situacao] = mapped_column(Enum(Situacao), default=Situacao.rascunho)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    solicitante: Mapped["Usuario"] = relationship(back_populates="reembolsos")
    historico: Mapped[list["HistoricoAnalise"]] = relationship(
        back_populates="reembolso", order_by="HistoricoAnalise.id"
    )


class HistoricoAnalise(Base):
    __tablename__ = "historico_analises"

    id: Mapped[int] = mapped_column(primary_key=True)
    reembolso_id: Mapped[int] = mapped_column(ForeignKey("reembolsos.id"))
    responsavel_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    etapa: Mapped[Etapa] = mapped_column(Enum(Etapa))
    decisao: Mapped[Decisao] = mapped_column(Enum(Decisao))
    data: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)
    observacao: Mapped[str | None] = mapped_column(Text)

    reembolso: Mapped["Reembolso"] = relationship(back_populates="historico")
    responsavel: Mapped["Usuario"] = relationship()