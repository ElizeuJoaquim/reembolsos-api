from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Categoria, Decisao, Etapa, Perfil, Reembolso, Situacao


# ---------- Autenticação ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioSaida(BaseModel):
    """O que a API mostra de um usuário. Não existe campo de senha aqui (RN13)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    perfil: Perfil
    departamento_id: int


# ---------- Reembolsos: entrada ----------
def _data_nao_futura(data: date | None) -> date | None:
    if data is not None and data > date.today():  # RN06
        raise ValueError("A data da despesa não pode ser futura")
    return data


class ReembolsoEntrada(BaseModel):
    # extra="forbid": qualquer campo desconhecido (perfil, situacao, solicitante_id...)
    # faz a API recusar o pedido com 422 (RN15 e Cenário 04)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    categoria: Categoria
    valor: Decimal = Field(gt=0, max_digits=10, decimal_places=2)  # RN04
    data_despesa: date
    justificativa: str = Field(min_length=3, max_length=500)
    comprovante_ref: str = Field(min_length=1, max_length=100)

    @field_validator("data_despesa")
    @classmethod
    def validar_data(cls, data: date) -> date:
        return _data_nao_futura(data)


class ReembolsoAtualizacao(BaseModel):
    """Alteração parcial: só os campos enviados são modificados."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    categoria: Categoria | None = None
    valor: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    data_despesa: date | None = None
    justificativa: str | None = Field(default=None, min_length=3, max_length=500)
    comprovante_ref: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("data_despesa")
    @classmethod
    def validar_data(cls, data: date | None) -> date | None:
        return _data_nao_futura(data)


# ---------- Reembolsos: saída ----------
class HistoricoSaida(BaseModel):
    id: int
    etapa: Etapa
    decisao: Decisao
    responsavel_id: int
    responsavel_nome: str
    data: datetime
    observacao: str | None


class ReembolsoSaida(BaseModel):
    id: int
    solicitante_id: int
    categoria: Categoria
    valor: Decimal
    data_despesa: date
    justificativa: str
    comprovante_ref: str
    situacao: Situacao
    criado_em: datetime


class ReembolsoDetalhe(ReembolsoSaida):
    historico: list[HistoricoSaida]


def _em_reais(centavos: int) -> Decimal:
    return (Decimal(centavos) / 100).quantize(Decimal("0.01"))


def reembolso_para_saida(r: Reembolso) -> ReembolsoSaida:
    return ReembolsoSaida(
        id=r.id,
        solicitante_id=r.solicitante_id,
        categoria=r.categoria,
        valor=_em_reais(r.valor_centavos),
        data_despesa=r.data_despesa,
        justificativa=r.justificativa,
        comprovante_ref=r.comprovante_ref,
        situacao=r.situacao,
        criado_em=r.criado_em,
    )


def reembolso_para_detalhe(r: Reembolso) -> ReembolsoDetalhe:
    historico = [
        HistoricoSaida(
            id=h.id,
            etapa=h.etapa,
            decisao=h.decisao,
            responsavel_id=h.responsavel_id,
            responsavel_nome=h.responsavel.nome,
            data=h.data,
            observacao=h.observacao,
        )
        for h in r.historico
    ]
    return ReembolsoDetalhe(**reembolso_para_saida(r).model_dump(), historico=historico)


# ---------- Análise e pagamento ----------
class DecisaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decisao: Literal["aprovada", "recusada"]
    observacao: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def exigir_justificativa_na_recusa(self):
        if self.decisao == "recusada" and not self.observacao:  # RN11
            raise ValueError("Toda recusa precisa de uma justificativa no campo observacao")
        return self


class PagamentoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    observacao: str | None = Field(default=None, max_length=500)


# ---------- Usuários e departamentos ----------
class DepartamentoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


def _validar_senha(senha: str) -> str:
    if len(senha.encode("utf-8")) > 72:  # limite do bcrypt
        raise ValueError("A senha deve ter no máximo 72 caracteres")
    return senha


class UsuarioCadastro(BaseModel):
    # Não existe campo "perfil" aqui: todo cadastro comum nasce como colaborador (RN15)
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    senha: str = Field(min_length=8)
    departamento_id: int

    @field_validator("nome", mode="before")
    @classmethod
    def limpar_nome(cls, nome):
        return nome.strip() if isinstance(nome, str) else nome

    @field_validator("email")
    @classmethod
    def email_minusculo(cls, email: str) -> str:
        return email.lower()

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, senha: str) -> str:
        return _validar_senha(senha)


class UsuarioAtualizacao(BaseModel):
    """O próprio usuário só pode alterar nome e senha (RN15)."""

    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(default=None, min_length=2, max_length=100)
    senha_atual: str | None = None
    nova_senha: str | None = Field(default=None, min_length=8)

    @field_validator("nome", mode="before")
    @classmethod
    def limpar_nome(cls, nome):
        return nome.strip() if isinstance(nome, str) else nome

    @field_validator("nova_senha")
    @classmethod
    def validar_nova_senha(cls, senha: str | None) -> str | None:
        return _validar_senha(senha) if senha is not None else None

    @model_validator(mode="after")
    def senhas_juntas(self):
        if (self.nova_senha is None) != (self.senha_atual is None):
            raise ValueError("Para trocar a senha, informe senha_atual e nova_senha juntas")
        return self