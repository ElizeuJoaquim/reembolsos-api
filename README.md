# NexusCorp: Plataforma de Gestão de Reembolsos

API REST em Python (FastAPI) para centralizar a gestão de reembolsos corporativos da NexusCorp, com identificação de usuários, controle de acesso por perfil, fluxo de aprovação e histórico completo das decisões.

## Funcionalidades

- **Colaborador**: registra, consulta, altera (enquanto rascunho), exclui (enquanto rascunho) e envia para análise as suas solicitações de reembolso, e acompanha a situação e o histórico de cada uma.
- **Gestor**: consulta as solicitações do seu departamento e as aprova ou recusa.
- **Financeiro**: consulta as solicitações já aprovadas por um gestor, faz a análise final e registra o pagamento.
- **Todos os perfis**: login com token, consulta de filtros por situação e categoria (e por departamento, quando permitido) e alteração dos próprios dados (nome e senha).

O ciclo de vida de uma solicitação é:

`rascunho` → `aguardando_gestor` → `aguardando_financeiro` → `aprovada` → `paga`

Uma recusa (do gestor ou do financeiro, sempre com justificativa) encerra o processo na situação `recusada`.

## Tecnologias

| Item | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| API | FastAPI |
| Banco de dados | SQLite (relacional), acessado com SQLAlchemy |
| Autenticação | Token JWT (PyJWT) |
| Senhas | bcrypt |
| Testes | pytest e TestClient |

## Como executar

Pré-requisito: Python 3.12 ou superior.

```bash
# 1. Criar e ativar o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar as dependências
pip install -r requirements.txt

# 3. Criar o banco e os usuários de demonstração
python seed.py

# 4. Iniciar a API
uvicorn app.main:app --reload
```

A API fica em `http://127.0.0.1:8000`. O arquivo do banco (`reembolsos.db`) é criado na pasta do projeto.

Para começar do zero, apague o arquivo `reembolsos.db` e rode `python seed.py` novamente.

## Usuários de demonstração

Todos usam a senha `Senha@123` (apenas para demonstração).

| Nome | E-mail | Perfil | Departamento |
|---|---|---|---|
| Ana | ana@nexuscorp.com | Colaborador | Comercial |
| Bruno | bruno@nexuscorp.com | Colaborador | Tecnologia |
| Patrícia | patricia@nexuscorp.com | Gestor | Comercial |
| Carlos | carlos@nexuscorp.com | Gestor | Tecnologia |
| Fernanda | fernanda@nexuscorp.com | Financeiro | Financeiro |

## Documentação da API

Com a API em execução:

- Swagger (interativo, com botão **Authorize** para o login): `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Contrato OpenAPI (JSON): `http://127.0.0.1:8000/openapi.json`

No Swagger, clique em **Authorize**, informe o e-mail em `username` e a senha em `password`, e todas as rotas protegidas passam a usar o token.

## Testes automatizados

```bash
pytest -v
```

São 21 testes: um para cada cenário de homologação (Cenários 01 a 08) e outros para as regras de negócio. Cada teste usa um banco novo, em memória, com os cinco usuários de demonstração. Por isso os testes não dependem uns dos outros e não alteram o arquivo `reembolsos.db`.

## Estrutura do projeto

```
reembolsos-api/
├── app/
│   ├── main.py            # cria a aplicação e registra as rotas
│   ├── database.py        # conexão com o banco SQLite
│   ├── models.py          # tabelas e relacionamentos (SQLAlchemy)
│   ├── schemas.py         # contratos de entrada e saída (Pydantic)
│   ├── security.py        # hash de senha (bcrypt) e token (JWT)
│   ├── deps.py            # identificação do usuário e controle de perfil
│   └── routers/
│       ├── auth.py        # login e dados do usuário logado
│       ├── usuarios.py    # cadastro, alteração dos próprios dados, departamentos
│       ├── reembolsos.py  # operações do colaborador e listas por perfil
│       └── analises.py    # aprovação, recusa e pagamento
├── tests/
│   ├── conftest.py        # banco de testes em memória
│   └── test_cenarios.py   # cenários do professor e regras de negócio
├── docs/
│   └── documentacao-tecnica.md
├── evidencias/            # prints das execuções e das tentativas bloqueadas
├── seed.py                # departamentos e usuários de demonstração
├── pytest.ini
└── requirements.txt
```

## Documentação técnica

A descrição da solução, o modelo de dados, o contrato das operações, a matriz de permissões, as regras de negócio e as decisões de segurança estão em [`docs/documentacao-tecnica.md`](docs/documentacao-tecnica.md).

## Evidências

A pasta [`evidencias/`](evidencias/) reúne os prints numerados, na ordem da demonstração: execução das operações de cada perfil, tentativas de acesso não autorizado, o fluxo completo de aprovação e o resultado do `pytest -v`.
