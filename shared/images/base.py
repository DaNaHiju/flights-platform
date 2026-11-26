"""The ImageProvider interface: what the platform needs from a photo source.

Callers (the API router) depend on this module only, like FlightProvider. A
provider returns the image bytes themselves, not a link: photos are served from
our own origin, never hotlinked from the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ImageProviderError(Exception):
    """The provider could not answer right now (rate limit, timeout, bad reply).

    Transient by definition: callers must NOT cache it. The message is safe to
    log: providers never put credentials or request URLs in it.
    """


@dataclass(frozen=True)
class DestinationImage:
    """A photo plus the attribution the provider's terms require."""

    data: bytes
    content_type: str
    credit_user: str
    # The provider's page for this photo; the credit links to it.
    credit_url: str


class ImageProvider(Protocol):
    """A source of destination photos."""

    name: str

    def find_destination_image(self, city: str, country: str) -> DestinationImage | None:
        """A photo of the place, or None when the provider has no usable one.

        Raises ImageProviderError when the provider could not answer (the caller
        must not treat that as "no photo exists").
        """
        ...
