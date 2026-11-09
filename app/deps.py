from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Perfil, Usuario
from app.security import ler_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def usuario_atual(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> Usuario:
    """Descobre quem está logado. Sem token válido, devolve 401 (RN01 e RN14)."""
    erro = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    usuario_id = ler_token(token)
    if usuario_id is None:
        raise erro
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise erro
    return usuario


def exigir_perfil(*perfis: Perfil):
    """Permite a rota só para os perfis informados; os outros recebem 403."""

    def verificador(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if usuario.perfil not in perfis:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seu perfil não tem permissão para esta operação",
            )
        return usuario

    return verificador