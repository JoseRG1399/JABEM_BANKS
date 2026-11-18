"""Worker en segundo plano para consultar la API de las tiendas sin congelar la UI."""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from app.integrations.store_api import StoreApiClient, StoreApiError


class StoreApiWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        host: str,
        fetch: Callable[[StoreApiClient, dt.date, dt.date], dict],
        parse: Callable[[dict], object],
        date_from: dt.date,
        date_to: dt.date,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._fetch = fetch
        self._parse = parse
        self._date_from = date_from
        self._date_to = date_to

    def run(self) -> None:  # noqa: D102 (override de QThread)
        try:
            client = StoreApiClient(self._host)
            payload = self._fetch(client, self._date_from, self._date_to)
            self.finished_ok.emit(self._parse(payload))
        except StoreApiError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - una respuesta inesperada no debe tumbar la app
            self.failed.emit(f"No se pudo procesar la respuesta de la API: {exc}")
