"""Application-level holds on case file deletion/replacement; never a purge tool."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import object_session

from .db import get_db
from .models import AuditLog, CaseDocumentHold as Hold, ServiceRequest, User, utcnow
from .security import current_staff, require_admin

router=APIRouter(prefix="/api/v1/admin")
REASONS={"privacy_review":"Privacy review","legal_obligation":"Legal obligation review","manual_review":"Manual records review"}
ACTIONS=("document_preservation.held","document_preservation.released")
MESSAGE="These case files are on a preservation hold. An administrator must review and release it before file deletion or replacement."


class Decision(BaseModel):
    model_config=ConfigDict(extra="forbid")
    held: bool=Field(strict=True)
    revision: int=Field(ge=0,le=2147483646,strict=True)
    reason: Literal["privacy_review","legal_obligation","manual_review"]
    note: str=Field(min_length=20,max_length=2000)

    @field_validator("note")
    @classmethod
    def plain_note(cls,value):
        value=value.strip()
        if len(value)<20 or any(ord(char)<32 and char not in "\n\t" or ord(char)==127 for char in value):
            raise ValueError("Explain the records review using at least 20 plain-text characters.")
        return value


def stamp(value):
    from .tickets import aware
    return aware(value).isoformat() if value else None


def cached_held(db,case_id):
    cache=db.info.setdefault("document_preservation_views",{})
    if case_id not in cache:cache[case_id]=bool(db.scalar(select(Hold.held).where(Hold.service_request_id==case_id)))
    return cache[case_id]


def held_for(record):
    db=object_session(record)
    if db is None:return False
    case_id=record.id if isinstance(record,ServiceRequest) else record.service_request_id
    return cached_held(db,case_id)


def ensure_removable(db,case_id):
    # Hold writers and all file removals serialize on this case row. The lock
    # remains until the caller commits/rolls back, including object deletion.
    key=db.scalar(select(ServiceRequest.id).where(ServiceRequest.id==case_id).with_for_update())
    if key is None:raise HTTPException(404,"Case not found.")
    if db.scalar(select(Hold.held).where(Hold.service_request_id==case_id)):raise HTTPException(409,MESSAGE)


def detail(db,case_id,admin):
    columns=(Hold.held,Hold.revision,Hold.changed_at)
    row=db.execute(select(*columns).where(Hold.service_request_id==case_id)).first()
    result={"held":bool(row and row.held),"revision":row.revision if row else 0,"changed_at":stamp(row.changed_at) if row else None,"can_manage":admin}
    if admin:
        private=db.get(Hold,case_id)
        result.update(reason=private.reason if private else None,note=private.note if private else "")
        rows=db.execute(select(AuditLog.id,AuditLog.action,AuditLog.created_at,AuditLog.metadata_,User.display_name)
            .outerjoin(User,User.id==AuditLog.actor_user_id).where(AuditLog.entity_type=="service_request",AuditLog.entity_id==case_id,AuditLog.action.in_(ACTIONS))
            .order_by(AuditLog.created_at.desc(),AuditLog.id.desc()).limit(10)).all()
        result["history"]=[{"id":str(item.id),"held":item.action==ACTIONS[0],"at":stamp(item.created_at),"actor":item.display_name or "Former staff or system",
            "reason":item.metadata_.get("reason") if item.metadata_.get("reason") in REASONS else None,
            "note":item.metadata_.get("note") if isinstance(item.metadata_.get("note"),str) else ""} for item in rows]
    return result


@router.get("/tickets/{ticket_number}/document-hold")
def read(ticket_number:str,user:User=Depends(current_staff),db=Depends(get_db)):
    from .admin import _get_ticket
    return detail(db,_get_ticket(db,user,ticket_number).id,user.is_admin)


@router.put("/tickets/{ticket_number}/document-hold")
def change(ticket_number:str,payload:Decision,user:User=Depends(require_admin),db=Depends(get_db)):
    from .admin import _get_ticket
    case=_get_ticket(db,user,ticket_number,lock=True)
    row=db.get(Hold,case.id)
    if (row.revision if row else 0)!=payload.revision:raise HTTPException(409,"The preservation decision changed. Refresh and review it before saving again.")
    if row and row.held==payload.held:raise HTTPException(409,"The case already has this preservation state. Refresh before recording another decision.")
    if row is None:
        if not payload.held:raise HTTPException(409,"There is no active hold to release.")
        row=Hold(service_request_id=case.id,revision=0);db.add(row)
    row.held=payload.held;row.revision+=1;row.reason=payload.reason;row.note=payload.note;row.changed_by_user_id=user.id;row.changed_at=utcnow()
    db.add(AuditLog(actor_user_id=user.id,action=ACTIONS[0] if payload.held else ACTIONS[1],entity_type="service_request",entity_id=case.id,
        metadata_={"revision":row.revision,"reason":row.reason,"note":row.note}))
    db.commit();db.info.get("document_preservation_views",{}).pop(case.id,None)
    return detail(db,case.id,True)


@router.get("/document-holds")
def queue(status:Literal["active","released","all"]="active",reason:Literal["all","privacy_review","legal_obligation","manual_review"]="all",
    q:str=Query("",max_length=40,pattern=r"^[^\x00-\x1f\x7f]*$"),page:int=Query(1,ge=1,le=10000),_:User=Depends(require_admin),db=Depends(get_db)):
    query=select(Hold.service_request_id,Hold.held,Hold.reason,Hold.revision,Hold.changed_at,ServiceRequest.ticket_number).join(ServiceRequest,ServiceRequest.id==Hold.service_request_id)
    if status!="all":query=query.where(Hold.held.is_(status=="active"))
    if reason!="all":query=query.where(Hold.reason==reason)
    if q.strip():
        escaped=q.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        query=query.where(ServiceRequest.ticket_number.ilike(f"%{escaped}%",escape="\\"))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.execute(query.order_by(Hold.changed_at.desc(),Hold.service_request_id.desc()).offset((page-1)*25).limit(25)).all()
    return {"items":[{"ticket_number":row.ticket_number,"held":row.held,"reason":row.reason,"revision":row.revision,"changed_at":stamp(row.changed_at)} for row in rows],
        "total":total,"active_count":db.scalar(select(func.count()).select_from(Hold).where(Hold.held.is_(True))),"page":page,"page_size":25,"checked_at":utcnow().isoformat()}
