"""Vertical Chain API router — Step 6.

Chains are computed on-the-fly from element_identity + level_identity.
No materialised storage; manual identity overrides take immediate effect.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Project
from app.schemas.chain import BuildChainsResult, ChainDetail, ChainSummary
from app.services import chain_service as svc

router = APIRouter(tags=["chains"])


def _verify_project_exists(db: Session, number: str) -> None:
    """Raise 404 if no dbo.Project rows exist for this project number."""
    exists = db.query(Project).filter(Project.Number == number).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Project '{number}' not found")


@router.post(
    "/projects/{number}/chains/build",
    response_model=BuildChainsResult,
    summary="Build vertical chains from identity hub",
)
def build_chains(number: str, db: Session = Depends(get_db)):
    _verify_project_exists(db, number)
    return svc.build_chains(db, number)


@router.get(
    "/projects/{number}/chains",
    response_model=list[ChainSummary],
    summary="List all vertical chains for a project",
)
def list_chains(number: str, db: Session = Depends(get_db)):
    _verify_project_exists(db, number)
    return svc.get_chains(db, number)


@router.get(
    "/projects/{number}/chains/{element_identity_id}",
    response_model=ChainDetail,
    summary="Get full chain detail for one element",
)
def get_chain_detail(
    number: str,
    element_identity_id: int,
    db: Session = Depends(get_db),
):
    _verify_project_exists(db, number)
    detail = svc.get_chain_detail(db, number, element_identity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Element not found or has no level assignment")
    return detail