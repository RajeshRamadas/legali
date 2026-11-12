"""Verified customers manage only their own revocable sign-ins."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from .customer_auth import aware, current_customer, MAX_ACTIVE_SESSIONS
from .db import get_db
from .models import AuditLog, CustomerAccount, CustomerSession, utcnow

router=APIRouter(prefix="/api/v1/account")


def lock_account(db,account):
    return db.scalar(select(CustomerAccount).where(CustomerAccount.id==account.id).with_for_update().execution_options(populate_existing=True))


@router.get("/sessions")
def sessions(account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    now=utcnow();current=account._authenticated_session_id
    rows=db.scalars(select(CustomerSession).where(CustomerSession.account_id==account.id,CustomerSession.token_version==account.token_version,
        CustomerSession.revoked_at.is_(None),CustomerSession.expires_at>now).order_by(CustomerSession.created_at.desc(),CustomerSession.id.desc()).limit(MAX_ACTIVE_SESSIONS)).all()
    return {"items":[{"id":str(row.id),"browser":row.browser,"device":row.device,"created_at":aware(row.created_at).isoformat(),
        "last_seen_at":aware(row.last_seen_at).isoformat(),"expires_at":aware(row.expires_at).isoformat(),"is_current":row.id==current} for row in rows],
        "checked_at":now.isoformat(),"max_active":MAX_ACTIVE_SESSIONS,"activity_interval_seconds":300}


def end_session(db,account,key):
    current=account._authenticated_session_id
    lock_account(db,account)
    row=db.scalar(select(CustomerSession).where(CustomerSession.account_id==account.id,CustomerSession.id==key))
    if row is None:raise HTTPException(404,"Sign-in session not found.")
    if row.revoked_at is None:
        row.revoked_at=utcnow();row.revoke_reason="customer"
        db.add(AuditLog(action="customer.session_revoked",entity_type="customer_account",entity_id=account.id,
            metadata_={"session_id":str(key),"current":key==current}))
        db.commit()
    return {"revoked":True,"current":key==current}


@router.post("/sessions/{session_id}/revoke")
def revoke(session_id:uuid.UUID,account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    return end_session(db,account,session_id)


@router.post("/logout")
def logout(account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    return end_session(db,account,account._authenticated_session_id)


@router.post("/sessions/revoke-others")
def revoke_others(account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    current=account._authenticated_session_id;lock_account(db,account)
    result=db.execute(update(CustomerSession).where(CustomerSession.account_id==account.id,CustomerSession.id!=current,
        CustomerSession.token_version==account.token_version,CustomerSession.revoked_at.is_(None),CustomerSession.expires_at>utcnow())
        .values(revoked_at=utcnow(),revoke_reason="other_sessions").execution_options(synchronize_session=False))
    if result.rowcount:
        db.add(AuditLog(action="customer.other_sessions_revoked",entity_type="customer_account",entity_id=account.id,metadata_={"count":result.rowcount}))
    db.commit()
    return {"revoked":result.rowcount}
