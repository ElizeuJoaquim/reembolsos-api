from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Banco SQLite: um arquivo (reembolsos.db) criado na pasta do projeto
DATABASE_URL = "sqlite:///./reembolsos.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def ativar_chaves_estrangeiras(conexao, _registro):
    # O SQLite não confere chaves estrangeiras por padrão; aqui ligamos a conferência
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Abre uma sessão com o banco para cada requisição e fecha no final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()