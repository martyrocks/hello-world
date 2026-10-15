from __future__ import annotations

from ..config import Settings
from .base import Provider, ProviderError
from .demo import DemoProvider
from .duffel import DuffelProvider
from .serpapi import SerpApiProvider
from .travelpayouts import TravelpayoutsProvider

ALL = {
    "travelpayouts": TravelpayoutsProvider,
    "duffel": DuffelProvider,
    "serpapi": SerpApiProvider,
    "demo": DemoProvider,
}


def configured_providers(settings: Settings, only: list[str] | None = None) -> list[Provider]:
    """Build every provider that has credentials; fall back to demo data if none do."""
    providers: list[Provider] = []
    if settings.travelpayouts_token:
        providers.append(TravelpayoutsProvider(settings.travelpayouts_token))
    if settings.duffel_token:
        providers.append(DuffelProvider(settings.duffel_token))
    if settings.serpapi_key:
        providers.append(SerpApiProvider(settings.serpapi_key))
    if only:
        wanted = {n.strip().lower() for n in only}
        unknown = wanted - set(ALL)
        if unknown:
            raise ValueError(f"Unknown provider(s): {', '.join(sorted(unknown))}")
        providers = [p for p in providers if p.name in wanted]
        if "demo" in wanted:
            providers.append(DemoProvider())
        missing = wanted - {p.name for p in providers}
        if missing:
            raise ValueError(
                f"Provider(s) not configured (missing API key): {', '.join(sorted(missing))}"
            )
    if not providers:
        providers.append(DemoProvider())
    return providers


__all__ = ["ALL", "Provider", "ProviderError", "configured_providers"]
