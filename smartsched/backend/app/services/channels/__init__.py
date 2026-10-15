"""Notification channels ("Bildirim kanalları") on Apprise + pywebpush; see app/models/channels.py and
docs/product/2026-10-15-integrations-options.md.

Modules: :mod:`.config` (administrator configuration, KVKK gate, VAPID), :mod:`.links` (user linking),
:mod:`.targets` (department webhooks), :mod:`.text` (TR/EN messages, link-only), :mod:`.outbox` (worker queue),
:mod:`.transport` (the network boundary), :mod:`.adapters` (``notify_dispatch`` channels).

Nothing registers on import. :func:`register` adds the adapters to ``app.services.notify_dispatch`` once per process
(the start-up hook); :func:`unregister` removes them (tests).
"""

from __future__ import annotations


def register() -> None:
    from app.services import notify_dispatch as nd
    from app.services.channels.adapters import ADAPTERS

    names = {a.name for a in nd.channels()}
    for adapter in ADAPTERS:
        if adapter.name not in names:
            nd.register_channel(adapter)


def unregister() -> None:
    from app.services import notify_dispatch as nd
    from app.services.channels.adapters import ADAPTERS

    for adapter in ADAPTERS:
        nd.unregister_channel(adapter.name)
