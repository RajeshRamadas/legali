"""Versioned DDL shared by migration 0040 and metadata-created databases.

Keep v1 definitions unchanged after release; use a new version for later DDL.
Database owners can change schema. These guards protect data operations, not DDL.
"""
from sqlalchemy import text

MESSAGE = "Audit history is append-only. Append a new event instead."
PG_BODY = f"BEGIN RAISE EXCEPTION USING ERRCODE = '23000', MESSAGE = '{MESSAGE}'; END;"
PG_INSTALL = (
    f"CREATE FUNCTION homexo_audit_guard_v1() RETURNS trigger LANGUAGE plpgsql AS $guard${PG_BODY}$guard$",
    "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION homexo_audit_guard_v1()",
    "ALTER TABLE audit_logs ENABLE ALWAYS TRIGGER audit_logs_append_only",
)
PG_REMOVE = (
    "DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs",
    "DROP FUNCTION IF EXISTS homexo_audit_guard_v1()",
)
SQLITE_INSTALL = (
    f"CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END",
    f"CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit_logs BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END",
    # SQLite REPLACE can skip delete triggers when recursive_triggers is off.
    f"CREATE TRIGGER audit_logs_no_replace BEFORE INSERT ON audit_logs WHEN EXISTS (SELECT 1 FROM audit_logs WHERE id = NEW.id) BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END",
)
SQLITE_REMOVE = tuple(f"DROP TRIGGER IF EXISTS {name}" for name in
    ("audit_logs_no_replace", "audit_logs_no_delete", "audit_logs_no_update"))


def install(connection):
    dialect = connection.dialect.name
    if dialect not in ("postgresql", "sqlite"):
        raise RuntimeError("Audit protection supports PostgreSQL and SQLite only.")
    for statement in PG_INSTALL if dialect == "postgresql" else SQLITE_INSTALL:
        connection.execute(text(statement))


def remove(connection):
    for statement in PG_REMOVE if connection.dialect.name == "postgresql" else SQLITE_REMOVE:
        connection.execute(text(statement))


def after_create(table, connection, **kwargs):
    install(connection)


def before_drop(table, connection, **kwargs):
    remove(connection)


def protection(connection):
    """Read actual guard definitions; never attempt a destructive health probe."""
    dialect = connection.dialect.name
    if dialect == "postgresql":
        row = connection.execute(text("""SELECT t.tgenabled, t.tgtype, p.proname, p.prosrc,
            t.tgqual IS NULL AND t.tgnargs = 0 AND t.tgattr = ''::int2vector AS unconditional,
            p.pronamespace = c.relnamespace AS same_schema
            FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE t.tgrelid = to_regclass('audit_logs')
            AND t.tgname = 'audit_logs_append_only' AND NOT t.tgisinternal""")).mappings().first()
        configured = bool(row and row["tgenabled"] == "A" and row["tgtype"] == 58 and row["same_schema"] and row["unconditional"]
            and row["proname"] == "homexo_audit_guard_v1" and row["prosrc"].strip() == PG_BODY)
    elif dialect == "sqlite":
        rows = connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'audit_logs'")).all()
        definitions = {name: " ".join(sql.strip().rstrip(';').split()) for name, sql in rows}
        configured = all(definitions.get(statement.split()[2]) == " ".join(statement.split()) for statement in SQLITE_INSTALL)
    else:
        return {"state": "unsupported"}
    return {"state": "configured" if configured else "missing"}
