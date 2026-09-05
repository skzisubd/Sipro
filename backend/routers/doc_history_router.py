"""Riwayat dokumen terbit per lead/customer (Fase 91)."""
from fastapi import APIRouter, Depends, HTTPException

import doc_history
from db import ORG_ID
from rbac import require_permission

router = APIRouter(prefix="/doc-history", tags=["doc-history"])


@router.get("/{entity_type}/{entity_id}")
async def issued_documents(entity_type: str, entity_id: str,
                           user: dict = Depends(require_permission("documents", "view"))):
    if entity_type not in ("lead", "customer"):
        raise HTTPException(status_code=400, detail="entity_type harus lead atau customer.")
    return {"data": await doc_history.history(user.get("org_id", ORG_ID), entity_type, entity_id)}
