import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# Em produção a chave vem de uma variável de ambiente (SECRET_KEY).
# O valor abaixo serve só para desenvolvimento.
SECRET_KEY = os.getenv("SECRET_KEY", "chave-apenas-para-desenvolvimento-troque-em-producao")
ALGORITMO = "HS256"
MINUTOS_DE_VALIDADE = 30


def gerar_hash(senha: str) -> str:
    """Transforma a senha em um hash bcrypt (não dá para voltar ao texto original)."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    except ValueError:  # por exemplo, senha longa demais para o bcrypt
        return False


# Hash usado quando o e-mail não existe, para o login gastar o mesmo tempo
# nos dois casos e não revelar quais e-mails estão cadastrados.
HASH_FALSO = gerar_hash("senha-que-nao-existe")


def criar_token(usuario_id: int) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_DE_VALIDADE)
    return jwt.encode({"sub": str(usuario_id), "exp": expira}, SECRET_KEY, algorithm=ALGORITMO)


def ler_token(token: str) -> int | None:
    """Devolve o id do usuário se o token for válido e não tiver expirado; senão, None."""
    try:
        dados = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])
        return int(dados["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None