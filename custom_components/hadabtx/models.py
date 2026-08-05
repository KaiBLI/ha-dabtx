"""Runtime data models shared between platforms for one config entry."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional


@dataclass
class PendingConfig:
    """
    Holds values staged in the dashboard (Number/Select/Text entities) but
    not yet written to the modulator. Cleared fields are represented as
    None (or "" for text) and are left out of the applied change entirely.
    """

    remote_ip: Optional[str] = None
    remote_port: Optional[int] = None
    frequency_hz: Optional[float] = None
    dab_block: Optional[str] = None
    amplitude: Optional[int] = None
    dac_current: Optional[int] = None
    connection_mode: Optional[str] = None
    tii_main_id: Optional[int] = None
    tii_sub_id: Optional[int] = None
    def as_kwargs(self) -> dict:
        """Only the fields that have actually been staged."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if getattr(self, f.name) not in (None, "")
        }
