"""PostgreSQL row-level security on the per-person tables (wave 3 W3-SEC; app/core/rls.py, docs/SECURITY.md §4)

* a ``NOLOGIN`` role ``smartsched_rls`` (no ``BYPASSRLS``) with DML rights on every table of the schema (today's
  and, through default privileges, the ones later migrations create; never ``TRUNCATE``). A request of a signed-in
  user runs its transactions as that role (``set_config('role', ...)``, transaction-local), so the policies apply
  even when the application logs in as the table owner or a superuser (the compose default);
* three helper functions on the request GUCs ``app.user_id`` / ``app.perms`` / ``app.system``;
* ``ENABLE ROW LEVEL SECURITY`` + one policy per table that mirrors the API rules: the owner, the administrators
  the API already lets in (DSR handling ``setup.users``, retention ``setup.settings``, ...) and, for the booking
  tables, every booking-module member (the grid shows everyone's bookings to ``room.view``). Not ``FORCE``: the
  owner's own sessions (migrations, workers, the CLI) are the system context.

SQLite (tests, dev): nothing to do, the upgrade and the downgrade are no-ops.

Revision ID: 0035_rls_policies
Revises: 0034_ai_usage
Create Date: 2026-10-17 20:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0035_rls_policies"
down_revision = "0034_ai_usage"
branch_labels = None
depends_on = None

ROLE = "smartsched_rls"

#: every permission that makes someone a member of the booking module (CRBS ``room.view`` shows all bookings;
#: approvers, planners and the retention / DSR administrators act on other people's bookings through the API)
BOOKING_MEMBERS = (
    "room.view",
    "planning.view",
    "planning.edit",
    "planning.admin",
    "approvals.decide",
    "audit.view",
    "bookings.skip_approval",
    "system.export_bookings",
    "setup.rooms",
    "setup.settings",
    "setup.users",
    "book_single.create",
    "book_single.request",
    "book_single.edit_other_booking",
    "book_single.cancel_other_booking",
    "book_single.set_user",
    "book_recur.create",
    "book_recur.request",
    "book_recur.edit_other_booking",
    "book_recur.cancel_other_booking",
    "book_recur.set_user",
)


def _any(*perms: str) -> str:
    return "smartsched_rls_any(ARRAY[" + ", ".join(f"'{p}'" for p in perms) + "]::text[])"


SYS = "smartsched_rls_system()"
UID = "smartsched_rls_uid()"

#: (table, policy name, command, USING expression); WITH CHECK = USING for ALL policies
POLICIES: tuple[tuple[str, str, str, str], ...] = (
    ("inapp_notifications", "rls_owner", "ALL", f"{SYS} OR user_id = {UID} OR {_any('setup.users', 'setup.settings')}"),
    ("consents", "rls_owner", "ALL", f"{SYS} OR user_id = {UID} OR {_any('setup.users')}"),
    # the AI redactor of any signed-in user's AI call must see who withdrew ``ai_personal`` (app/ai/personal.py)
    ("consents", "rls_ai_switch", "SELECT", f"{UID} IS NOT NULL AND purpose = 'ai_personal'"),
    ("dsr_requests", "rls_owner", "ALL", f"{SYS} OR user_id = {UID} OR {_any('setup.users')}"),
    ("calendar_feed_tokens", "rls_owner", "ALL", f"{SYS} OR user_id = {UID} OR {_any('setup.users')}"),
    ("ai_usage", "rls_owner", "ALL", f"{SYS} OR user_id = {UID} OR {_any('planning.admin', 'setup.settings')}"),
    (
        "constraints",
        "rls_teacher_wish",
        "ALL",
        f"{SYS} OR source IS DISTINCT FROM 'TEACHER' OR created_by = {UID} "
        f"OR {_any('planning.view', 'planning.edit', 'planning.admin', 'setup.users')}",
    ),
    ("bookings", "rls_member", "ALL", f"{SYS} OR user_id = {UID} OR {_any(*BOOKING_MEMBERS)}"),
    ("booking_series", "rls_member", "ALL", f"{SYS} OR user_id = {UID} OR {_any(*BOOKING_MEMBERS)}"),
    ("approval_requests", "rls_member", "ALL", f"{SYS} OR requested_by = {UID} OR {_any(*BOOKING_MEMBERS)}"),
)

FUNCTIONS = (
    """CREATE OR REPLACE FUNCTION smartsched_rls_system() RETURNS boolean LANGUAGE sql STABLE AS
    $$ SELECT coalesce(current_setting('app.system', true), '') = 'on' $$""",
    """CREATE OR REPLACE FUNCTION smartsched_rls_uid() RETURNS integer LANGUAGE sql STABLE AS
    $$ SELECT nullif(current_setting('app.user_id', true), '')::integer $$""",
    """CREATE OR REPLACE FUNCTION smartsched_rls_any(p text[]) RETURNS boolean LANGUAGE sql STABLE AS
    $$ SELECT string_to_array(nullif(current_setting('app.perms', true), ''), ',') && p $$""",
)

ROLE_SQL = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
        CREATE ROLE {ROLE} NOLOGIN NOBYPASSRLS;
    END IF;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE WARNING 'smartsched: cannot create role {ROLE}; RLS applies only to non-owner logins (docs/SECURITY.md)';
END $$;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}')
       AND NOT pg_has_role(current_user, '{ROLE}', 'MEMBER') THEN
        EXECUTE format('GRANT {ROLE} TO %I', current_user);
    END IF;
EXCEPTION WHEN insufficient_privilege OR invalid_grant_operation THEN
    RAISE WARNING 'smartsched: cannot grant {ROLE} to the migration role';
END $$;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO {ROLE}', current_schema());
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON ALL TABLES IN SCHEMA %I TO {ROLE}',
                       current_schema());
        EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO {ROLE}', current_schema());
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES '
                       'ON TABLES TO {ROLE}', current_schema());
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {ROLE}',
                       current_schema());
    END IF;
END $$;
"""

REVOKE_SQL = f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM {ROLE}', current_schema());
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM {ROLE}', current_schema());
        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM {ROLE}', current_schema());
        EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM {ROLE}', current_schema());
        EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM {ROLE}', current_schema());
    END IF;
END $$;
"""


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite: no row-level security; the API checks are the only ones (docs/SECURITY.md)
    for fn in FUNCTIONS:
        op.execute(fn)
    op.execute(ROLE_SQL)
    have = _tables()
    for table in sorted({t for t, *_ in POLICIES} & have):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for table, name, cmd, using in POLICIES:
        if table not in have:
            continue
        check = f" WITH CHECK ({using})" if cmd == "ALL" else ""
        op.execute(f"CREATE POLICY {name} ON {table} AS PERMISSIVE FOR {cmd} USING ({using}){check}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    have = _tables()
    for table, name, _cmd, _using in POLICIES:
        if table in have:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    for table in sorted({t for t, *_ in POLICIES} & have):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(REVOKE_SQL)  # the role itself is cluster-wide (other databases may use it): kept
    for fn in ("smartsched_rls_any(text[])", "smartsched_rls_uid()", "smartsched_rls_system()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
