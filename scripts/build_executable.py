"""Genera el ejecutable de Windows con PyInstaller (sección 25).

Uso:
    python scripts/build_executable.py

Genera: dist/AnalizadorBancario/AnalizadorBancario.exe

El ejecutable incluye ``alembic.ini`` y la carpeta de migraciones
(``app/database/migrations``): ``app/database/migrator.py`` los localiza en
``sys._MEIPASS`` cuando corre empaquetado y aplica las migraciones
pendientes con Alembic, igual que en desarrollo. Esto es lo que permite que
instalar una versión nueva sobre una base de datos ya en uso agregue las
columnas/tablas nuevas sin perder los datos existentes, en vez de recurrir
a ``Base.metadata.create_all`` (que solo sirve para una base de datos
nueva y jamás altera tablas que ya existen).

``app/database/migrations/env.py`` se agrega como archivo de datos, no como
módulo: Alembic lo carga en tiempo de ejecución con ``exec()`` (no con un
``import`` normal), así que PyInstaller nunca rastrea sus imports al
analizar el grafo de dependencias. Por eso se declaran a mano como
``--hidden-import`` los que ``env.py`` necesita y que ningún otro módulo ya
importa de forma normal (p. ej. ``logging.config``, usado solo ahí).
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
        f"--add-data={PROJECT_ROOT / 'alembic.ini'}{';'}.",
        f"--add-data={PROJECT_ROOT / 'app' / 'database' / 'migrations'}{';'}app/database/migrations",
        "--hidden-import=logging.config",
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
