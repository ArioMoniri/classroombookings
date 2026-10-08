"""Booking enhancements wave 1, P10 typed room features (docs/product/booking-enhancements.md §4.1):
``room_custom_fields`` gain filterable / public / icon / unit / solver_tag / category, values gain value_num
(NUMBER, indexed with the field) and value_json (MULTISELECT); the permission ``rooms.features``.

Data migration: the free-text room tags (``rooms.tags``: PC, TIP, LAB, AMPHI ...) become yes/no features with
that ``solver_tag`` (the feature reads the tag, so nothing is copied and the solver keeps its vocabulary);
existing CRBS CHECKBOX / SELECT / TEXT fields and values stay as they are (CHECKBOX = BOOLEAN).

Revision ID: 0012_room_features
Revises: 0011_integrations
Create Date: 2026-10-08 16:30:00

"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0012_room_features"
down_revision = "0011_integrations"
branch_labels = None
depends_on = None

PERMISSIONS = [("rooms.features", "Manage the room feature catalogue and the rooms' feature values")]
TAG_LABELS = {
    "PC": ("Bilgisayar laboratuvarı", "lab"),
    "TIP": ("Tıp Fakültesi dersliği", "other"),
    "LAB": ("Laboratuvar", "lab"),
    "AMPHI": ("Amfi", "seating"),
    "AMFI": ("Amfi", "seating"),
}


def grant(perms: list[tuple[str, str]]) -> None:
    """Add permissions to the catalogue; the Administrator role holds every permission."""
    conn = op.get_bind()
    have = {r[0] for r in conn.execute(sa.text("select name from permissions"))}
    for name, desc in perms:
        if name not in have:
            conn.execute(
                sa.text('insert into permissions (name, "group", description) values (:n, :g, :d)'),
                {"n": name, "g": name.split(".", 1)[0], "d": desc},
            )
    admin = conn.execute(sa.text("select id from roles where code = 'ADMIN'")).scalar()
    if admin is None:
        return
    for name, _ in perms:
        pid = conn.execute(sa.text("select id from permissions where name = :n"), {"n": name}).scalar()
        exists = conn.execute(
            sa.text("select 1 from role_permissions where role_id = :r and permission_id = :p"), {"r": admin, "p": pid}
        ).first()
        if exists is None:
            conn.execute(
                sa.text("insert into role_permissions (role_id, permission_id) values (:r, :p)"), {"r": admin, "p": pid}
            )


def revoke(perms: list[tuple[str, str]]) -> None:
    conn = op.get_bind()
    for name, _ in perms:
        pid = conn.execute(sa.text("select id from permissions where name = :n"), {"n": name}).scalar()
        if pid is None:
            continue
        conn.execute(sa.text("delete from role_permissions where permission_id = :p"), {"p": pid})
        conn.execute(sa.text("delete from room_acl_permissions where permission_id = :p"), {"p": pid})
        conn.execute(sa.text("delete from permissions where id = :p"), {"p": pid})


def upgrade() -> None:
    with op.batch_alter_table("room_custom_fields") as batch:
        batch.add_column(sa.Column("filterable", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("icon", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("unit", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("solver_tag", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("category", sa.String(length=32), nullable=True))
    with op.batch_alter_table("room_custom_field_values") as batch:
        batch.add_column(sa.Column("value_num", sa.Float(), nullable=True))
        batch.add_column(sa.Column("value_json", sa.JSON(), nullable=True))
        batch.create_index("ix_room_field_values_field_num", ["field_id", "value_num"])
    grant(PERMISSIONS)
    # adopt the room tags as typed yes/no features (one per tag no field maps yet)
    conn = op.get_bind()
    tags: list[str] = []
    for (raw,) in conn.execute(sa.text("select tags from rooms")):
        try:
            values = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except ValueError:
            values = []
        for t in values or []:
            tag = str(t).strip().upper().replace(" ", "_")[:16]
            if tag and tag not in tags:
                tags.append(tag)
    existing = {
        str(r[1]).casefold(): (r[0], r[2])
        for r in conn.execute(sa.text("select id, name, type from room_custom_fields"))
    }
    pos = conn.execute(sa.text("select coalesce(max(pos), 0) from room_custom_fields")).scalar() or 0
    for tag in sorted(tags):
        label, category = TAG_LABELS.get(tag, (tag, "other"))
        same = existing.get(label.casefold())
        if same is not None and same[1] in ("CHECKBOX", "BOOLEAN"):  # e.g. upgraded again after a downgrade
            conn.execute(
                sa.text("update room_custom_fields set type = 'BOOLEAN', solver_tag = :s, category = :c where id = :i"),
                {"s": tag, "c": category, "i": same[0]},
            )
            continue
        name = label if same is None else f"{label} ({tag})"
        pos += 1
        conn.execute(
            sa.text(
                "insert into room_custom_fields (name, type, pos, filterable, public, solver_tag, category) "
                "values (:n, 'BOOLEAN', :p, :t, :t, :s, :c)"
            ),
            {"n": name[:64], "p": pos, "t": True, "s": tag, "c": category},
        )


def downgrade() -> None:
    conn = op.get_bind()
    # typed values that CRBS cannot show go with the columns; BOOLEAN reverts to CRBS CHECKBOX
    conn.execute(sa.text("update room_custom_fields set type = 'CHECKBOX' where type = 'BOOLEAN'"))
    conn.execute(sa.text("update room_custom_fields set type = 'TEXT' where type = 'NUMBER'"))
    conn.execute(
        sa.text(
            "delete from room_custom_field_values where field_id in (select id from room_custom_fields where type = 'MULTISELECT')"
        )
    )
    conn.execute(sa.text("update room_custom_fields set type = 'SELECT' where type = 'MULTISELECT'"))
    revoke(PERMISSIONS)
    with op.batch_alter_table("room_custom_field_values") as batch:
        batch.drop_index("ix_room_field_values_field_num")
        batch.drop_column("value_json")
        batch.drop_column("value_num")
    with op.batch_alter_table("room_custom_fields") as batch:
        for col in ("category", "solver_tag", "unit", "icon", "public", "filterable"):
            batch.drop_column(col)
