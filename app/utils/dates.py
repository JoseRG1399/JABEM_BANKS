"""Utilidades para el manejo de fechas.

La aplicación se usa en México: el formato principal de entrada y de
visualización es día/mes/año. Las fechas ambiguas nunca se interpretan
como formato estadounidense (mes/día/año).
"""
from __future__ import annotations

import datetime as dt

_INPUT_FORMATS = (
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
)

DISPLAY_FORMAT = "%d/%m/%Y"
ISO_FORMAT = "%Y-%m-%d"

_active_display_format = DISPLAY_FORMAT


def set_display_format(fmt: str) -> None:
    """Cambia el formato usado por ``format_date_for_display`` (configurable
    desde la pantalla de Configuración, sección 17)."""
    global _active_display_format
    _active_display_format = fmt or DISPLAY_FORMAT


def get_display_format() -> str:
    return _active_display_format


def parse_date(raw: str | dt.date | dt.datetime | None) -> dt.date | None:
    """Parsea una fecha en cualquiera de los formatos soportados.

    Soporta: ``01-07-2026``, ``01/07/2026``, ``2026-07-01``.
    """
    if raw is None:
        return None
    if isinstance(raw, dt.datetime):
        return raw.date()
    if isinstance(raw, dt.date):
        return raw

    text = str(raw).strip()
    if not text:
        return None

    for fmt in _INPUT_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Formato de fecha no reconocido: {raw!r}")


def format_date_for_display(value: dt.date | None) -> str:
    if value is None:
        return ""
    return value.strftime(_active_display_format)


def format_date_iso(value: dt.date | None) -> str:
    if value is None:
        return ""
    return value.strftime(ISO_FORMAT)
