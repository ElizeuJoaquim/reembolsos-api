from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import usuario_atual
from app.models import Departamento, Perfil, Usuario
from app.schemas import DepartamentoSaida, UsuarioAtualizacao, UsuarioCadastro, UsuarioSaida
from app.security import gerar_hash, verificar_senha

router = APIRouter(tags=["Usuários"])


@router.get("/departamentos", response_model=list[DepartamentoSaida], summary="Listar departamentos")
def listar_departamentos(db: Session = Depends(get_db)):
    return db.scalars(select(Departamento).order_by(Departamento.nome)).all()


@router.post("/usuarios", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED,
             summary="Cadastrar usuário (sempre como colaborador)")
def cadastrar(entrada: UsuarioCadastro, db: Session = Depends(get_db)):
    if db.get(Departamento, entrada.departamento_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Departamento não encontrado")
    if db.scalar(select(Usuario.id).where(Usuario.email == entrada.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com este e-mail")

    usuario = Usuario(
        nome=entrada.nome,
        email=entrada.email,
        senha_hash=gerar_hash(entrada.senha),  # RN13: a senha nunca é guardada em texto
        perfil=Perfil.colaborador,  # RN15: o perfil nunca vem do cliente
        departamento_id=entrada.departamento_id,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com este e-mail")
    db.refresh(usuario)
    return usuario


@router.patch("/usuarios/me", response_model=UsuarioSaida, summary="Alterar meu nome ou minha senha")
def atualizar_meus_dados(
    entrada: UsuarioAtualizacao,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    dados = entrada.model_dump(exclude_unset=True, exclude_none=True)
    if not dados:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe ao menos um campo para alterar")

    if "nova_senha" in dados:
        if not verificar_senha(entrada.senha_atual, usuario.senha_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Senha atual incorreta")
        usuario.senha_hash = gerar_hash(entrada.nova_senha)
    if "nome" in dados:
        usuario.nome = dados["nome"]

    db.commit()
    db.refresh(usuario)
    return usuario