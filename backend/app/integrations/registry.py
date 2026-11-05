from __future__ import annotations

from .base import Connector
from .connectors import PLANNED, EbayConnector, EtsyConnector, RedditConnector, ShopifyConnector, YouTubeConnector

CONNECTOR_CLASSES: dict[str, type[Connector]] = {
    c.id: c for c in (YouTubeConnector, RedditConnector, EbayConnector, EtsyConnector, ShopifyConnector, *PLANNED)
}

_instances: dict[str, Connector] = {}


def get(cid: str) -> Connector:
    if cid not in CONNECTOR_CLASSES:
        raise KeyError(f"unknown connector '{cid}'")
    if cid not in _instances:
        _instances[cid] = CONNECTOR_CLASSES[cid]()
    return _instances[cid]


def register(instance: Connector) -> None:
    """Register/override an instance (tests, custom adapters)."""
    CONNECTOR_CLASSES.setdefault(instance.id, type(instance))
    _instances[instance.id] = instance


def reset() -> None:
    _instances.clear()


def all_status() -> list[dict]:
    return [get(cid).status() for cid in CONNECTOR_CLASSES]


def research_connectors() -> list[Connector]:
    return [get(cid) for cid, c in CONNECTOR_CLASSES.items() if c.kind == "research"]
