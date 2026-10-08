"""I/O schemas for the CRBS-parity routes: roles, constraints, departments, holidays, room admin, booking
admin (sessions, schedules, periods, timetable weeks), org settings."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.importers import normalize as n
from app.schemas.common import ORMModel

LimitInt = int | None


def _clean(v: str | None) -> str | None:
    return n.clean_text(v) if v is not None else None


def _required_clean(v: str) -> str:
    text = n.clean_text(v)
    if not text:
        raise ValueError("must not be empty")
    return text


# --- roles -----------------------------------------------------------------------------------------


class RoleIn(BaseModel):
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=255)
    max_active_bookings: LimitInt = Field(default=None, ge=0)
    range_min: LimitInt = Field(default=None, ge=0)
    range_max: LimitInt = Field(default=None, ge=0)
    recur_max_instances: LimitInt = Field(default=None, ge=0)
    permissions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    max_active_bookings: LimitInt = Field(default=None, ge=0)
    range_min: LimitInt = Field(default=None, ge=0)
    range_max: LimitInt = Field(default=None, ge=0)
    recur_max_instances: LimitInt = Field(default=None, ge=0)
    permissions: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _required_clean(v) if v is not None else None


class RoleOut(BaseModel):
    id: int
    code: str | None
    name: str
    description: str | None
    max_active_bookings: int | None
    range_min: int | None
    range_max: int | None
    recur_max_instances: int | None
    permissions: list[str]
    user_count: int = 0
    users: list[dict[str, Any]] | None = None


class ConstraintValue(BaseModel):
    type: Literal["R", "U", "X"] = "R"
    value: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _value(self) -> ConstraintValue:
        if self.type == "U" and self.value is None:
            raise ValueError("type U needs a value")
        if self.type != "U":
            self.value = None
        return self


class ConstraintsIO(BaseModel):
    max_active_bookings: ConstraintValue = Field(default_factory=ConstraintValue)
    range_min: ConstraintValue = Field(default_factory=ConstraintValue)
    range_max: ConstraintValue = Field(default_factory=ConstraintValue)
    recur_max_instances: ConstraintValue = Field(default_factory=ConstraintValue)


# --- departments, holidays -----------------------------------------------------------------------


class DepartmentIn(BaseModel):
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _required_clean(v) if v is not None else None


class DepartmentOut(ORMModel):
    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    faculty_id: int | None = None
    is_evening: bool = False
    user_count: int = 0


class HolidayIn(BaseModel):
    term_id: int
    name: str = Field(max_length=50)
    date_start: dt.date
    date_end: dt.date

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)

    @model_validator(mode="after")
    def _order(self) -> HolidayIn:
        if self.date_end < self.date_start:
            raise ValueError("date_end is before date_start")
        return self


class HolidayUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    date_start: dt.date | None = None
    date_end: dt.date | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:  # same normalisation as HolidayIn (NBSP, runs of spaces)
        return _required_clean(v) if v is not None else None


class HolidayOut(ORMModel):
    id: int
    term_id: int
    name: str
    date_start: dt.date
    date_end: dt.date


# --- room admin ----------------------------------------------------------------------------------


class RoomGroupIn(BaseModel):
    name: str = Field(max_length=32)
    description: str | None = None
    room_ids: list[int] | None = None

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)


class RoomGroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=32)
    description: str | None = None
    room_ids: list[int] | None = None


class RoomGroupOut(BaseModel):
    id: int
    name: str
    description: str | None
    pos: int
    room_count: int
    room_ids: list[int]


class OrderIn(BaseModel):
    ids: list[int]


class RoomBookingUpdate(BaseModel):
    room_group_id: int | None = None
    owner_user_id: int | None = None
    location: str | None = Field(default=None, max_length=64)
    icon: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=255)
    is_bookable: bool | None = None
    display_name: str | None = Field(default=None, max_length=64)


class RoomAdminOut(BaseModel):
    id: int
    code: str
    display_name: str
    capacity: int
    is_bookable: bool
    room_group_id: int | None
    room_group: str | None
    owner_user_id: int | None
    owner_name: str | None
    location: str | None
    icon: str | None
    notes: str | None
    photo_url: str | None
    pos: int
    fields: dict[str, Any] = Field(default_factory=dict)


class CustomFieldIn(BaseModel):
    name: str = Field(max_length=64)
    type: Literal["TEXT", "CHECKBOX", "SELECT"]
    options: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)

    @model_validator(mode="after")
    def _opts(self) -> CustomFieldIn:
        self.options = [o for o in (n.clean_text(x) for x in self.options) if o]
        if self.type == "SELECT" and not self.options:
            raise ValueError("a SELECT field needs options")
        return self


class CustomFieldOut(BaseModel):
    id: int
    name: str
    type: str
    options: list[dict[str, Any]]


class AclIn(BaseModel):
    entity_type: Literal["room", "room_group"]
    entity_id: int
    context_type: Literal["user", "role", "department"]
    context_id: int
    permissions: list[str]


class AclUpdate(BaseModel):
    permissions: list[str]


class AclOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    entity_label: str | None
    context_type: str
    context_id: int
    context_label: str | None
    permissions: list[str]


# --- booking admin -------------------------------------------------------------------------------


class SessionSettingsIn(BaseModel):
    is_selectable: bool | None = None
    default_schedule_id: int | None = None


class SessionOut(BaseModel):
    term_id: int
    code: str
    name: str
    kind: str
    date_start: dt.date | None
    date_end: dt.date | None
    is_current: bool
    is_selectable: bool
    default_schedule_id: int | None
    mapped_dates: int
    holidays: int


class TermScheduleIn(BaseModel):
    room_group_id: int
    schedule_id: int


class ScheduleIn(BaseModel):
    name: str = Field(max_length=32)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=32)
    description: str | None = None


class PeriodIn(BaseModel):
    name: str = Field(max_length=30)
    #: "09:20", "09.20" (dotted, as the planning office writes them) or "9:20"
    time_start: str
    time_end: str
    bookable: bool = True
    days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("days are ISO weekdays 1..7")
        return sorted(set(v))


class PeriodUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=30)
    time_start: str | None = None
    time_end: str | None = None
    bookable: bool | None = None
    days: list[int] | None = None


class PeriodOut(BaseModel):
    id: int
    schedule_id: int
    name: str
    time_start: str
    time_end: str
    bookable: bool
    days: list[int]
    start_period: int
    end_period: int


class ScheduleOut(BaseModel):
    id: int
    name: str
    description: str | None
    type: str
    periods: list[PeriodOut]


class TimetableWeekIn(BaseModel):
    name: str = Field(max_length=20)
    bgcol: str
    icon: str | None = None

    @field_validator("name")
    @classmethod
    def _req_name(cls, v: str) -> str:
        return _required_clean(v)

    @field_validator("bgcol")
    @classmethod
    def _col(cls, v: str) -> str:
        v = v.strip().lstrip("#").upper()
        if len(v) != 6 or any(c not in "0123456789ABCDEF" for c in v):
            raise ValueError("colour must be a 6-digit hex value such as 71AAE3")
        return v


class TimetableWeekUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=20)
    bgcol: str | None = None
    icon: str | None = None

    @field_validator("bgcol")
    @classmethod
    def _col(cls, v: str | None) -> str | None:
        return TimetableWeekIn._col(v) if v is not None else None


class TimetableWeekOut(BaseModel):
    id: int
    name: str
    bgcol: str
    fgcol: str
    icon: str | None


class DatesIn(BaseModel):
    #: {"2026-02-16": week_id | null}
    dates: dict[dt.date, int | None]


class ApplyWeekIn(BaseModel):
    timetable_week_id: int | None


# --- org -----------------------------------------------------------------------------------------


class OrgSettingsIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    displaytype: Literal["day", "room"] | None = None
    d_columns: Literal["periods", "rooms", "days"] | None = None
    timezone: str | None = None
    login_message_enabled: bool | None = None
    login_message_text: str | None = Field(default=None, max_length=1024)
    maintenance_mode: bool | None = None
    maintenance_mode_message: str | None = Field(default=None, max_length=1024)
    use_room_groups: bool | None = None
    pattern_long: str | None = None
    pattern_weekday: str | None = None
    pattern_time: str | None = None
    default_language: str | None = None
    languages: list[str] | None = None
    bookings_show_name: bool | None = None
    max_active_bookings: int | None = Field(default=None, ge=0)
    max_active_bookings_unlimited: bool | None = None
    #: CRBS hides rooms without a room group from the booking grid; True shows them in an ungrouped tab
    show_ungrouped_rooms: bool | None = None
    #: CRBS settings/General: highlight the mouse-focused grid slot
    grid_highlight: bool | None = None
    # deliberate-difference switches (app/services/bookings_settings.py BOOKINGS_SPECS explains each)
    enforce_max_active_on_create: bool | None = None
    recur_max_counts_replacements: bool | None = None
    maintenance_gates_lists: bool | None = None
    manual_current_term: bool | None = None
    export_ungrouped_rooms: bool | None = None
    recurring_department_needs_set_department: bool | None = None
    ignore_unauthorised_user_department: bool | None = None
    cancel_all_includes_past: bool | None = None
    term_date_change: Literal["cancel", "confirm"] | None = None

    @field_validator("website")
    @classmethod
    def _website(cls, v: str | None) -> str | None:
        """B8: only http(s) links (the login page renders it as a link: no ``javascript:`` / ``data:``)."""
        if v is None:
            return None
        text = n.clean_text(v) or ""
        if not text:
            return ""
        from urllib.parse import urlsplit

        parts = urlsplit(text)
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            raise ValueError("website must be an http:// or https:// address")
        return text

    @field_validator("languages")
    @classmethod
    def _languages(cls, v: list[str] | None) -> list[str] | None:
        """B8: a non-empty subset of the shipped languages (the frontend has message files for them): Turkish,
        English and the 12 other CRBS languages (P18-LANG); ``pt_BR`` / ``German`` are stored as ``pt-br`` / ``de``."""
        if v is None:
            return None
        from app.services.bookings_i18n import SHIPPED_LANGUAGES, normalize_language

        codes = [normalize_language(x) for x in v]
        out = list(dict.fromkeys(c for c in codes if c))
        if None in codes or not out:
            raise ValueError(f"languages must be chosen from {', '.join(SHIPPED_LANGUAGES)}")
        return out

    @field_validator("default_language")
    @classmethod
    def _default_language(cls, v: str | None) -> str | None:
        from app.services.bookings_i18n import SHIPPED_LANGUAGES, normalize_language

        if v is None:
            return None
        code = normalize_language(v)
        if code is None:
            raise ValueError(f"default_language must be one of {', '.join(SHIPPED_LANGUAGES)}")
        return code

    @model_validator(mode="after")
    def _cols(self) -> OrgSettingsIn:
        if self.displaytype and self.d_columns:
            ok = {"day": {"periods", "rooms"}, "room": {"periods", "days"}}[self.displaytype]
            if self.d_columns not in ok:
                raise ValueError(f"columns {self.d_columns!r} do not fit display type {self.displaytype!r}")
        from app.services.bookings_i18n import valid_pattern

        for kind in ("pattern_long", "pattern_weekday", "pattern_time"):
            value = getattr(self, kind)
            if value is not None and not valid_pattern(kind, value.strip()):
                raise ValueError(f"{kind} must be one of GET /org/date-patterns (or empty for the default)")
            if value is not None:
                setattr(self, kind, value.strip())
        return self


class LdapSettingsIn(BaseModel):
    enabled: bool | None = None
    create_users: bool | None = None
    server: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    version: int | None = Field(default=None, ge=2, le=3)
    use_tls: bool | None = None
    ignore_cert: bool | None = None
    bind_dn_format: str | None = Field(default=None, max_length=1024)
    base_dn: str | None = Field(default=None, max_length=1024)
    search_filter: str | None = Field(default=None, max_length=1024)
    attr_firstname: str | None = None
    attr_lastname: str | None = None
    attr_displayname: str | None = None
    attr_email: str | None = None
    default_role_id: int | None = None
    default_department_id: int | None = None


class LdapTestIn(BaseModel):
    username: str
    password: str
    settings: LdapSettingsIn | None = None


class SmtpSettingsIn(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] | None = None
    username: str | None = None
    password: str | None = None
    from_address: str | None = None
    from_name: str | None = None
    timeout_s: int | None = Field(default=None, ge=1, le=120)


class SmtpTestIn(BaseModel):
    to: str


class SetupIn(BaseModel):
    org_name: str = Field(max_length=255)
    timezone: str = "Europe/Istanbul"
    admin_email: str
    admin_username: str | None = None
    admin_password: str = Field(min_length=8, max_length=256)
    admin_displayname: str | None = None

    @field_validator("org_name")
    @classmethod
    def _req_org_name(cls, v: str) -> str:
        return _required_clean(v)


class TranslationIn(BaseModel):
    language: str = Field(max_length=32)
    set: str = Field(max_length=64)
    key: str = Field(max_length=255)
    text: str

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        """An override is for a shipped language (P18-LANG: the 14), stored under its code (``pt-br``)."""
        from app.services.bookings_i18n import SHIPPED_LANGUAGES, normalize_language

        code = normalize_language(v)
        if code is None:
            raise ValueError(f"language must be one of {', '.join(SHIPPED_LANGUAGES)}")
        return code


class TranslationOut(ORMModel):
    id: int
    language: str
    set: str
    key: str
    text: str


def to_clean(v: Any) -> Any:
    return _clean(v) if isinstance(v, str) else v
