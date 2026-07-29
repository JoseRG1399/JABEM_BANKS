"""Interfaz común que deben implementar todos los parsers de archivos bancarios."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.constants import FileType
from app.schemas.parsed_movement import ParseOutcome


class BaseParser(ABC):
    file_type: FileType

    @abstractmethod
    def parse(self, file_path: Path) -> ParseOutcome:
        """Lee el archivo indicado y devuelve las filas interpretadas y los
        errores encontrados. Una fila inválida no debe interrumpir la lectura
        del resto del archivo.
        """
        raise NotImplementedError


def decode_bytes(raw_bytes: bytes) -> str:
    """Decodifica el contenido de un archivo probando codificaciones comunes."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")
