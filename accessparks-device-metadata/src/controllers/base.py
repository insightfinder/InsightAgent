from __future__ import annotations

from typing import Protocol

from models import ControllerDevice


class Controller(Protocol):
    """A vendor controller that can list its devices.

    Sites/networks/customers a vendor organizes devices under are an
    implementation detail of list_devices() — they are not part of this
    interface and are not carried onto ControllerDevice.
    """

    name: str

    def list_devices(self) -> list[ControllerDevice]: ...
