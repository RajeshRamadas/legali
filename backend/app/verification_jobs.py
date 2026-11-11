"""Durable verification work. No HTTP request or database lock spans analysis."""
import argparse
import time
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import select, update

from . import config, property_law, tickets, verification, verification_usage, ai_processing
from .admin import _get_ticket
from .db import SessionLocal, engine, get_db
from .models import AuditLog, CLOSED_STATUSES, ServiceRequest, User, VerificationJob, VerificationRun, utcnow
from .security import current_staff
from .telemetry import WorkerConfigurationError, observe_worker
from .tickets import aware

router=APIRouter(prefix="/api/v1/admin/tickets")
LEASE_SECONDS=900
REASONS={"interrupted":"Worker interrupted. Review before starting a fresh analysis.",
    "access_changed":"The requester's case access changed. Analysis was stopped.",
    "evidence_changed":"Case evidence or intake changed. Review and submit a fresh analysis.",
    "configuration_changed":"Processing settings changed. Review the current settings and submit again.",
    "analysis_failed":"Analysis did not complete. No new result was accepted; review before retrying.",
    "consent_changed":"Customer AI permission changed or needs review. No new result was accepted; review the current choice before retrying.",
    "cancelled":"Cancelled. Any provider request already in progress cannot be recalled."}


class Submission(verification.RunRequest):
    use_llm: bool=Field(default=False,strict=True)
    consent_to_external_processing: bool=Field(default=False,strict=True)
    submission_key: uuid.UUID
    configuration_revision: str=Field(default="",max_length=64)

    @field_validator("state")
    @classmethod
    def plain_state(cls,value):
        value=value.strip()
        if len(value)<2 or any(ord(char)<32 or ord(char)==127 for char in value):
            raise ValueError("Choose a plain-text state or union territory.")
        return value


class StopWork(Exception):
    def __init__(self,reason,status="failed"):
        self.reason,self.status=reason,status


def configuration(use_llm):
    value={"law_version":property_law.LAW_VERSION,"ocr":config.VERIFICATION_OCR_LANGUAGES}
    if use_llm:
        value.update(provider=config.VERIFICATION_LLM_PROVIDER,base=config.VERIFICATION_LLM_BASE_URL,
            extract=verification.model_for("extract"),compare=verification.model_for("compare"),images=config.VERIFICATION_SEND_PAGE_IMAGES)
    return verification.fingerprint(value)


def input_revision(ticket,prepared):
    return verification.fingerprint({"scope":prepared["scope"],"files":prepared["documents"],"status":ticket.status,
        "report_status":ticket.report.status if ticket.report else None})


def audit(db,job,action,actor=None):
    db.add(AuditLog(actor_user_id=actor.id if actor else None,action=action,entity_type="service_request",
        entity_id=job.service_request_id,metadata_={"job_id":str(job.id),"use_llm":job.request["use_llm"]}))


def finish(job,status,reason=None):
    job.status=status;job.reason_code=reason;job.phase="finished";job.finished_at=utcnow();job.claim_token=None;job.lease_until=None


def expired(job):
    return job.status=="running" and (not job.lease_until or aware(job.lease_until)<=utcnow())


def recover(db,case_id=None):
    query=select(VerificationJob).where(VerificationJob.status=="running",(VerificationJob.lease_until.is_(None))|(VerificationJob.lease_until<=utcnow()))
    if case_id:query=query.where(VerificationJob.service_request_id==case_id)
    for job in db.scalars(query.with_for_update(skip_locked=True)):
        finish(job,"failed","interrupted");audit(db,job,"verification.job_interrupted")
    db.flush()


def view(job,user,usage=None):
    interrupted=expired(job)
    return {"id":str(job.id),"status":"interrupted" if interrupted else job.status,"phase":job.phase,
        "created_at":aware(job.created_at).isoformat(),"started_at":aware(job.started_at).isoformat() if job.started_at else None,
        "finished_at":aware(job.finished_at).isoformat() if job.finished_at else None,
        "state":job.request["state"],"use_llm":job.request["use_llm"],"run_id":str(job.run_id) if job.run_id else None,
        "message":REASONS.get("interrupted" if interrupted else job.reason_code),
        "usage":usage if usage is not None else verification_usage.summary(),
        "can_cancel":job.status in ("queued","running") and (user.is_admin or user.id==job.requested_by_user_id)}


@router.post("/{ticket_number}/verification/jobs",status_code=202)
def submit(ticket_number:str,payload:Submission,user:User=Depends(current_staff),db=Depends(get_db)):
    ticket=_get_ticket(db,user,ticket_number,lock=True)
    request=payload.model_dump(mode="json",exclude={"submission_key","configuration_revision"})
    previous=db.scalar(select(VerificationJob).where(VerificationJob.service_request_id==ticket.id,VerificationJob.submission_key==payload.submission_key))
    if previous:
        if previous.request!=request or previous.requested_by_user_id!=user.id:
            raise HTTPException(409,"This submission reference was already used with different settings.")
        return view(previous,user,verification_usage.summaries(db,[previous.id]).get(previous.id))
    if ticket.status in CLOSED_STATUSES:raise HTTPException(409,"Reopen this case before requesting analysis.")
    prepared=verification.prepare(ticket,verification.RunRequest.model_validate(request))
    revision=configuration(payload.use_llm)
    if payload.use_llm and payload.configuration_revision!=revision:
        raise HTTPException(409,"Processing settings changed. Reload the case and review consent again.")
    recover(db,ticket.id)
    if db.scalar(select(VerificationJob.id).where(VerificationJob.service_request_id==ticket.id,VerificationJob.status.in_(("queued","running"))).limit(1)):
        raise HTTPException(409,"Background analysis is already active. Refresh its status before submitting again.")
    since=utcnow()-timedelta(seconds=60)
    if db.scalar(select(VerificationRun.id).where(VerificationRun.service_request_id==ticket.id,VerificationRun.created_at>since).limit(1)) or db.scalar(
        select(VerificationJob.id).where(VerificationJob.service_request_id==ticket.id,VerificationJob.created_at>since).limit(1)):
        raise HTTPException(429,"Wait one minute between new analysis requests for this case.")
    job=VerificationJob(service_request_id=ticket.id,requested_by_user_id=user.id,submission_key=payload.submission_key,
        request=request,input_fingerprint=input_revision(ticket,prepared),configuration_revision=revision,
        consent_revision=prepared["ai_approval"]["revision"] if prepared.get("ai_approval") else None)
    db.add(job);db.flush();audit(db,job,"verification.job_queued",user);db.commit()
    return view(job,user)


@router.get("/{ticket_number}/verification/jobs")
def history(ticket_number:str,page:int=Query(1,ge=1,le=10000),user:User=Depends(current_staff),db=Depends(get_db)):
    ticket=_get_ticket(db,user,ticket_number)
    rows=db.scalars(select(VerificationJob).where(VerificationJob.service_request_id==ticket.id)
        .order_by(VerificationJob.created_at.desc(),VerificationJob.id.desc()).offset((page-1)*20).limit(20)).all()
    usage=verification_usage.summaries(db,[job.id for job in rows])
    return {"items":[view(job,user,usage.get(job.id)) for job in rows],"page":page,"page_size":20}


def find(db,ticket,job_id):
    job=db.scalar(select(VerificationJob).where(VerificationJob.id==job_id,VerificationJob.service_request_id==ticket.id).with_for_update())
    if not job:raise HTTPException(404,"Analysis job not found.")
    return job


@router.post("/{ticket_number}/verification/jobs/{job_id}/cancel")
def cancel(ticket_number:str,job_id:uuid.UUID,user:User=Depends(current_staff),db=Depends(get_db)):
    ticket=_get_ticket(db,user,ticket_number,lock=True);job=find(db,ticket,job_id)
    if job.requested_by_user_id!=user.id and not user.is_admin:raise HTTPException(403,"Only the requester or an administrator can cancel this analysis.")
    if job.status in ("queued","running"):
        finish(job,"cancelled","cancelled");audit(db,job,"verification.job_cancelled",user);db.commit()
    return view(job,user,verification_usage.summaries(db,[job.id]).get(job.id))


def owned(job,token):
    if not job or job.status!="running" or job.claim_token!=token or expired(job):raise StopWork("interrupted")


def inputs(db,job):
    user=db.get(User,job.requested_by_user_id) if job.requested_by_user_id else None
    if not user or user.account_status!="active" or not user.role_names.intersection(("admin","super_admin","agent")):
        raise StopWork("access_changed","cancelled")
    number=db.scalar(select(ServiceRequest.ticket_number).where(ServiceRequest.id==job.service_request_id))
    if not number:raise StopWork("evidence_changed","stale")
    try:ticket=_get_ticket(db,user,number)
    except HTTPException:raise StopWork("access_changed","cancelled")
    request=verification.RunRequest.model_validate(job.request)
    if job.configuration_revision!=configuration(request.use_llm):raise StopWork("configuration_changed")
    if request.use_llm and not verification.provider_status()["configured"]:raise StopWork("configuration_changed")
    try:prepared=verification.prepare(ticket,request)
    except ai_processing.ApprovalRequired:raise StopWork("consent_changed","cancelled")
    except HTTPException:raise StopWork("evidence_changed","stale")
    if request.use_llm and prepared["ai_approval"]["revision"]!=job.consent_revision:raise StopWork("consent_changed","cancelled")
    if ticket.status in CLOSED_STATUSES or input_revision(ticket,prepared)!=job.input_fingerprint:
        raise StopWork("evidence_changed","stale")
    return prepared,request


def checkpoint(job_id,token,phase):
    with SessionLocal() as db:
        job=db.get(VerificationJob,job_id);owned(job,token);inputs(db,job)
        changed=db.execute(update(VerificationJob).where(VerificationJob.id==job_id,VerificationJob.status=="running",
            VerificationJob.claim_token==token,VerificationJob.lease_until>utcnow())
            .values(phase=phase,lease_until=utcnow()+timedelta(seconds=LEASE_SECONDS)).execution_options(synchronize_session=False))
        if changed.rowcount!=1:raise StopWork("interrupted")
        db.commit()


def claim():
    with SessionLocal() as db:
        recover(db)
        job=db.scalar(select(VerificationJob).where(VerificationJob.status=="queued")
            .order_by(VerificationJob.created_at,VerificationJob.id).with_for_update(skip_locked=True).limit(1))
        if not job:db.commit();return None
        token=uuid.uuid4();job.status="running";job.claim_token=token;job.started_at=utcnow();job.lease_until=utcnow()+timedelta(seconds=LEASE_SECONDS)
        audit(db,job,"verification.job_started");key=job.id;db.commit();return key,token


def process_one():
    selected=claim()
    if not selected:return False
    key,token=selected;result=None;failure=None
    try:
        with SessionLocal() as db:
            job=db.get(VerificationJob,key);owned(job,token);prepared,request=inputs(db,job);usage_case_id=job.service_request_id
        with verification_usage.scope(usage_case_id,key):
            result=verification.run_prepared(prepared,request,lambda phase:checkpoint(key,token,phase))
        if request.use_llm and result["llm_status"]!="completed":raise StopWork("analysis_failed")
    except ai_processing.ApprovalRequired:failure=StopWork("consent_changed","cancelled")
    except StopWork as error:failure=error
    except Exception:failure=StopWork("analysis_failed")
    with SessionLocal() as db:
        # Case, then job: the same lock order as submission/cancellation.
        case_id=db.scalar(select(VerificationJob.service_request_id).where(VerificationJob.id==key))
        if not case_id:return True
        db.execute(select(ServiceRequest.id).where(ServiceRequest.id==case_id).with_for_update())
        job=db.scalar(select(VerificationJob).where(VerificationJob.id==key).with_for_update())
        try:owned(job,token)
        except StopWork:return True
        if not failure:
            try:
                if job.request["use_llm"]:ai_processing.approved(db,case_id,job.consent_revision,lock=True)
                inputs(db,job)
            except ai_processing.ApprovalRequired:failure=StopWork("consent_changed","cancelled")
            except StopWork as error:failure=error
        if failure:finish(job,failure.status,failure.reason)
        else:
            run=VerificationRun(service_request_id=case_id,created_by_user_id=job.requested_by_user_id,result=result)
            db.add(run);db.flush();job.run_id=run.id;finish(job,"completed")
        audit(db,job,"verification.job_"+job.status);db.commit()
    return True


@observe_worker("verification")
def tick():
    from .audit_guard_v1 import protection
    from .operations import schema_matches
    with engine.connect() as connection:
        if not schema_matches(connection) or protection(connection)["state"]!="configured":
            raise WorkerConfigurationError("Apply current migrations and restore audit guards before processing jobs.")
    return process_one()


def main():
    parser=argparse.ArgumentParser(description="Run durable verification jobs using the API's database, provider and storage configuration.")
    parser.add_argument("--loop",action="store_true",help="Continue polling; without this flag process at most one job.")
    args=parser.parse_args()
    if engine.dialect.name!="postgresql":parser.error("The verification worker requires PostgreSQL.")
    while True:
        tick()
        if not args.loop:return
        time.sleep(10)


if __name__=="__main__":main()
