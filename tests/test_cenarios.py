"""Testes automáticos dos cenários de homologação da NexusCorp (Cenários 01 a 08)
e das principais regras de negócio.

Executar na raiz do projeto, com o ambiente virtual ativo:
    pytest -v
"""

from datetime import date, datetime, timedelta, timezone

import jwt

from app.security import ALGORITMO, SECRET_KEY

ANA = "ana@nexuscorp.com"  # colaboradora, Comercial
BRUNO = "bruno@nexuscorp.com"  # colaborador, Tecnologia
PATRICIA = "patricia@nexuscorp.com"  # gestora, Comercial
CARLOS = "carlos@nexuscorp.com"  # gestor, Tecnologia
FERNANDA = "fernanda@nexuscorp.com"  # financeiro


# ---------- Funções de apoio ----------
def corpo(**mudancas) -> dict:
    dados = {
        "categoria": "transporte",
        "valor": 180.00,
        "data_despesa": (date.today() - timedelta(days=1)).isoformat(),
        "justificativa": "Corrida de táxi para reunião com cliente",
        "comprovante_ref": "NF-0001",
    }
    dados.update(mudancas)
    return dados


def criar(client, headers, **mudancas) -> int:
    resposta = client.post("/reembolsos", json=corpo(**mudancas), headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def criar_e_enviar(client, headers, **mudancas) -> int:
    reembolso_id = criar(client, headers, **mudancas)
    resposta = client.post(f"/reembolsos/{reembolso_id}/enviar", headers=headers)
    assert resposta.status_code == 200, resposta.text
    return reembolso_id


def decidir(client, headers, reembolso_id, etapa, decisao, observacao=None):
    """etapa: 'gestor' ou 'financeiro'."""
    dados = {"decisao": decisao}
    if observacao:
        dados["observacao"] = observacao
    return client.post(f"/reembolsos/{reembolso_id}/analise-{etapa}", json=dados, headers=headers)


def pagar(client, headers, reembolso_id):
    return client.post(f"/reembolsos/{reembolso_id}/pagamento", json={}, headers=headers)


def depto_id(client, nome: str) -> int:
    departamentos = client.get("/departamentos").json()
    return next(d["id"] for d in departamentos if d["nome"] == nome)


# ---------- Cenários do professor ----------
def test_cenario_01_colaborador_nao_acessa_solicitacao_de_outro_colaborador(client, auth):
    ana, bruno = auth(ANA), auth(BRUNO)
    id_bruno = criar(client, bruno, valor=1234.56, comprovante_ref="NF-SECRETA")

    resposta = client.get(f"/reembolsos/{id_bruno}", headers=ana)

    assert resposta.status_code == 403
    assert set(resposta.json()) == {"detail"}  # nenhum dado da solicitação
    assert "1234" not in resposta.text
    assert "NF-SECRETA" not in resposta.text


def test_cenario_02_gestor_de_outro_departamento_nao_aprova(client, auth):
    bruno, patricia, carlos = auth(BRUNO), auth(PATRICIA), auth(CARLOS)
    id_bruno = criar_e_enviar(client, bruno)

    resposta = decidir(client, patricia, id_bruno, "gestor", "aprovada")

    assert resposta.status_code == 403
    detalhe = client.get(f"/reembolsos/{id_bruno}", headers=carlos).json()
    assert detalhe["situacao"] == "aguardando_gestor"  # nada foi alterado
    assert detalhe["historico"] == []


def test_cenario_03_senha_incorreta_e_recusada_sem_revelar_detalhes(client):
    senha_errada = client.post("/auth/login", data={"username": ANA, "password": "senha-errada"})
    email_inexistente = client.post(
        "/auth/login", data={"username": "fantasma@nexuscorp.com", "password": "senha-errada"}
    )

    assert senha_errada.status_code == 401
    assert email_inexistente.status_code == 401
    # a mesma resposta nos dois casos: não revela quais e-mails existem
    assert senha_errada.json() == email_inexistente.json() == {"detail": "E-mail ou senha incorretos"}
    assert "access_token" not in senha_errada.text


def test_cenario_04_nao_e_possivel_alterar_perfil_nem_departamento(client, auth):
    ana = auth(ANA)
    antes = client.get("/auth/me", headers=ana).json()

    tentativas = [
        client.patch("/usuarios/me", json={"perfil": "financeiro"}, headers=ana),
        client.patch(
            "/usuarios/me", json={"departamento_id": depto_id(client, "Financeiro")}, headers=ana
        ),
        client.post("/reembolsos", json=corpo(perfil="financeiro"), headers=ana),
    ]
    for resposta in tentativas:
        assert resposta.status_code == 422
        assert any(erro["type"] == "extra_forbidden" for erro in resposta.json()["detail"])

    depois = client.get("/auth/me", headers=ana).json()
    assert depois == antes
    assert depois["perfil"] == "colaborador"


def test_cenario_04_colaborador_nao_usa_rotas_do_financeiro(client, auth):
    ana = auth(ANA)
    id_ana = criar_e_enviar(client, ana)

    assert decidir(client, ana, id_ana, "financeiro", "aprovada").status_code == 403
    assert pagar(client, ana, id_ana).status_code == 403
    assert client.get("/reembolsos/financeiro", headers=ana).status_code == 403


def test_cenario_05_financeiro_nao_aprova_antes_do_gestor(client, auth):
    ana, fernanda = auth(ANA), auth(FERNANDA)
    id_ana = criar_e_enviar(client, ana)

    assert decidir(client, fernanda, id_ana, "financeiro", "aprovada").status_code == 409
    assert pagar(client, fernanda, id_ana).status_code == 409

    detalhe = client.get(f"/reembolsos/{id_ana}", headers=ana).json()
    assert detalhe["situacao"] == "aguardando_gestor"
    assert detalhe["historico"] == []


def test_cenario_06_valor_nao_pode_ser_alterado_apos_envio(client, auth):
    ana = auth(ANA)
    id_ana = criar_e_enviar(client, ana, valor=180.00)

    resposta = client.patch(f"/reembolsos/{id_ana}", json={"valor": 1800}, headers=ana)

    assert resposta.status_code == 409
    assert client.get(f"/reembolsos/{id_ana}", headers=ana).json()["valor"] == "180.00"


def test_cenario_07_gestor_ve_apenas_pendentes_do_proprio_departamento(client, auth):
    ana, bruno, patricia = auth(ANA), auth(BRUNO), auth(PATRICIA)
    id_ana = criar_e_enviar(client, ana, comprovante_ref="NF-A1")
    id_bruno = criar_e_enviar(client, bruno, comprovante_ref="NF-B1")

    resposta = client.get(
        "/reembolsos/departamento", params={"situacao": "aguardando_gestor"}, headers=patricia
    )

    assert resposta.status_code == 200
    ids = [item["id"] for item in resposta.json()]
    assert ids == [id_ana]
    assert id_bruno not in ids

    outro_departamento = client.get(
        "/reembolsos/departamento",
        params={"departamento_id": depto_id(client, "Tecnologia")},
        headers=patricia,
    )
    assert outro_departamento.status_code == 403


def test_cenario_08_historico_completo_com_responsaveis(client, auth):
    ana, patricia, fernanda = auth(ANA), auth(PATRICIA), auth(FERNANDA)
    id_ana = criar_e_enviar(client, ana)

    assert decidir(client, patricia, id_ana, "gestor", "aprovada", "Despesa de cliente").status_code == 200
    assert decidir(client, fernanda, id_ana, "financeiro", "aprovada").status_code == 200
    assert pagar(client, fernanda, id_ana).status_code == 200

    detalhe = client.get(f"/reembolsos/{id_ana}", headers=ana).json()
    assert detalhe["situacao"] == "paga"
    percurso = [(h["etapa"], h["decisao"], h["responsavel_nome"]) for h in detalhe["historico"]]
    assert percurso == [
        ("gestor", "aprovada", "Patrícia"),
        ("financeiro", "aprovada", "Fernanda"),
        ("pagamento", "paga", "Fernanda"),
    ]
    assert all(h["data"] for h in detalhe["historico"])  # cada decisão tem data


# ---------- Regras de negócio ----------
def test_rn01_sem_login_acesso_negado(client):
    assert client.get("/reembolsos/minhas").status_code == 401
    assert client.post("/reembolsos", json=corpo()).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer token-invalido"}).status_code == 401


def test_rn04_valor_zero_ou_negativo_e_recusado(client, auth):
    ana = auth(ANA)

    for valor in (0, -10):
        assert client.post("/reembolsos", json=corpo(valor=valor), headers=ana).status_code == 422

    assert client.get("/reembolsos/minhas", headers=ana).json() == []  # nada foi gravado


def test_rn05_comprovante_repetido_e_recusado(client, auth):
    ana, bruno = auth(ANA), auth(BRUNO)
    criar(client, ana, comprovante_ref="NF-REPETIDA")

    repetido = client.post("/reembolsos", json=corpo(comprovante_ref="NF-REPETIDA"), headers=ana)
    assert repetido.status_code == 409

    # a regra vale por colaborador: outra pessoa pode usar a mesma referência
    outra_pessoa = client.post("/reembolsos", json=corpo(comprovante_ref="NF-REPETIDA"), headers=bruno)
    assert outra_pessoa.status_code == 201


def test_rn06_data_futura_e_recusada(client, auth):
    ana = auth(ANA)
    amanha = (date.today() + timedelta(days=1)).isoformat()

    resposta = client.post("/reembolsos", json=corpo(data_despesa=amanha), headers=ana)

    assert resposta.status_code == 422


def test_rn09_gestor_nao_aprova_a_propria_solicitacao(client, auth):
    patricia = auth(PATRICIA)
    id_patricia = criar_e_enviar(client, patricia)

    resposta = decidir(client, patricia, id_patricia, "gestor", "aprovada")

    assert resposta.status_code == 403


def test_rn10_pagamento_exige_aprovacao_do_financeiro(client, auth):
    ana, patricia, fernanda = auth(ANA), auth(PATRICIA), auth(FERNANDA)
    id_ana = criar_e_enviar(client, ana)
    decidir(client, patricia, id_ana, "gestor", "aprovada")

    # aprovada pelo gestor, mas ainda sem a aprovação do financeiro
    assert pagar(client, fernanda, id_ana).status_code == 409


def test_rn11_recusa_exige_justificativa_e_encerra_o_processo(client, auth):
    ana, patricia = auth(ANA), auth(PATRICIA)
    id_ana = criar_e_enviar(client, ana)

    sem_justificativa = decidir(client, patricia, id_ana, "gestor", "recusada")
    assert sem_justificativa.status_code == 422

    recusada = decidir(client, patricia, id_ana, "gestor", "recusada", "Comprovante ilegível")
    assert recusada.status_code == 200
    assert recusada.json()["situacao"] == "recusada"
    assert recusada.json()["historico"][0]["observacao"] == "Comprovante ilegível"

    # processo encerrado: nada mais pode mudar
    assert decidir(client, patricia, id_ana, "gestor", "aprovada").status_code == 409
    assert client.patch(f"/reembolsos/{id_ana}", json={"valor": 1}, headers=ana).status_code == 409
    assert client.delete(f"/reembolsos/{id_ana}", headers=ana).status_code == 409


def test_rn13_resposta_nunca_expoe_senha(client, auth):
    ana = auth(ANA)

    meus_dados = client.get("/auth/me", headers=ana)

    assert set(meus_dados.json()) == {"id", "nome", "email", "perfil", "departamento_id"}
    assert "$2b$" not in meus_dados.text  # nem o hash aparece


def test_rn14_token_expirado_e_recusado(client):
    expirado = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        SECRET_KEY,
        algorithm=ALGORITMO,
    )

    resposta = client.get("/auth/me", headers={"Authorization": f"Bearer {expirado}"})

    assert resposta.status_code == 401


def test_rn15_cadastro_comum_sempre_cria_colaborador(client):
    dados = {
        "nome": "Marcos",
        "email": "marcos@nexuscorp.com",
        "senha": "Senha@123",
        "departamento_id": depto_id(client, "Comercial"),
    }

    criado = client.post("/usuarios", json=dados)
    assert criado.status_code == 201
    assert criado.json()["perfil"] == "colaborador"
    assert "senha" not in criado.json() and "senha_hash" not in criado.json()

    login = client.post("/auth/login", data={"username": dados["email"], "password": "Senha@123"})
    assert login.status_code == 200

    tentativa = client.post("/usuarios", json={**dados, "email": "outro@nexuscorp.com", "perfil": "gestor"})
    assert tentativa.status_code == 422


def test_gestor_nao_ve_rascunho_de_colaborador(client, auth):
    ana, patricia = auth(ANA), auth(PATRICIA)
    id_rascunho = criar(client, ana)

    assert client.get(f"/reembolsos/{id_rascunho}", headers=patricia).status_code == 403
    assert client.get("/reembolsos/departamento", headers=patricia).json() == []


def test_financeiro_so_ve_solicitacoes_aprovadas_pelo_gestor(client, auth):
    ana, patricia, fernanda = auth(ANA), auth(PATRICIA), auth(FERNANDA)
    aprovada = criar_e_enviar(client, ana, comprovante_ref="NF-1")
    pendente = criar_e_enviar(client, ana, comprovante_ref="NF-2")
    decidir(client, patricia, aprovada, "gestor", "aprovada")

    lista = client.get("/reembolsos/financeiro", headers=fernanda)

    assert lista.status_code == 200
    assert [item["id"] for item in lista.json()] == [aprovada]
    assert client.get(f"/reembolsos/{pendente}", headers=fernanda).status_code == 403