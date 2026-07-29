# Analizador Bancario

Sistema de escritorio para Windows que importa movimientos bancarios desde
archivos TXT y CSV, evita duplicados, clasifica movimientos por sucursal y
categoría (con reglas configurables), y genera reportes y exportaciones a
Excel. Funciona completamente de manera local, sin conexión a internet.

El nombre de la aplicación puede cambiarse desde la pantalla de
Configuración (o editando `app/config.py` → `APP_NAME_DEFAULT`).

---

## 1. Requisitos

- Windows 10/11.
- Python 3.12 o superior.
- ~500 MB libres para el entorno virtual y las dependencias (PySide6 es el
  paquete más pesado).

---

## 2. Creación del entorno virtual

Desde la raíz del proyecto, en PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

---

## 3. Instalación de dependencias

```bash
pip install -r requirements.txt
```

Esto instala: PySide6, SQLAlchemy, Alembic, pandas, openpyxl, pytest y
PyInstaller.

---

## 4. Inicialización de la base de datos

```bash
python scripts/initialize_database.py
```

Crea (o actualiza) el archivo SQLite y aplica las migraciones de Alembic.
También ocurre automáticamente la primera vez que se ejecuta `main.py`.

---

## 5. Carga de catálogos iniciales

```bash
python scripts/seed_catalogs.py
```

Carga bancos (BBVA, Mifel), cuentas (BBVA, MIFEL, MIFEL2), las 21
sucursales, sus identificadores, las 10 categorías y las 8 reglas de
clasificación especiales descritas en la especificación. El script es
**idempotente**: ejecutarlo varias veces no duplica registros. También se
ejecuta automáticamente al iniciar `main.py`.

---

## 6. Ejecución

```bash
python main.py
```

Abre la ventana principal. En el primer arranque puede tardar unos segundos
mientras se verifica/crea la base de datos y se cargan los catálogos.

---

## 7. Pruebas

```bash
pytest
```

Suite completa: parsers (TXT/CSV con distintos casos borde), normalización,
dinero, fechas, hashes, duplicados, clasificación, reclasificación manual,
repositorios (paginación y filtros), reportes, exportación a Excel,
respaldos, y pruebas de humo de la interfaz gráfica (construyen las
pantallas y diálogos reales contra una base de datos real, en modo
`offscreen` de Qt, ya que no es posible tomar capturas de una app de
escritorio en un entorno sin pantalla).

Para correr solo un subconjunto:

```bash
pytest tests/parsers -v
pytest tests/services -v
```

---

## 8. Generación del ejecutable

```bash
python scripts/build_executable.py
```

Genera `dist/AnalizadorBancario/AnalizadorBancario.exe` (aplicación sin
consola). Para personalizar el icono, coloca un archivo `resources/icon.ico`
antes de compilar.

> El ejecutable **no** incluye Alembic ni los archivos de migración: al
> detectar su ausencia, la aplicación crea el esquema directamente desde los
> modelos (equivalente para una base de datos nueva). Ver "Decisiones
> técnicas" más abajo.

---

## 9. Ubicación de la base de datos

- **Modo desarrollo** (`python main.py`): `data/database/analizador_bancario.db`,
  dentro del repositorio.
- **Modo empaquetado** (ejecutable de PyInstaller):
  `%LOCALAPPDATA%\AnalizadorBancario\database\analizador_bancario.db`.

---

## 10. Ubicación de respaldos, logs y exportaciones

Misma lógica que la base de datos (`data/...` en desarrollo,
`%LOCALAPPDATA%\AnalizadorBancario\...` en el ejecutable):

| Carpeta | Desarrollo | Empaquetado |
|---|---|---|
| Base de datos | `data/database/` | `%LOCALAPPDATA%\AnalizadorBancario\database\` |
| Respaldos | `data/backups/` | `%LOCALAPPDATA%\AnalizadorBancario\backups\` |
| Exportaciones | `data/exports/` | `%LOCALAPPDATA%\AnalizadorBancario\exports\` |
| Logs | `data/logs/` | `%LOCALAPPDATA%\AnalizadorBancario\logs\` |
| Configuración (`settings.json`) | `data/config/` | `%LOCALAPPDATA%\AnalizadorBancario\config\` |

Las carpetas de exportaciones y respaldos también pueden cambiarse desde
Configuración. Desde esa misma pantalla hay botones para abrir la carpeta de
respaldos y la de logs directamente.

---

## Estructura del proyecto

```text
analizador_bancario/
├── main.py                      # Punto de entrada (UI)
├── requirements.txt
├── pyproject.toml
├── alembic.ini
├── README.md
│
├── app/
│   ├── config.py                 # Rutas, AppSettings (settings.json)
│   ├── constants.py               # Enums de dominio
│   │
│   ├── database/
│   │   ├── connection.py          # Engine SQLAlchemy (WAL, foreign_keys)
│   │   ├── session.py             # Database, session_scope()
│   │   ├── migrator.py            # Alembic upgrade / create_all fallback
│   │   ├── seed.py                # Catálogos iniciales (idempotente)
│   │   └── migrations/            # Alembic (env.py + versions/)
│   │
│   ├── models/                    # Bank, BankAccount, Branch,
│   │                               # BranchIdentifier, MovementCategory,
│   │                               # ClassificationRule, ImportedFile,
│   │                               # Movement, MovementClassificationHistory
│   │
│   ├── repositories/              # Acceso a datos (sin SQL en la UI)
│   │
│   ├── parsers/                   # BbvaTxtParser, MifelCsvParser, factory
│   │
│   ├── services/
│   │   ├── normalization_service.py
│   │   ├── duplicate_service.py
│   │   ├── classification_service.py   # motor de reglas + reclasificación
│   │   ├── import_service.py           # orquestador de importación
│   │   ├── report_service.py           # 8 reportes (sección 15.8)
│   │   ├── export_service.py           # exportación a Excel
│   │   └── backup_service.py           # respaldo / restauración
│   │
│   ├── schemas/                   # dataclasses de transporte
│   │
│   ├── ui/
│   │   ├── main_window.py, theme.py
│   │   ├── pages/                 # dashboard, import, movements,
│   │   │                          # unclassified, branches, rules,
│   │   │                          # reports, settings
│   │   ├── dialogs/               # import_result, movement_detail,
│   │   │                          # classify_movement, branch, rule
│   │   ├── widgets/                # sidebar, metric_card, filter_bar,
│   │   │                           # pagination, loading_overlay
│   │   └── workers/                # ImportWorker (QThread)
│   │
│   └── utils/                     # dates, money, text, hashes, logging
│
├── tests/                         # pytest (unidad + integración + humo UI)
│   ├── parsers/, services/, repositories/, fixtures/
│
├── data/                          # BD/respaldos/exportaciones/logs (dev)
│
└── scripts/
    ├── initialize_database.py
    ├── seed_catalogs.py
    └── build_executable.py
```

---

## Decisiones técnicas

- **Dinero en centavos enteros**: `cargo`/`abono`/`saldo` se parsean con
  `Decimal` y se persisten como `int` (centavos) para evitar errores de
  redondeo de `float`.
- **Duplicados por ocurrencia**: el hash de un movimiento no incluye un
  contador; se calcula cuántas veces aparece cada hash dentro del archivo
  nuevo y cuántas ya existen en la base, y solo se insertan las apariciones
  que excedan lo ya guardado. Esto permite que dos movimientos legítimamente
  idénticos coexistan sin perderse ni duplicarse.
- **Clasificación en memoria por importación**: reglas e identificadores se
  cargan una sola vez por archivo importado (no por fila), para escalar a
  archivos grandes.
- **Alembic con fallback**: en desarrollo se usan migraciones reales; el
  ejecutable empaquetado no las incluye (por la complejidad de rutas
  relativas dentro de un bundle de PyInstaller) y en su lugar crea el
  esquema directamente desde los modelos SQLAlchemy la primera vez que se
  ejecuta. Para una base de datos nueva el resultado es idéntico.
- **Sin ORM en la UI**: toda la interfaz pasa por repositorios; ninguna
  pantalla ejecuta SQL directamente.
- **Reclasificación retroactiva**: al crear una regla desde la pantalla de
  reclasificación manual, se aplica no solo al movimiento seleccionado sino
  a todos los movimientos existentes que coincidan (con confirmación
  explícita del usuario mostrando cuántos se verían afectados).
- **Respaldos con la API nativa de SQLite** (`sqlite3.Connection.backup`),
  no una copia de archivo, para que funcionen de forma segura con el modo
  WAL activo.

---

## Limitaciones conocidas

- El "Formato de fecha" y el "Tema" de Configuración se aplican en caliente
  a la sesión activa; algunos estilos de tema oscuro pueden no cubrir el
  100% de los widgets nativos de Qt en casos de borde no probados
  manualmente.
- La detección de columnas del TXT de BBVA usa un encabezado con las
  palabras "Cargo"/"Abono"/"Saldo" para ubicar posiciones; un banco con un
  layout radicalmente distinto necesitaría su propio parser (el diseño ya
  contempla esto vía `parser_factory.register_parser`).
- La reclasificación retroactiva al crear una regla recorre los movimientos
  candidatos en Python (no solo con `SQL` agregado) porque el motor de
  coincidencias soporta expresiones regulares arbitrarias; en bases de
  datos muy grandes (cientos de miles de movimientos) esa operación puntual
  puede tardar unos segundos.
- No se implementó un mecanismo de undo/deshacer para la reclasificación
  masiva más allá del historial de auditoría (`MovementClassificationHistory`);
  revertir manualmente requiere reclasificar de nuevo.
- Las pruebas de interfaz gráfica son "de humo" (construyen pantallas y
  ejercitan sus acciones principales contra una base de datos real) y no
  sustituyen una verificación visual manual, que no fue posible realizar en
  este entorno de desarrollo por no contar con una herramienta de captura
  de pantalla para aplicaciones de escritorio.

---

## Siguientes mejoras recomendadas

1. Agregar más parsers de bancos reales conforme se disponga de archivos de
   ejemplo (el diseño ya está preparado para ello).
2. Mover la reclasificación retroactiva masiva a un `QThread` si en la
   práctica llega a tardar más de uno o dos segundos con datos reales.
3. Completar el modo oscuro con una revisión visual manual pantalla por
   pantalla.
4. Agregar accesos directos de teclado y un modo de alto contraste para
   accesibilidad.
5. Exponer `rows_per_page`/moneda de forma más granular (por ejemplo,
   moneda por cuenta bancaria en vez de una sola configuración global).
