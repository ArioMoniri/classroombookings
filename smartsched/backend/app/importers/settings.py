"""Importer settings (environment / ``.env``, prefix ``IMPORT_``).

* ``IMPORT_NON_ROOM_VENUES`` (JSON list): words and phrases of a *definitive room* cell that name a place
  that is no classroom (CASE, an office, ONLINE, Zoom ...).  A row whose definitive cell names one of
  them and no room code needs no room (``needs_room=false``) and gets a data note.  Matching is on whole
  words after Turkish folding (``ONLINE`` = ``online``, ``ÖĞRETİM ÜYESİ ODASI`` = ``öğretim üyesi odası``).
* ``IMPORT_GRID_CARRY_FORWARD`` (bool, default off): when a weekly board has fewer week sheets than the
  term has weeks (the Güz board has weeks 1-2 only), the last week's *blocks* (closed rooms, HAZIRLIK,
  events) also hold in the missing weeks.  Off by default: a missing week is reported, nothing invented.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Turkish and English defaults (lower case, matched after Turkish folding)
DEFAULT_NON_ROOM_VENUES: tuple[str, ...] = (
    # CASE: the simulation centre (Center of Advanced Simulation and Education), not a classroom
    "case",
    "simülasyon merkezi",
    # offices
    "öğretim üyesi odası",
    "öğretim üyesinin odası",
    "öğretim elemanı odası",
    "hoca odası",
    "hocanın odası",
    "ofis",
    "office",
    "instructor's office",
    # distance / online
    "online",
    "çevrimiçi",
    "uzaktan",
    "uzaktan eğitim",
    "uzem",
    "zoom",
    "teams",
    "microsoft teams",
    "google meet",
    "webex",
    "remote",
    # clubs and other non-teaching rooms
    "kulüp",
    "kulübü",
    "klüp",
    "klubü",
    "club",
)


class ImporterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IMPORT_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    non_room_venues: list[str] = list(DEFAULT_NON_ROOM_VENUES)
    grid_carry_forward: bool = False


def importer_settings() -> ImporterSettings:
    """Read on every import (cheap) so a changed environment applies without a restart."""
    return ImporterSettings()


__all__ = ["DEFAULT_NON_ROOM_VENUES", "ImporterSettings", "importer_settings"]
