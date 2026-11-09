from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import exigir_perfil
from app.models import Decisao, Etapa, HistoricoAnalise, Perfil, Reembolso, Situacao, Usuario
from app.routers.reembolsos import _buscar
from app.schemas import DecisaoEntrada, PagamentoEntrada, ReembolsoDetalhe, reembolso_para_detalhe

router = APIRouter(prefix="/reembolsos", tags=["Análises e pagamento"])


def _registrar(
    db: Session,
    reembolso: Reembolso,
    responsavel: Usuario,
    etapa: Etapa,
    decisao: Decisao,
    nova_situacao: Situacao,
    observacao: str | None,
) -> ReembolsoDetalhe:
    """Grava a decisão no histórico e muda a situação na mesma operação (RN12)."""
    db.add(
        HistoricoAnalise(
            reembolso_id=reembolso.id,
            responsavel_id=responsavel.id,
            etapa=etapa,
            decisao=decisao,
            observacao=observacao,
        )
    )
    reembolso.situacao = nova_situacao
    db.commit()
    db.refresh(reembolso)
    return reembolso_para_detalhe(reembolso)


def _negar_propria_solicitacao(reembolso: Reembolso, usuario: Usuario) -> None:
    if reembolso.solicitante_id == usuario.id:  # RN09
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Você não pode analisar uma solicitação de sua própria autoria",
        )


@router.post("/{reembolso_id}/analise-gestor", response_model=ReembolsoDetalhe,
             summary="Gestor aprova ou recusa")
def analisar_como_gestor(
    reembolso_id: int,
    entrada: DecisaoEntrada,
    gestor: Usuario = Depends(exigir_perfil(Perfil.gestor)),
    db: Session = Depends(get_db),
):
    reembolso = _buscar(db, reembolso_id)

    if reembolso.solicitante.departamento_id != gestor.departamento_id:  # RN03
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não tem permissão para analisar esta solicitação")
    _negar_propria_solicitacao(reembolso, gestor)
    if reembolso.situacao != Situacao.aguardando_gestor:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta solicitação não está aguardando análise do gestor")

    nova = Situacao.aguardando_financeiro if entrada.decisao == "aprovada" else Situacao.recusada
    return _registrar(db, reembolso, gestor, Etapa.gestor, Decisao(entrada.decisao), nova, entrada.observacao)


@router.post("/{reembolso_id}/analise-financeiro", response_model=ReembolsoDetalhe,
             summary="Financeiro aprova ou recusa")
def analisar_como_financeiro(
    reembolso_id: int,
    entrada: DecisaoEntrada,
    financeiro: Usuario = Depends(exigir_perfil(Perfil.financeiro)),
    db: Session = Depends(get_db),
):
    reembolso = _buscar(db, reembolso_id)

    _negar_propria_solicitacao(reembolso, financeiro)
    if reembolso.situacao != Situacao.aguardando_financeiro:  # RN08 e Cenário 05
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta solicitação não está aguardando análise do financeiro")

    nova = Situacao.aprovada if entrada.decisao == "aprovada" else Situacao.recusada
    return _registrar(db, reembolso, financeiro, Etapa.financeiro, Decisao(entrada.decisao), nova, entrada.observacao)


@router.post("/{reembolso_id}/pagamento", response_model=ReembolsoDetalhe,
             summary="Financeiro registra o pagamento")
def registrar_pagamento(
    reembolso_id: int,
    entrada: PagamentoEntrada,
    financeiro: Usuario = Depends(exigir_perfil(Perfil.financeiro)),
    db: Session = Depends(get_db),
):
    reembolso = _buscar(db, reembolso_id)

    _negar_propria_solicitacao(reembolso, financeiro)
    if reembolso.situacao != Situacao.aprovada:  # RN10
        raise HTTPException(status.HTTP_409_CONFLICT, "Somente solicitações aprovadas pelo financeiro podem ser pagas")

    return _registrar(db, reembolso, financeiro, Etapa.pagamento, Decisao.paga, Situacao.paga, entrada.observacao)