"""Seed only an empty, explicitly reserved PostgreSQL performance database."""
import argparse
import base64
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import sys
import uuid

from sqlalchemy import create_engine, func, inspect, select, table, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ('WHATSAPP_ACCESS_TOKEN', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'ANTHROPIC_API_KEY', 'VERIFICATION_LLM_API_KEY',
    'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', 'RAZORPAY_WEBHOOK_SECRET', 'RESEND_API_KEY', 'TWILIO_AUTH_TOKEN',
    'S3_BUCKET', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY', 'BOOTSTRAP_ADMIN_EMAIL', 'BOOTSTRAP_ADMIN_PASSWORD')
WORKERS = ('NOTIFY_WORKER_ENABLED', 'BLOG_AGENT_ENABLED', 'CHAT_RETENTION_ENABLED', 'RERA_SAMPLE_WHEN_EMPTY')


def validate_environment(env):
    url = make_url(env.get('DATABASE_URL', ''))
    if env.get('APP_ENV') != 'performance' or url.get_backend_name() != 'postgresql' or not re.fullmatch(r'legali_perf_[a-z0-9_]{1,40}', url.database or ''):
        raise ValueError('Use APP_ENV=performance and a dedicated legali_perf_* PostgreSQL database.')
    if any(env.get(name) != 'false' for name in WORKERS) or any(env.get(name) for name in PROVIDERS):
        raise ValueError('Performance fixtures require disabled workers and no provider/bootstrap configuration.')
    if len(env.get('JWT_SECRET', '')) < 32 or not env.get('STAFF_MFA_ENCRYPTION_KEY'):
        raise ValueError('Performance fixtures require temporary JWT/MFA keys.')
    return url


def ensure_empty(db, tables):
    for table in tables:
        if table.name not in ('roles', 'service_types') and db.scalar(select(func.count()).select_from(table)):
            raise ValueError('Refusing to seed a database containing business data. Create a fresh performance database.')


def assert_target_empty(database_url):
    engine = create_engine(make_url(database_url).set(drivername='postgresql+psycopg'), connect_args={'connect_timeout': 3})
    try:
        with engine.connect() as connection:
            for name in inspect(connection).get_table_names():
                if name not in ('alembic_version', 'roles', 'service_types') and connection.scalar(select(1).select_from(table(name)).limit(1)):
                    raise ValueError('Refusing a performance database containing data before migrations.')
    finally:
        engine.dispose()


def seed(destination, tickets_count=200, customer_count=20):
    validate_environment(os.environ)
    if destination.exists():
        raise ValueError('Choose a new private identity file.')
    if not 20 <= tickets_count <= 2000 or not 2 <= customer_count <= 100 or tickets_count < customer_count:
        raise ValueError('Invalid bounded fixture sizes.')
    sys.path.insert(0, str(ROOT / 'backend'))
    from cryptography.fernet import Fernet
    from app import config, tickets
    from app.bootstrap import sync_reference_data
    from app.customer_auth import create_session_token
    from app.db import engine
    from app.models import Base, CustomerAccount, LawyerProfile, ReraProject, Role, ServiceType, SupportMessage, SupportRequest, User, utcnow
    from app.operations import expected_revisions
    from app.security import create_access_token
    with engine.begin() as connection:
        with Session(bind=connection, join_transaction_mode='rollback_only', expire_on_commit=False) as db:
            db.execute(text('SELECT pg_advisory_xact_lock(946207321)'))
            if set(db.scalars(text('SELECT version_num FROM alembic_version'))) != expected_revisions():
                raise ValueError('Apply migrations before seeding performance fixtures.')
            ensure_empty(db, Base.metadata.sorted_tables)
            sync_reference_data(db)
            admin_role = db.scalar(select(Role).where(Role.name == 'admin'))
            agent_role = db.scalar(select(Role).where(Role.name == 'agent'))
            secret = base64.b32encode(os.urandom(20))
            admin = User(display_name='Synthetic Performance Administrator', email='admin@performance.invalid', roles=[admin_role],
                mfa_secret=Fernet(config.STAFF_MFA_ENCRYPTION_KEY.encode()).encrypt(secret).decode())
            db.add(admin)
            accounts = [CustomerAccount(phone_normalized=f'{index:010d}', full_name=f'Synthetic Customer {index}') for index in range(customer_count)]
            db.add_all(accounts); db.flush()
            service = db.scalar(select(ServiceType).where(ServiceType.slug == 'general-guidance'))
            for index in range(tickets_count):
                account = accounts[index % customer_count]
                case = tickets.create_ticket(db, customer_name=account.full_name, phone=account.phone_normalized, email=None, property_type='apartment',
                    service=service, package=None, location='Synthetic locality', description='Performance fixture only.', source='website')
                issue = SupportRequest(account_id=account.id, service_request_id=case.id, submission_key=uuid.uuid4(), kind='case_update',
                    subject=f'Synthetic support {index}', details='Synthetic performance support request.', reply_due_at=utcnow() + timedelta(hours=72))
                db.add(issue); db.flush()
                db.add(SupportMessage(support_request_id=issue.id, submission_key=uuid.uuid4(), author_type='staff', author_user_id=admin.id,
                    visibility='internal', body='Synthetic private note; never part of customer results.'))
            for index in range(8):
                lawyer = User(display_name=f'Synthetic Advocate {index}', email=f'lawyer{index}@performance.invalid', roles=[agent_role])
                db.add(lawyer); db.flush()
                db.add(LawyerProfile(user_id=lawyer.id, slug=f'performance-lawyer-{index}', headline='Synthetic property consultation',
                    specialisations=['Property & real estate'], languages=['English'], experience_years=10, consultation_fee=500, is_listed=True,
                    weekly_hours={day: [['10:00', '18:00']] for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')}))
            for index in range(40):
                db.add(ReraProject(registration_no=f'PERF-{index}', slug=f'performance-project-{index}', name=f'Synthetic Project {index}',
                    promoter_name='Synthetic Promoter', promoter_slug='synthetic-promoter', district='Bengaluru', locality='Synthetic locality',
                    locality_slug='synthetic-locality', total_units=100, booked_units=30, is_sample=True))
            db.flush()
            identity = {'customer': create_session_token(accounts[0], db=db), 'admin': create_access_token(admin, mfa=True),
                'counts': {'customers': customer_count, 'cases': tickets_count, 'support_requests': tickets_count, 'lawyers': 8, 'projects': 40}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting another run's identity file; mode is private from creation.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(identity, output)
    print('Created synthetic performance fixtures; private identities written without logging credentials.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tickets', type=int, default=200)
    parser.add_argument('--customers', type=int, default=20)
    args = parser.parse_args()
    try:
        seed(args.output, args.tickets, args.customers)
    except Exception:
        print('Performance fixture seeding failed. Check isolation, empty database and migrations; no credentials are logged.', file=sys.stderr)
        sys.exit(1)
