import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select
from app import config
from app.db import SessionLocal, engine
from app.models import AuditLog, SupportMessage, SupportRequest, utcnow
from conftest import authenticate_customer

BASE = '/api/v1/account/support-requests'
ADMIN = '/api/v1/admin/support-requests'


def payload(**changes):
    return {'kind':'complaint','subject':'A case service issue','details':'Please help resolve the delay with my case.','submission_key':str(uuid.uuid4()),**changes}


def create(client, **changes):
    result=client.post(BASE,json=payload(**changes))
    assert result.status_code == 201, result.text
    return result.json()


def review(client, headers, item, **changes):
    return client.patch(f"{ADMIN}/{item['id']}",headers=headers,json={'revision':item['revision'],'status':'in_progress',**changes})


def reply(client, item, **changes):
    return client.post(f"{BASE}/{item['id']}/messages",json={'body':'Please also check this additional detail.','submission_key':str(uuid.uuid4()),**changes})


def test_customer_and_admin_boundaries(client, admin_headers, agent):
    assert client.get(BASE).status_code == client.post(BASE,json=payload()).status_code == 401
    assert client.get(BASE,headers=admin_headers).status_code == 401
    assert client.get(ADMIN).status_code == 401
    assert client.get(ADMIN,headers=agent['headers']).status_code == 403
    authenticate_customer(client)
    item=create(client)
    assert client.get(ADMIN).status_code == 401
    assert item['reference'].startswith('SR-') and item['revision']==1
    assert client.get(BASE).headers['cache-control']=='private, no-store'
    for suffix in ('','/messages'):
        assert client.get(f"{ADMIN}/{item['id']}{suffix}",headers=agent['headers']).status_code == 403
    assert review(client,agent['headers'],item).status_code == 403


def test_owner_isolation_and_case_link(client, raise_ticket, admin_headers):
    ticket=raise_ticket(); owner=dict(client.headers)
    item=create(client,ticket_number=ticket.lower())
    authenticate_customer(client,'9123456789')
    assert client.get(BASE).json()['items']==[]
    assert client.post(BASE,json=payload(ticket_number=ticket)).status_code == 404
    for suffix in ('','/messages'):
        assert client.get(f"{BASE}/{item['id']}{suffix}").status_code == 404
    assert reply(client,item).status_code == 404
    assert client.get(f"{BASE}/{item['id']}",headers=owner).json()['ticket_number']==ticket
    assert client.get(f"{ADMIN}/{item['id']}",headers=admin_headers).status_code == 200


def test_retries_are_exactly_once_and_conflicting_payloads_rejected(client):
    authenticate_customer(client); data=payload()
    item=client.post(BASE,json=data).json()
    assert client.post(BASE,json=data).status_code == 200
    assert client.post(BASE,json={**data,'subject':'Different issue'}).status_code == 409
    message={'body':'One additional detail','submission_key':str(uuid.uuid4())}
    assert reply(client,item,**message).status_code == 201
    assert reply(client,item,**message).status_code == 200
    assert reply(client,item,**{**message,'body':'Changed message'}).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SupportRequest))==1
        assert db.scalar(select(func.count()).select_from(SupportMessage))==1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_type=='support_request'))==2


def test_customer_thread_excludes_internal_notes_and_actor_details(client, admin_headers):
    authenticate_customer(client); item=create(client)
    result=review(client,admin_headers,item,status='waiting_for_customer',customer_response='Please confirm which document is affected.',internal_note='PRIVATE_INTERNAL_NOTE')
    assert result.status_code == 200,result.text
    customer=client.get(f"{BASE}/{item['id']}/messages").json()
    assert customer['total']==1 and 'PRIVATE_INTERNAL_NOTE' not in str(customer)
    assert all('author_user_id' not in row and 'submission_key' not in row for row in customer['items'])
    staff=client.get(f"{ADMIN}/{item['id']}/messages",headers=admin_headers).json()
    assert staff['total']==2 and any(row['visibility']=='internal' for row in staff['items'])
    for path in (BASE,f"{BASE}/{item['id']}"):
        assert 'PRIVATE_INTERNAL_NOTE' not in client.get(path).text
    with SessionLocal() as db:
        assert 'PRIVATE_INTERNAL_NOTE' not in str([r.metadata_ for r in db.scalars(select(AuditLog).where(AuditLog.entity_type=='support_request'))])


def test_resolution_validation_stale_updates_and_reopening(client, admin_headers):
    authenticate_customer(client); item=create(client)
    assert review(client,admin_headers,item,status='resolved',internal_note='Not a customer response').status_code == 422
    updated=reply(client,item).json()
    assert review(client,admin_headers,item,status='resolved',customer_response='We completed the agreed action.').status_code == 409
    resolved=review(client,admin_headers,updated,status='resolved',customer_response='We completed the agreed action.').json()
    assert resolved['status']=='resolved' and resolved['reply_due_at'] is None
    reopened=reply(client,item).json()
    assert reopened['status']=='open' and reopened['resolved_at'] is None and reopened['revision']==4 and reopened['reply_due_at']


def test_open_and_reply_caps_and_replays(client, admin_headers, monkeypatch):
    monkeypatch.setattr(config,'SUPPORT_OPEN_LIMIT',1); monkeypatch.setattr(config,'SUPPORT_MESSAGES_PER_DAY',1)
    authenticate_customer(client); item=create(client)
    blocked=client.post(BASE,json=payload())
    assert blocked.status_code == 429 and int(blocked.headers['retry-after'])>0
    assert review(client,admin_headers,item,status='resolved',customer_response='We completed the agreed action.').status_code == 200
    second=create(client)
    assert reply(client,item).status_code == 429
    data={'body':'Additional detail','submission_key':str(uuid.uuid4())}
    assert reply(client,second,**data).status_code == 201
    assert reply(client,second,**data).status_code == 200
    assert reply(client,second).status_code == 429


def test_daily_creation_cap_survives_resolution(client, admin_headers, monkeypatch):
    monkeypatch.setattr(config,'SUPPORT_REQUESTS_PER_DAY',1)
    authenticate_customer(client); item=create(client)
    assert review(client,admin_headers,item,status='resolved',customer_response='We completed the agreed action.').status_code == 200
    blocked=client.post(BASE,json=payload())
    assert blocked.status_code == 429 and 1 <= int(blocked.headers['retry-after']) <= 86400


@pytest.mark.parametrize('changes',[{'subject':'     '},{'details':'    '},{'kind':'invalid'},{'details':'bad\x00text here'},{'subject':'x'*161}])
def test_invalid_input_is_rejected(client,changes):
    authenticate_customer(client)
    assert client.post(BASE,json=payload(**changes)).status_code == 422


def test_queue_filters_pagination_and_response_target(client, admin_headers):
    authenticate_customer(client)
    item=create(client,subject='Escalated document problem',kind='documents'); create(client,subject='Another question',kind='other')
    with SessionLocal() as db:
        db.get(SupportRequest,uuid.UUID(item['id'])).reply_due_at=utcnow()-timedelta(hours=1); db.commit()
    queue=client.get(ADMIN+'?kind=documents&q=document&page_size=1',headers=admin_headers).json()
    assert queue['total']==queue['overdue']==1 and queue['items'][0]['id']==item['id']
    assert client.get(ADMIN+'?q='+item['reference'],headers=admin_headers).json()['total']==1
    assert client.get(ADMIN,params={'q':'invalid\x00search'},headers=admin_headers).status_code == 422
    updated=reply(client,item).json(); assert updated['overdue']
    updated=review(client,admin_headers,updated,internal_note='Started checking.').json(); assert updated['overdue']
    updated=review(client,admin_headers,updated,customer_response='We are checking this and will follow up.').json()
    assert not updated['overdue'] and updated['reply_due_at'] is None
    assert client.get(BASE+'?page=0').status_code == 422
    assert client.get(BASE+'?page_size=100').status_code == 422


@pytest.mark.skipif(engine.dialect.name!='postgresql',reason='Requires PostgreSQL account row locks')
@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_creation_is_serialized(client,monkeypatch,same_key):
    monkeypatch.setattr(config,'SUPPORT_OPEN_LIMIT',1)
    authenticate_customer(client); data=payload(); barrier=Barrier(2)
    def send(_):
        barrier.wait(timeout=10)
        return client.post(BASE,json=data if same_key else payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(send,range(2)))
    assert sorted(row.status_code for row in result)==([200,201] if same_key else [201,429])


def test_thread_pagination_hides_notes_before_counting_and_slicing(client,admin_headers):
    authenticate_customer(client); item=create(client)
    for number in range(3):
        item=review(client,admin_headers,item,customer_response=f'Public response {number}',internal_note=f'PRIVATE {number}').json()
    first=client.get(f"{BASE}/{item['id']}/messages?page_size=2").json()
    second=client.get(f"{BASE}/{item['id']}/messages?page_size=2&page=2").json()
    assert first['total']==second['total']==3 and len(first['items'])==2 and len(second['items'])==1
    assert not set(row['id'] for row in first['items']) & set(row['id'] for row in second['items'])
    assert 'PRIVATE' not in str(first)+str(second)
    assert client.get(f"{ADMIN}/{item['id']}/messages",headers=admin_headers).json()['total']==6


@pytest.mark.skipif(engine.dialect.name!='postgresql',reason='Requires PostgreSQL account and request row locks')
def test_reply_racing_resolution_keeps_customer_followup_open(client,admin_headers):
    authenticate_customer(client); item=create(client); barrier=Barrier(2)
    def action(which):
        barrier.wait(timeout=10)
        return reply(client,item) if which else review(client,admin_headers,item,status='resolved',customer_response='We completed the agreed action.')
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(action,[False,True]))
    assert result[1].status_code==201 and result[0].status_code in (200,409)
    final=client.get(f"{BASE}/{item['id']}").json()
    assert final['status']=='open' and final['resolved_at'] is None


def test_support_routes_share_write_and_lookup_budgets():
    from app.abuse_protection import policy_for
    for path in (BASE,BASE+'/id/messages',ADMIN+'/id'):
        assert policy_for('GET',path).group=='lookups'
    assert policy_for('POST',BASE).group=='customer_writes'
    assert policy_for('POST',BASE+'/id/messages').group=='customer_writes'
    assert policy_for('PATCH',ADMIN+'/id').group=='customer_writes'


def test_queue_metadata_queries_do_not_grow_per_row(client,admin_headers,raise_ticket):
    from sqlalchemy import event
    from app.models import CustomerAccount, ServiceRequest
    ticket_number=raise_ticket()
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==ticket_number))
        account=db.scalar(select(CustomerAccount).where(CustomerAccount.phone_normalized=='9876543210'))
        for index in range(20):
            db.add(SupportRequest(account_id=account.id,service_request_id=ticket.id,submission_key=uuid.uuid4(),kind='case_update',subject=f'Batch fixture {index}',details='Synthetic query-count regression fixture.'))
        db.commit()
    selects=[]
    def capture(connection,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'): selects.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:
        first=client.get(ADMIN+'?page_size=1',headers=admin_headers)
        assert first.status_code==200
        small=len(selects); selects.clear()
        result=client.get(ADMIN+'?page_size=20',headers=admin_headers)
        assert result.status_code==200 and len(result.json()['items'])==20
        assert len(selects) <= small+2
        assert all(row['ticket_number']==ticket_number and row['customer']['phone_last4']=='3210' for row in result.json()['items'])
    finally: event.remove(engine,'before_cursor_execute',capture)
