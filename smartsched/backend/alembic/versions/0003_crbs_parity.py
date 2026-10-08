"""CRBS parity: roles/permissions, room groups/ACL/custom fields, booking calendar, bookings, outbox,
translations; users/rooms/programs gain the CRBS columns; seeds the CRBS permission catalogue and the default
roles (data.sql Administrator + Teacher, SmartSched Planner + Viewer) and links existing users to them.

Revision ID: 0003_crbs_parity
Revises: 0002_studio
Create Date: 2026-10-08 10:05:00

"""
from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0003_crbs_parity"
down_revision = "0002_studio"
branch_labels = None
depends_on = None

# Frozen copy of the catalogue at this revision (app/services/bookings_perms.py may grow later).
PERMISSIONS = [
    ("system.bypass_maintenance_mode", "Use bookings while maintenance mode is on"),
    ("system.export_bookings", "Export bookings to CSV"),
    ("system.view_all_sessions", "View past and future sessions, not only selectable ones"),
    ("setup.authentication", "Configure authentication (LDAP)"),
    ("setup.departments", "Manage departments"),
    ("setup.roles", "Manage roles and permissions"),
    ("setup.rooms", "Manage rooms, room groups and custom fields"),
    ("setup.rooms_acl", "Manage room access control"),
    ("setup.schedules", "Manage schedules and periods"),
    ("setup.sessions", "Manage sessions, holidays and timetable week dates"),
    ("setup.settings", "Manage organisation and general settings"),
    ("setup.timetable_weeks", "Manage timetable weeks"),
    ("setup.users", "Manage users"),
    ("room.view", "View rooms and their bookings"),
    ("book_single.create", "Create single bookings"),
    ("book_single.edit_other_booking", "Edit other users' single bookings"),
    ("book_single.cancel_other_booking", "Cancel other users' single bookings"),
    ("book_single.set_user", "Set the user of a single booking"),
    ("book_single.set_department", "Set the department of a single booking"),
    ("book_single.view_other_notes", "View notes of other users' single bookings"),
    ("book_single.view_other_users", "View the user of other users' single bookings"),
    ("book_recur.create", "Create recurring bookings"),
    ("book_recur.edit_other_booking", "Edit other users' recurring bookings"),
    ("book_recur.cancel_other_booking", "Cancel other users' recurring bookings"),
    ("book_recur.set_user", "Set the user of a recurring booking"),
    ("book_recur.set_department", "Set the department of a recurring booking"),
    ("book_recur.view_other_notes", "View notes of other users' recurring bookings"),
    ("book_recur.view_other_users", "View the user of other users' recurring bookings"),
    ("planning.view", "View planning data: terms, requests, runs, timetables"),
    ("planning.edit", "Import, edit requests and rules, generate and publish timetables"),
    ("planning.admin", "Planning administration: AI settings, built-in rules"),
]
_ALL = [p for p, _ in PERMISSIONS]
_BOOK = [p for p in _ALL if p.startswith(("book_single.", "book_recur."))]
ROLES = [
    ("ADMIN", "Administrator", "Administrator", _ALL),
    ("TEACHER", "Teacher", "Teacher", ["room.view", "book_single.create", "book_single.view_other_notes", "book_recur.view_other_notes"]),
    (
        "PLANNER",
        "Planner",
        "Planning office: imports, timetables and bookings",
        ["planning.view", "planning.edit", "system.view_all_sessions", "system.export_bookings", "system.bypass_maintenance_mode", "room.view"] + _BOOK,
    ),
    (
        "VIEWER",
        "Viewer",
        "Read-only access to plans and bookings",
        ["planning.view", "room.view"] + [p for p in _BOOK if p.endswith(("view_other_notes", "view_other_users"))],
    ),
]


def upgrade() -> None:
    op.create_table('booking_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('group', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('max_active_bookings', sa.Integer(), nullable=True),
    sa.Column('range_min', sa.Integer(), nullable=True),
    sa.Column('range_max', sa.Integer(), nullable=True),
    sa.Column('recur_max_instances', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code'),
    sa.UniqueConstraint('name')
    )
    op.create_table('room_acl',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('entity_type', sa.String(length=16), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('context_type', sa.String(length=16), nullable=False),
    sa.Column('context_id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('room_acl') as batch_op:
        batch_op.create_index('ix_room_acl_entity', ['entity_type', 'entity_id'], unique=False)

    op.create_table('room_custom_fields',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('pos', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('room_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('pos', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('timetable_weeks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=20), nullable=False),
    sa.Column('bgcol', sa.String(length=6), nullable=False),
    sa.Column('icon', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('translations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=32), nullable=False),
    sa.Column('set', sa.String(length=64), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('language', 'set', 'key', name='uq_translations_lang_set_key')
    )
    op.create_table('booking_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=30), nullable=False),
    sa.Column('time_start', sa.Time(), nullable=False),
    sa.Column('time_end', sa.Time(), nullable=False),
    sa.Column('bookable', sa.Boolean(), nullable=False),
    sa.Column('days', sa.JSON(), nullable=False),
    sa.Column('start_period', sa.Integer(), nullable=False),
    sa.Column('end_period', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['schedule_id'], ['booking_schedules.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('booking_periods') as batch_op:
        batch_op.create_index(batch_op.f('ix_booking_periods_schedule_id'), ['schedule_id'], unique=False)

    op.create_table('holidays',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('holidays') as batch_op:
        batch_op.create_index(batch_op.f('ix_holidays_term_id'), ['term_id'], unique=False)

    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_table('room_acl_permissions',
    sa.Column('acl_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['acl_id'], ['room_acl.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('acl_id', 'permission_id')
    )
    op.create_table('room_custom_field_options',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('field_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.String(length=64), nullable=False),
    sa.Column('pos', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['field_id'], ['room_custom_fields.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('room_custom_field_options') as batch_op:
        batch_op.create_index(batch_op.f('ix_room_custom_field_options_field_id'), ['field_id'], unique=False)

    op.create_table('term_booking_settings',
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('is_selectable', sa.Boolean(), nullable=False),
    sa.Column('default_schedule_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['default_schedule_id'], ['booking_schedules.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id')
    )
    op.create_table('term_dates',
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('timetable_week_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['timetable_week_id'], ['timetable_weeks.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('term_id', 'date')
    )
    with op.batch_alter_table('term_dates') as batch_op:
        batch_op.create_index(batch_op.f('ix_term_dates_timetable_week_id'), ['timetable_week_id'], unique=False)

    op.create_table('term_schedules',
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('room_group_id', sa.Integer(), nullable=False),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['room_group_id'], ['room_groups.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['schedule_id'], ['booking_schedules.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'room_group_id')
    )
    op.create_table('multi_bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('timetable_week_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['timetable_week_id'], ['timetable_weeks.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('multi_bookings') as batch_op:
        batch_op.create_index(batch_op.f('ix_multi_bookings_user_id'), ['user_id'], unique=False)

    op.create_table('notification_outbox',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('to_email', sa.String(length=255), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('booking_id', sa.Integer(), nullable=True),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notification_outbox') as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_outbox_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_notification_outbox_status'), ['status'], unique=False)

    op.create_table('password_reset_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('password_reset_tokens') as batch_op:
        batch_op.create_index(batch_op.f('ix_password_reset_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('user_constraints',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('max_active_bookings_type', sa.String(length=1), nullable=False),
    sa.Column('max_active_bookings_value', sa.Integer(), nullable=True),
    sa.Column('range_min_type', sa.String(length=1), nullable=False),
    sa.Column('range_min_value', sa.Integer(), nullable=True),
    sa.Column('range_max_type', sa.String(length=1), nullable=False),
    sa.Column('range_max_value', sa.Integer(), nullable=True),
    sa.Column('recur_max_instances_type', sa.String(length=1), nullable=False),
    sa.Column('recur_max_instances_value', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('booking_series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('period_id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('department_id', sa.Integer(), nullable=True),
    sa.Column('timetable_week_id', sa.Integer(), nullable=True),
    sa.Column('weekday', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.Column('cancel_reason', sa.Text(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.Column('cancelled_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['department_id'], ['programs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['period_id'], ['booking_periods.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['timetable_week_id'], ['timetable_weeks.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('booking_series') as batch_op:
        batch_op.create_index(batch_op.f('ix_booking_series_room_id'), ['room_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_booking_series_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_booking_series_term_id'), ['term_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_booking_series_user_id'), ['user_id'], unique=False)

    op.create_table('multi_booking_slots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mb_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('period_id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['mb_id'], ['multi_bookings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['period_id'], ['booking_periods.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('multi_booking_slots') as batch_op:
        batch_op.create_index(batch_op.f('ix_multi_booking_slots_mb_id'), ['mb_id'], unique=False)

    op.create_table('room_custom_field_values',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('field_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['field_id'], ['room_custom_fields.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'field_id', name='uq_room_field_value')
    )
    with op.batch_alter_table('room_custom_field_values') as batch_op:
        batch_op.create_index(batch_op.f('ix_room_custom_field_values_field_id'), ['field_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_room_custom_field_values_room_id'), ['room_id'], unique=False)

    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('series_id', sa.Integer(), nullable=True),
    sa.Column('term_id', sa.Integer(), nullable=False),
    sa.Column('period_id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('department_id', sa.Integer(), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('start_period', sa.Integer(), nullable=False),
    sa.Column('end_period', sa.Integer(), nullable=False),
    sa.Column('multi_booking_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.Column('cancel_reason', sa.Text(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.Column('cancelled_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['cancelled_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['department_id'], ['programs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['period_id'], ['booking_periods.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['series_id'], ['booking_series.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bookings') as batch_op:
        batch_op.create_index(batch_op.f('ix_bookings_date'), ['date'], unique=False)
        batch_op.create_index('ix_bookings_room_date', ['room_id', 'date'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_series_id'), ['series_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_term_id'), ['term_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_user_id'), ['user_id'], unique=False)

    op.create_table('booking_slots',
    sa.Column('booking_id', sa.Integer(), nullable=False),
    sa.Column('period', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('booking_id', 'period'),
    sa.UniqueConstraint('room_id', 'date', 'period', name='uq_booking_slots_room_date_period')
    )
    with op.batch_alter_table("programs") as batch_op:
        batch_op.add_column(sa.Column("description", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("icon", sa.String(length=255), nullable=True))

    with op.batch_alter_table("rooms") as batch_op:
        batch_op.add_column(sa.Column("room_group_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("location", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("icon", sa.String(length=255), nullable=True))
        batch_op.create_index("ix_rooms_room_group_id", ["room_group_id"], unique=False)
        batch_op.create_foreign_key("fk_rooms_room_group_id", "room_groups", ["room_group_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_rooms_owner_user_id", "users", ["owner_user_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("firstname", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("lastname", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("ext", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("role_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("force_password_reset", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("auth_source", sa.String(length=8), nullable=False, server_default="local"))
        batch_op.add_column(sa.Column("calendar_token", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("language", sa.String(length=32), nullable=True))
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=True)
        batch_op.create_index("ix_users_department_id", ["department_id"], unique=False)
        batch_op.create_index("ix_users_role_id", ["role_id"], unique=False)
        batch_op.create_index("ix_users_username", ["username"], unique=True)
        batch_op.create_unique_constraint("uq_users_calendar_token", ["calendar_token"])
        batch_op.create_foreign_key("fk_users_department_id", "programs", ["department_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_users_role_id", "roles", ["role_id"], ["id"], ondelete="SET NULL")

    _seed()


def _seed() -> None:
    """The only seed data: the permission catalogue and the default roles; existing users join the role
    named by their ``users.role`` code (ADMIN / PLANNER / VIEWER)."""
    conn = op.get_bind()
    perm_t = sa.table("permissions", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("group", sa.String), sa.column("description", sa.String))
    role_t = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("created_at", sa.DateTime),
    )
    rp_t = sa.table("role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer))
    op.bulk_insert(perm_t, [{"name": n, "group": n.split(".", 1)[0], "description": d} for n, d in PERMISSIONS])
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(role_t, [{"code": c, "name": n, "description": d, "created_at": now} for c, n, d, _ in ROLES])
    perm_ids = {r.name: r.id for r in conn.execute(sa.select(perm_t.c.id, perm_t.c.name))}
    role_ids = {r.code: r.id for r in conn.execute(sa.select(role_t.c.id, role_t.c.code))}
    op.bulk_insert(rp_t, [{"role_id": role_ids[c], "permission_id": perm_ids[p]} for c, _, _, ps in ROLES for p in ps])
    users_t = sa.table("users", sa.column("role", sa.String), sa.column("role_id", sa.Integer))
    for code, rid in role_ids.items():
        conn.execute(sa.update(users_t).where(users_t.c.role == code).values(role_id=rid))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("fk_users_role_id", type_="foreignkey")
        batch_op.drop_constraint("fk_users_department_id", type_="foreignkey")
        batch_op.drop_constraint("uq_users_calendar_token", type_="unique")
        batch_op.drop_index("ix_users_username")
        batch_op.drop_index("ix_users_role_id")
        batch_op.drop_index("ix_users_department_id")
        for col in (
            "language", "calendar_token", "auth_source", "force_password_reset", "last_login_at",
            "department_id", "role_id", "ext", "lastname", "firstname", "username",
        ):
            batch_op.drop_column(col)
        # users.email stays nullable: rows created after the upgrade may have no address
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_constraint("fk_rooms_owner_user_id", type_="foreignkey")
        batch_op.drop_constraint("fk_rooms_room_group_id", type_="foreignkey")
        batch_op.drop_index("ix_rooms_room_group_id")
        for col in ("icon", "location", "owner_user_id", "room_group_id"):
            batch_op.drop_column(col)
    with op.batch_alter_table("programs") as batch_op:
        batch_op.drop_column("icon")
        batch_op.drop_column("description")
    for table in (
        "booking_slots",
        "bookings",
        "room_custom_field_values",
        "multi_booking_slots",
        "booking_series",
        "user_constraints",
        "password_reset_tokens",
        "notification_outbox",
        "multi_bookings",
        "term_schedules",
        "term_dates",
        "term_booking_settings",
        "room_custom_field_options",
        "room_acl_permissions",
        "role_permissions",
        "holidays",
        "booking_periods",
        "translations",
        "timetable_weeks",
        "room_groups",
        "room_custom_fields",
        "room_acl",
        "roles",
        "permissions",
        "booking_schedules",
    ):
        op.drop_table(table)
