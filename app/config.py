"""Configuración central de la aplicación: rutas, nombre, valores por defecto."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME_DEFAULT = "Analizador Bancario"
APP_VERSION = "0.1.0"
COMPANY_FOLDER_NAME = "AnalizadorBancario"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_base_data_dir() -> Path:
    """Devuelve la carpeta raíz de datos de la aplicación.

    En modo empaquetado (PyInstaller) usa %LOCALAPPDATA%\\AnalizadorBancario
    porque la carpeta del ejecutable puede estar protegida contra escritura.
    En modo desarrollo usa la carpeta ``data`` del repositorio.
    """
    if is_frozen():
        local_app_data = Path.home() / "AppData" / "Local"
        return local_app_data / COMPANY_FOLDER_NAME
    return Path(__file__).resolve().parent.parent / "data"


@dataclass
class AppPaths:
    base_dir: Path
    database_dir: Path
    backups_dir: Path
    imports_dir: Path
    exports_dir: Path
    logs_dir: Path
    config_dir: Path

    @classmethod
    def from_base(cls, base_dir: Path) -> "AppPaths":
        return cls(
            base_dir=base_dir,
            database_dir=base_dir / "database",
            backups_dir=base_dir / "backups",
            imports_dir=base_dir / "imports",
            exports_dir=base_dir / "exports",
            logs_dir=base_dir / "logs",
            config_dir=base_dir / "config",
        )

    def ensure_exist(self) -> None:
        for path in (
            self.base_dir,
            self.database_dir,
            self.backups_dir,
            self.imports_dir,
            self.exports_dir,
            self.logs_dir,
            self.config_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def database_file(self) -> Path:
        return self.database_dir / "analizador_bancario.db"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"


@dataclass
class AppSettings:
    """Configuración editable por el usuario. Persistida en JSON."""

    app_name: str = APP_NAME_DEFAULT
    company_name: str = ""
    export_folder: str = ""
    backup_folder: str = ""
    date_format: str = "%d/%m/%Y"
    rows_per_page: int = 100
    backup_frequency_days: int = 1
    currency: str = "MXN"
    theme: str = "light"

    @classmethod
    def load(cls, settings_file: Path) -> "AppSettings":
        if not settings_file.exists():
            return cls()
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def save(self, settings_file: Path) -> None:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )


class Config:
    """Punto de acceso único a rutas y configuración de la aplicación."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.paths = AppPaths.from_base(base_dir or get_base_data_dir())
        self.paths.ensure_exist()
        self.settings = AppSettings.load(self.paths.settings_file)
        if not self.settings.export_folder:
            self.settings.export_folder = str(self.paths.exports_dir)
        if not self.settings.backup_folder:
            self.settings.backup_folder = str(self.paths.backups_dir)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.paths.database_file.as_posix()}"

    def save_settings(self) -> None:
        self.settings.save(self.paths.settings_file)


_config_instance: Config | None = None


def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
