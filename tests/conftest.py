"""Preparação dos testes: cada teste recebe um banco novo, vazio e em memória."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Departamento, Usuario
from app.security import gerar_hash
from seed import DEPARTAMENTOS, SENHA_PADRAO, USUARIOS  # mesmos dados do seed.py

# O hash é calculado uma única vez para os testes ficarem rápidos
HASH_PADRAO = gerar_hash(SENHA_PADRAO)


def _ativar_chaves_estrangeiras(conexao, _registro):
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _popular(db) -> None:
    departamentos = {}
    for nome in DEPARTAMENTOS:
        departamento = Departamento(nome=nome)
        db.add(departamento)
        db.flush()
        departamentos[nome] = departamento

    for nome, email, perfil, nome_departamento in USUARIOS:
        db.add(
            Usuario(
                nome=nome,
                email=email,
                senha_hash=HASH_PADRAO,
                perfil=perfil,
                departamento_id=departamentos[nome_departamento].id,
            )
        )
    db.commit()


@pytest.fixture()
def client():
    """Cliente de teste ligado a um banco novo (SQLite em memória)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _ativar_chaves_estrangeiras)
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with sessao() as db:
        _popular(db)

    def get_db_teste():
        db = sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = get_db_teste
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def auth(client):
    """Devolve uma função que faz login e entrega o cabeçalho com o token."""

    def entrar(email: str) -> dict:
        resposta = client.post("/auth/login", data={"username": email, "password": SENHA_PADRAO})
        assert resposta.status_code == 200, resposta.text
        return {"Authorization": f"Bearer {resposta.json()['access_token']}"}

    return entrar