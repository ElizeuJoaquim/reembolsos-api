from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import exigir_perfil, usuario_atual
from app.models import (
    Categoria,
    Decisao,
    Etapa,
    HistoricoAnalise,
    Perfil,
    Reembolso,
    Situacao,
    Usuario,
)
from app.schemas import (
    ReembolsoAtualizacao,
    ReembolsoDetalhe,
    ReembolsoEntrada,
    ReembolsoSaida,
    reembolso_para_detalhe,
    reembolso_para_saida,
)

router = APIRouter(prefix="/reembolsos", tags=["Reembolsos"])


# ---------- Funções de apoio ----------
def _buscar(db: Session, reembolso_id: int) -> Reembolso:
    reembolso = db.get(Reembolso, reembolso_id)
    if reembolso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Solicitação não encontrada")
    return reembolso


def _pode_consultar(usuario: Usuario, reembolso: Reembolso) -> bool:
    if reembolso.solicitante_id == usuario.id:
        return True
    if usuario.perfil == Perfil.gestor:
        # RN03: só o departamento do gestor, e nunca o rascunho de outra pessoa
        return (
            reembolso.solicitante.departamento_id == usuario.departamento_id
            and reembolso.situacao != Situacao.rascunho
        )
    if usuario.perfil == Perfil.financeiro:
        # só o que já recebeu aprovação de um gestor
        return any(
            h.etapa == Etapa.gestor and h.decisao == Decisao.aprovada
            for h in reembolso.historico
        )
    return False


def _exigir_acesso(usuario: Usuario, reembolso: Reembolso) -> None:
    if not _pode_consultar(usuario, reembolso):  # RN02 e Cenário 01
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não tem permissão para acessar esta solicitação")


def _exigir_dono(usuario: Usuario, reembolso: Reembolso) -> None:
    if reembolso.solicitante_id != usuario.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Somente o solicitante pode realizar esta operação")


def _exigir_rascunho(reembolso: Reembolso, acao: str) -> None:
    if reembolso.situacao != Situacao.rascunho:  # RN07 e Cenário 06
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Somente solicitações em rascunho podem ser {acao}. Situação atual: {reembolso.situacao.value}",
        )


def _referencia_em_uso(db: Session, usuario_id: int, referencia: str, ignorar_id: int | None = None) -> bool:
    consulta = select(Reembolso.id).where(
        Reembolso.solicitante_id == usuario_id,
        Reembolso.comprovante_ref == referencia,
    )
    if ignorar_id is not None:
        consulta = consulta.where(Reembolso.id != ignorar_id)
    return db.scalar(consulta) is not None


def _aplicar_filtros(consulta, situacao: Situacao | None, categoria: Categoria | None):
    if situacao is not None:
        consulta = consulta.where(Reembolso.situacao == situacao)
    if categoria is not None:
        consulta = consulta.where(Reembolso.categoria == categoria)
    return consulta.order_by(Reembolso.id.desc())


def _salvar(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:  # última barreira: as regras também existem dentro do banco
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Os dados conflitam com as regras do sistema")


MSG_COMPROVANTE = "Você já registrou uma despesa com esta referência de comprovante"  # RN05


# ---------- Rotas ----------
@router.post("", response_model=ReembolsoSaida, status_code=status.HTTP_201_CREATED,
             summary="Registrar solicitação (nasce como rascunho)")
def criar(entrada: ReembolsoEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    if _referencia_em_uso(db, usuario.id, entrada.comprovante_ref):
        raise HTTPException(status.HTTP_409_CONFLICT, MSG_COMPROVANTE)

    reembolso = Reembolso(
        solicitante_id=usuario.id,  # sempre o usuário logado, nunca um valor enviado pelo cliente
        categoria=entrada.categoria,
        valor_centavos=int(entrada.valor * 100),
        data_despesa=entrada.data_despesa,
        justificativa=entrada.justificativa,
        comprovante_ref=entrada.comprovante_ref,
        situacao=Situacao.rascunho,
    )
    db.add(reembolso)
    _salvar(db)
    db.refresh(reembolso)
    return reembolso_para_saida(reembolso)


# As três listas abaixo precisam vir ANTES de "/{reembolso_id}",
# senão palavras como "minhas" seriam lidas como se fossem um id.
@router.get("/minhas", response_model=list[ReembolsoSaida], summary="Listar minhas solicitações")
def listar_minhas(
    situacao: Situacao | None = None,
    categoria: Categoria | None = None,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    consulta = select(Reembolso).where(Reembolso.solicitante_id == usuario.id)
    consulta = _aplicar_filtros(consulta, situacao, categoria)
    return [reembolso_para_saida(r) for r in db.scalars(consulta)]


@router.get("/departamento", response_model=list[ReembolsoSaida],
            summary="Gestor: solicitações do meu departamento")
def listar_do_departamento(
    departamento_id: int | None = None,
    situacao: Situacao | None = None,
    categoria: Categoria | None = None,
    gestor: Usuario = Depends(exigir_perfil(Perfil.gestor)),
    db: Session = Depends(get_db),
):
    # RN03 e Cenário 07: o gestor só enxerga o próprio departamento
    if departamento_id is not None and departamento_id != gestor.departamento_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você só pode consultar o seu próprio departamento")

    consulta = (
        select(Reembolso)
        .join(Usuario, Reembolso.solicitante_id == Usuario.id)
        .where(
            Usuario.departamento_id == gestor.departamento_id,
            Reembolso.situacao != Situacao.rascunho,  # rascunho é privado de quem escreveu
            Reembolso.solicitante_id != gestor.id,  # as próprias ficam em /minhas
        )
    )
    consulta = _aplicar_filtros(consulta, situacao, categoria)
    return [reembolso_para_saida(r) for r in db.scalars(consulta)]


@router.get("/financeiro", response_model=list[ReembolsoSaida],
            summary="Financeiro: solicitações encaminhadas pelos gestores")
def listar_para_financeiro(
    departamento_id: int | None = None,
    situacao: Situacao | None = None,
    categoria: Categoria | None = None,
    financeiro: Usuario = Depends(exigir_perfil(Perfil.financeiro)),
    db: Session = Depends(get_db),
):
    # só entra o que já recebeu aprovação de um gestor
    aprovada_pelo_gestor = (
        select(HistoricoAnalise.id)
        .where(
            HistoricoAnalise.reembolso_id == Reembolso.id,
            HistoricoAnalise.etapa == Etapa.gestor,
            HistoricoAnalise.decisao == Decisao.aprovada,
        )
        .exists()
    )
    consulta = (
        select(Reembolso)
        .join(Usuario, Reembolso.solicitante_id == Usuario.id)
        .where(aprovada_pelo_gestor, Reembolso.solicitante_id != financeiro.id)
    )
    if departamento_id is not None:
        consulta = consulta.where(Usuario.departamento_id == departamento_id)
    consulta = _aplicar_filtros(consulta, situacao, categoria)
    return [reembolso_para_saida(r) for r in db.scalars(consulta)]


@router.get("/{reembolso_id}", response_model=ReembolsoDetalhe,
            summary="Consultar uma solicitação (com histórico)")
def detalhar(reembolso_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    reembolso = _buscar(db, reembolso_id)
    _exigir_acesso(usuario, reembolso)
    return reembolso_para_detalhe(reembolso)


@router.patch("/{reembolso_id}", response_model=ReembolsoSaida,
              summary="Alterar solicitação (somente em rascunho)")
def atualizar(
    reembolso_id: int,
    entrada: ReembolsoAtualizacao,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    reembolso = _buscar(db, reembolso_id)
    _exigir_dono(usuario, reembolso)
    _exigir_rascunho(reembolso, "alteradas")

    dados = entrada.model_dump(exclude_unset=True, exclude_none=True)
    if not dados:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe ao menos um campo para alterar")

    if "comprovante_ref" in dados and _referencia_em_uso(db, usuario.id, dados["comprovante_ref"], reembolso.id):
        raise HTTPException(status.HTTP_409_CONFLICT, MSG_COMPROVANTE)

    if "valor" in dados:
        reembolso.valor_centavos = int(dados.pop("valor") * 100)
    for campo, valor in dados.items():
        setattr(reembolso, campo, valor)

    _salvar(db)
    db.refresh(reembolso)
    return reembolso_para_saida(reembolso)


@router.delete("/{reembolso_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Excluir solicitação (somente em rascunho)")
def excluir(reembolso_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    reembolso = _buscar(db, reembolso_id)
    _exigir_dono(usuario, reembolso)
    _exigir_rascunho(reembolso, "excluídas")
    db.delete(reembolso)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{reembolso_id}/enviar", response_model=ReembolsoSaida,
             summary="Enviar para análise do gestor")
def enviar(reembolso_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    reembolso = _buscar(db, reembolso_id)
    _exigir_dono(usuario, reembolso)
    _exigir_rascunho(reembolso, "enviadas para análise")
    reembolso.situacao = Situacao.aguardando_gestor
    db.commit()
    db.refresh(reembolso)
    return reembolso_para_saida(reembolso)