"""Cliente HTTP de la API de las tiendas (proyecto externo).

Usa solo la biblioteca estándar (``urllib``) para no añadir dependencias al
ejecutable. Los errores de red o de formato se reportan siempre como
``StoreApiError`` con un mensaje apto para mostrarse al usuario.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_HOST_ENV_VAR = "NEXT_PUBLIC_API_HOST"
DEFAULT_TIMEOUT_SECONDS = 60

# El endpoint conserva el nombre del sistema de ventas (DIDI); en la app se muestra como Uber.
UBER_SALES_ENDPOINT = "/getVentasDeDIDIByFechasConDetalleDeVentas"
TRANSFER_PAYMENTS_ENDPOINT = "/manageInfoOfTransferenciaPayments"


class StoreApiError(Exception):
    """Error al consultar la API de las tiendas."""


def resolve_api_host(configured_host: str = "") -> str:
    """Host de la API: primero el configurado en la app y, si no hay, la
    variable de entorno ``NEXT_PUBLIC_API_HOST``."""
    return (configured_host or os.environ.get(API_HOST_ENV_VAR, "")).strip()


def build_day_range(date_from: dt.date, date_to: dt.date) -> tuple[str, str]:
    """Rango en el formato que espera la API (igual al del proyecto web)."""
    return (
        f"{date_from.isoformat()}T00:00:00.229Z",
        f"{date_to.isoformat()}T23:59:59.229Z",
    )


class StoreApiClient:
    def __init__(self, host: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        host = (host or "").strip().rstrip("/")
        parsed = urllib.parse.urlparse(host)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise StoreApiError(
                "La dirección de la API no está configurada o no es válida. "
                "Captúrala en Configuración (por ejemplo https://servidor.com)."
            )
        self._host = host
        self._timeout = timeout

    def get_uber_sales(self, date_from: dt.date, date_to: dt.date) -> dict[str, Any]:
        start, end = build_day_range(date_from, date_to)
        return self._post(UBER_SALES_ENDPOINT, {"startDate": start, "endDate": end})

    def get_transfer_payments(self, date_from: dt.date, date_to: dt.date) -> dict[str, Any]:
        start, end = build_day_range(date_from, date_to)
        return self._post(TRANSFER_PAYMENTS_ENDPOINT, {"startDate": start, "endDate": end})

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self._host}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise StoreApiError(f"La API respondió con error {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise StoreApiError(
                f"No se pudo conectar con la API. Revisa tu conexión a internet. ({exc})"
            ) from exc

        try:
            data = json.loads(body)
        except ValueError as exc:
            raise StoreApiError("La API devolvió una respuesta que no es JSON válido.") from exc
        if not isinstance(data, dict):
            raise StoreApiError("La API devolvió una respuesta con formato inesperado.")
        return data
