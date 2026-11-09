"""Cria departamentos e usuários de exemplo. Pode ser executado várias vezes."""

from sqlalchemy import select

from app import models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.models import Departamento, Perfil, Usuario
from app.security import gerar_hash

SENHA_PADRAO = "Senha@123"  # só para demonstração

DEPARTAMENTOS = ["Comercial", "Tecnologia", "Financeiro"]

USUARIOS = [
    ("Ana", "ana@nexuscorp.com", Perfil.colaborador, "Comercial"),
    ("Bruno", "bruno@nexuscorp.com", Perfil.colaborador, "Tecnologia"),
    ("Patrícia", "patricia@nexuscorp.com", Perfil.gestor, "Comercial"),
    ("Carlos", "carlos@nexuscorp.com", Perfil.gestor, "Tecnologia"),
    ("Fernanda", "fernanda@nexuscorp.com", Perfil.financeiro, "Financeiro"),
]


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        deptos = {}
        for nome in DEPARTAMENTOS:
            depto = db.scalar(select(Departamento).where(Departamento.nome == nome))
            if depto is None:
                depto = Departamento(nome=nome)
                db.add(depto)
                db.flush()
            deptos[nome] = depto

        for nome, email, perfil, nome_depto in USUARIOS:
            if db.scalar(select(Usuario).where(Usuario.email == email)) is None:
                db.add(
                    Usuario(
                        nome=nome,
                        email=email,
                        senha_hash=gerar_hash(SENHA_PADRAO),
                        perfil=perfil,
                        departamento_id=deptos[nome_depto].id,
                    )
                )
        db.commit()
    print("Dados de exemplo criados.")


if __name__ == "__main__":
    main()