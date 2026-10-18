"""Card contract ``helper.card.v1`` (HB-07), the wire format between the helper backend and the HX renderer.

Aligned with docs/design/v3/helper.md §4.2 (wire types → presentations), §4.3 (catalogue) and §17 (asks A1, A2, A7,
A8) and with the architecture doc §5.3. Rules:

* **Server-built only.** :mod:`app.ai.helper.cards` builds every card from an index entry or an action result. The
  model never emits a card; its own words only ever appear in an ``answer`` card.
* **No URL, no HTML, no Markdown link anywhere.** Every string field is a :data:`Plain` (``<`` / ``>``, ``://``,
  ``www.``, ``javascript:`` and ``data:`` are refused; the JSON Schema carries the same pattern for the client).
  Navigation is a ``feature_id`` that the client maps to its own route (``components/helper/feature-links.ts``).
* **Turkish first, English always:** person-facing text is a :class:`Txt` ``{tr, en}``; the client shows its locale.
* The client chooses the presentation from ``type`` + ``action``; an unknown ``type`` renders as ``answer`` + ``nav``.

``GET /helper/schema`` publishes :func:`card_json_schema` (a snapshot test guards it on both sides).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter

from app.ai.sanitize import strip_controls

CARD_VERSION: Literal[1] = 1
SCHEMA_ID = "helper.card.v1"

_FORBIDDEN = re.compile(r"[<>]|://|\bwww\.|javascript:|data:", re.IGNORECASE)
#: the same rule for JSON Schema consumers (ECMA regex; pydantic checks it with :func:`_plain`)
PLAIN_PATTERN = r"^(?![\s\S]*(?:://|[wW][wW][wW]\.|[jJ]avascript:|[dD]ata:))[^<>]*$"


def _plain(v: str) -> str:
    if _FORBIDDEN.search(v):
        raise ValueError("cards carry no URL, HTML or markup")
    return v


LINK_MARK = "[bağlantı]"
_LINKISH = re.compile(r"(?:https?|ftp)://\S*|\bwww\.\S*|javascript:|data:", re.IGNORECASE)


def scrub(text: object, limit: int = 400) -> str:
    """Database or model text made safe for a card: no control characters, no angle brackets, no links; trimmed.
    (:func:`app.ai.helper.cards.clean` is this function.)"""
    t = strip_controls(str(text if text is not None else ""))
    t = _LINKISH.sub(LINK_MARK, t).replace("<", "‹").replace(">", "›")
    t = " ".join(t.split())
    return t if len(t) <= limit else t[: limit - 1] + "…"


def _scrub_str(v: Any) -> Any:
    return scrub(v) if isinstance(v, str) else v


def _plain_field(max_length: int) -> Any:
    return Field(max_length=max_length, json_schema_extra={"pattern": PLAIN_PATTERN})


Plain = Annotated[str, AfterValidator(_plain), _plain_field(400)]
LongPlain = Annotated[str, AfterValidator(_plain), _plain_field(1200)]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$", max_length=64)]
Token = Annotated[str, Field(pattern=r"^[A-Za-z0-9_\-.]+$", max_length=600)]
#: an argument value echoed on a card (prefill): text is neutralised, never refused, so a model-written note with a
#: link can never turn a card into a 500
SafeStr = Annotated[str, BeforeValidator(_scrub_str), AfterValidator(_plain), _plain_field(400)]
Scalar = SafeStr | int | float | bool | None
#: an option's value: an id or a code the server made (``17``, ``room_unavailable``)
OptionValue = Annotated[str, Field(pattern=r"^[A-Za-z0-9_\-:.]{1,64}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Txt(_Strict):
    """One person-facing text in both languages (Turkish first)."""

    tr: Plain
    en: Plain


class Texts(_Strict):
    tr: list[Plain] = Field(default_factory=list, max_length=8)
    en: list[Plain] = Field(default_factory=list, max_length=8)


class CardBase(_Strict):
    v: Literal[1] = CARD_VERSION
    #: server id (correlation for refresh, feedback and telemetry)
    id: Annotated[str, Field(pattern=r"^[a-f0-9]{8,32}$")]
    #: the registry action the card belongs to (``None`` for index-only cards)
    action: Name | None = None
    title: Txt | None = None


# ------------------------------------------------------------------------------------------------ R0


class AnswerCard(CardBase):
    """The model's text (plain, cleaned by the output guard), or an index sentence (``source: index``)."""

    type: Literal["answer"] = "answer"
    text: LongPlain
    lang: Literal["tr", "en"]
    source: Literal["ai", "index"]
    #: the person's own helper notes this answer drew on, shown as "Notunuza göre: {not}" (helper.md §5.1); absent
    #: when none (the server matches the note's words in the answer; the model's claim is never trusted)
    notes_used: list[Plain] | None = Field(default=None, max_length=2)


class NavCard(CardBase):
    """ "Nerede?": a feature-index entry. The client resolves ``feature_id`` → href; the server sends no URL."""

    type: Literal["nav"] = "nav"
    feature_id: Name
    kind: Literal["page", "tab", "setting", "control"]
    path: Texts
    steps: Texts = Field(default_factory=Texts)
    #: ``data-tour`` id for "Göster" (absent: only "Sayfayı aç")
    anchor: Annotated[str, Field(pattern=r"^[a-z][a-z0-9\-]*$", max_length=64)] | None = None
    #: actions the person may run from here ("Burada yap"), already filtered by permission
    actions: list[Name] = Field(default_factory=list, max_length=4)


class Column(_Strict):
    key: Name
    label: Txt
    kind: Literal["text", "date", "time", "room", "person", "status", "number"]


class RowAction(_Strict):
    """A per-row button: asks ``POST /helper/actions/{action}/card`` with ``args`` (no model call)."""

    action: Name
    label: Txt
    args: dict[Name, Scalar] = Field(default_factory=dict)
    danger: bool = False


class Row(_Strict):
    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_\-:]{1,64}$")]
    cells: dict[Name, Plain | Txt]
    actions: list[RowAction] = Field(default_factory=list, max_length=3)


class ListCard(CardBase):
    """≤ 5 rows by default (helper.md A8; the wire allows 20), the rest on the page through ``more``."""

    type: Literal["list"] = "list"
    columns: list[Column] = Field(max_length=6)
    rows: list[Row] = Field(max_length=20)
    total: int = Field(ge=0)
    #: feature id of the full list ("Tümünü … aç")
    more: Name | None = None
    empty: Txt | None = None


class Fact(_Strict):
    label: Txt
    #: the value with its unit and, where useful, a sentence (simplicity rule 5: never a bare number)
    value: Txt
    status: Literal["ok", "warn", "bad", "info"] = "info"


class FactsCard(CardBase):
    type: Literal["facts"] = "facts"
    items: list[Fact] = Field(max_length=8)
    nav: Name | None = None


class Option(_Strict):
    value: OptionValue | int
    label: Txt
    hint: Txt | None = None


class ChoiceCard(CardBase):
    """helper.md A2: one ambiguous argument ("Hangi A 204?"), 2–5 options; the pick re-asks the action's card."""

    type: Literal["choice"] = "choice"
    arg: Name
    question: Txt
    options: list[Option] = Field(min_length=2, max_length=5)
    #: the other arguments already resolved (sent back with the pick)
    args: dict[Name, Scalar] = Field(default_factory=dict)


# ------------------------------------------------------------------------------------------------ writes


class FormField(_Strict):
    name: Name
    label: Txt
    kind: Literal["text", "number", "date", "time", "period", "room", "select", "toggle", "textarea"]
    required: bool
    value: Scalar = None
    #: options the client fetches from the existing endpoints with the person's own session
    options_source: Literal["rooms", "periods", "reasons"] | None = None
    options: list[Option] = Field(default_factory=list, max_length=12)
    max_length: int | None = None


class FormCard(CardBase):
    """Missing or ambiguous arguments of a write (or "Değiştir"); submitting asks the action's card again."""

    type: Literal["form"] = "form"
    action: Name
    fields: list[FormField] = Field(max_length=7)
    missing: list[Name] = Field(default_factory=list)
    risk: Literal["R1", "R2"]
    message: Txt | None = None


class PreviewLine(_Strict):
    label: Txt
    value: Txt


class ConfirmCard(CardBase):
    """The server preview of one write. The card *is* the confirmation (R1); R2 names who is affected. Only the
    button confirms (``POST /helper/actions/confirm`` with ``token``); typed text never does."""

    type: Literal["confirm"] = "confirm"
    action: Name
    risk: Literal["R1", "R2"]
    token: Token
    expires_at: datetime
    preview: list[PreviewLine] = Field(max_length=8)
    #: R2: who else is affected ("P. T.'ye bildirim gider")
    affected: Txt | None = None
    warnings: list[Txt] = Field(default_factory=list, max_length=4)
    #: the primary button: effect + object ("Rezerve et: A 204 · 18.02.2026 10:10–10:50"), built by the server
    button: Txt
    undoable: bool
    danger: bool = False
    #: the arguments the preview was built from (prefill for "Değiştir")
    args: dict[Name, Scalar] = Field(default_factory=dict)


class Entity(_Strict):
    kind: Literal["booking", "approval_request", "note"]
    id: int
    feature_id: Name | None = None


class FollowUp(_Strict):
    """helper.md A7: ≤ 2 chips after a result, an action with partial args or a feature to open."""

    label: Txt
    action: Name | None = None
    feature_id: Name | None = None
    args: dict[Name, Scalar] = Field(default_factory=dict)


class ResultCard(CardBase):
    type: Literal["result"] = "result"
    action: Name
    ok: bool
    message: Txt
    entity: Entity | None = None
    undo_token: Token | None = None
    undo_expires_at: datetime | None = None
    follow_ups: list[FollowUp] = Field(default_factory=list, max_length=2)


# ------------------------------------------------------------------------------------------------ status


class _StatusCard(CardBase):
    code: Annotated[str, Field(pattern=r"^[a-z_]{2,48}$")]
    message: Txt
    #: index hits as "Nerede?" rows (≤ 3)
    fallback: list[NavCard] = Field(default_factory=list, max_length=3)


class LimitCard(_StatusCard):
    type: Literal["limit"] = "limit"


class RefusalCard(_StatusCard):
    type: Literal["refusal"] = "refusal"


class ErrorCard(_StatusCard):
    type: Literal["error"] = "error"


Card = Annotated[
    AnswerCard
    | NavCard
    | ListCard
    | FactsCard
    | ChoiceCard
    | FormCard
    | ConfirmCard
    | ResultCard
    | LimitCard
    | RefusalCard
    | ErrorCard,
    Field(discriminator="type"),
]
CARD_ADAPTER: TypeAdapter[Any] = TypeAdapter(Card)
CARD_TYPES = ("answer", "nav", "list", "facts", "choice", "form", "confirm", "result", "limit", "refusal", "error")


def validate_card(data: Any) -> Any:
    """Parse a card (the turn loop and the tests check every emitted card with it)."""
    return CARD_ADAPTER.validate_python(data)


def card_json_schema() -> dict[str, Any]:
    schema = CARD_ADAPTER.json_schema(mode="serialization")
    return {"$id": SCHEMA_ID, "title": "SmartSched helper card v1", **schema}


__all__ = [
    "CARD_ADAPTER",
    "CARD_TYPES",
    "CARD_VERSION",
    "Card",
    "ChoiceCard",
    "Column",
    "ConfirmCard",
    "Entity",
    "ErrorCard",
    "Fact",
    "FactsCard",
    "FollowUp",
    "FormCard",
    "FormField",
    "LimitCard",
    "ListCard",
    "NavCard",
    "Option",
    "PLAIN_PATTERN",
    "PreviewLine",
    "RefusalCard",
    "ResultCard",
    "Row",
    "RowAction",
    "SCHEMA_ID",
    "Texts",
    "Txt",
    "AnswerCard",
    "card_json_schema",
    "validate_card",
]
