"""Genera el ejecutable de Windows con PyInstaller (sección 25).

Uso:
    python scripts/build_executable.py

Genera: dist/AnalizadorBancario/AnalizadorBancario.exe

Decisión de diseño: el ejecutable NO incluye ``alembic.ini`` ni las
migraciones. ``app/database/migrator.py`` detecta su ausencia y crea el
esquema directamente desde los modelos (``Base.metadata.create_all``), que
es equivalente para una base de datos nueva. Esto evita los problemas de
rutas relativas de Alembic dentro de un paquete congelado.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = PROJECT_ROOT / "public" / "images" / "Logo.ico"


def main() -> None:
    import PyInstaller.__main__

    args = [
        str(PROJECT_ROOT / "main.py"),
        "--name=AnalizadorBancario",
        "--windowed",
        "--noconfirm",
        f"--distpath={PROJECT_ROOT / 'dist'}",
        f"--workpath={PROJECT_ROOT / 'build'}",
        f"--specpath={PROJECT_ROOT}",
        f"--add-data={PROJECT_ROOT / 'public' / 'images'}{';'}public/images",
    ]

    if ICON_PATH.exists():
        args.append(f"--icon={ICON_PATH}")
    else:
        print(
            f"Aviso: no se encontró un icono en {ICON_PATH}; el ejecutable se "
            "generará con el icono por defecto. Coloca un archivo .ico ahí para "
            "personalizarlo."
        )

    PyInstaller.__main__.run(args)

    exe_path = PROJECT_ROOT / "dist" / "AnalizadorBancario" / "AnalizadorBancario.exe"
    if exe_path.exists():
        print(f"\nEjecutable generado en: {exe_path}")
    else:
        print("\nEl ejecutable no se generó en la ubicación esperada; revisa la salida de PyInstaller.")


if __name__ == "__main__":
    main()
