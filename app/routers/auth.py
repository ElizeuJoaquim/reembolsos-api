from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import usuario_atual
from app.models import Usuario
from app.schemas import Token, UsuarioSaida
from app.security import HASH_FALSO, criar_token, verificar_senha

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=Token, summary="Entrar no sistema")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))

    # Sempre confere um hash, exista o usuário ou não (mesmo tempo de resposta)
    senha_ok = verificar_senha(form.password, usuario.senha_hash if usuario else HASH_FALSO)

    if usuario is None or not senha_ok:
        # Mensagem única: não revela se o e-mail existe nem o que está errado (Cenário 03)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=criar_token(usuario.id))


@router.get("/me", response_model=UsuarioSaida, summary="Ver meus dados")
def meus_dados(usuario: Usuario = Depends(usuario_atual)):
    return usuario