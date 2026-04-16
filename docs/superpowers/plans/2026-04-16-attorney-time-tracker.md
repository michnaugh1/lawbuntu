# Attorney Time Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a passive, GNOME-native time tracker that attributes desktop activity to legal matters and exports CJA-20 CSVs, hourly invoices, and flat-fee analytics for a solo criminal defense attorney on Ubuntu/Wayland.

**Architecture:** A Python daemon (systemd user service) receives focus events from a GNOME Shell extension and tab events from a browser extension via DBus, matches them to matters indexed from `~/OpenCases/` (rclone-mounted Google Drive), and persists sessions to SQLite. A separate GTK4/libadwaita review app reads the same database for narrative editing and export.

**Tech Stack:** Python 3.12, SQLite (WAL), PyGObject/GTK4/libadwaita, pydbus, PyYAML, inotify-simple, pytest, GJS (GNOME Shell extension), WebExtensions MV3 (browser extension), Ollama HTTP API (opt-in narratives), LibreOffice UNO (invoice PDF).

---

## File Map

```
ubuntu-lawyers/
├── daemon/
│   ├── __main__.py          # Entry point: wires all components, starts GLib mainloop
│   ├── config.py            # Loads ~/.config/ubuntu-lawyers/config.yaml
│   ├── db.py                # SQLite connection, WAL mode, schema init
│   ├── models.py            # Dataclasses: Matter, Session, Entry, ActivityItem, Config
│   ├── matter_indexer.py    # Scans ~/OpenCases/, parses .matter.yaml, inotify watcher
│   ├── matter_matcher.py    # Scores signals against matter index; returns best match
│   ├── timer.py             # Session state machine: start/pause/switch/close, idle
│   └── dbus_service.py      # Exposes com.northcoastlegal.UbuntuLawyers1 on session bus
├── extension/
│   ├── metadata.json        # GNOME Shell extension metadata
│   ├── extension.js         # Registers focus listener; sends events to daemon via DBus
│   └── indicator.js         # Top-bar panel: matter name, confirmation, matter picker
├── browser-extension/
│   ├── manifest.json        # WebExtensions MV3 manifest
│   ├── background.js        # Service worker: tab activated/updated listener
│   └── native-host/
│       ├── host.py          # Native messaging host: stdin/stdout ↔ daemon DBus
│       └── com.northcoastlegal.ubuntu_lawyers.json  # Host manifest
├── review-app/
│   ├── main.py              # GTK4 app entry point
│   ├── window.py            # AdwApplicationWindow with sidebar nav
│   ├── views/
│   │   ├── today.py         # Today view: timeline bar + entry list
│   │   ├── analytics.py     # Flat-fee dashboard
│   │   └── export.py        # CJA CSV + hourly invoice export
│   ├── widgets/
│   │   ├── timeline.py      # Custom Cairo timeline drawing widget
│   │   └── entry_row.py     # Entry row: narrative field, CJA dropdown, Ollama button
│   └── ollama.py            # HTTP client for localhost Ollama narrative suggestions
├── tests/
│   ├── conftest.py          # Shared fixtures: in-memory DB, sample matters
│   ├── test_matter_matcher.py
│   ├── test_timer.py
│   ├── test_matter_indexer.py
│   ├── test_db.py
│   ├── test_cja_export.py
│   └── test_flat_fee.py
├── install.sh               # Installs all components; registers systemd units
├── ubuntu-lawyers-daemon.service  # systemd user unit for daemon
├── rclone-opencases.service       # systemd user unit for rclone mount
├── pyproject.toml
└── docs/
    └── test-matrix.md
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `daemon/__init__.py`, `daemon/models.py` (stub)
- Create: `tests/conftest.py` (stub)
- Create: `review-app/__init__.py` (stub)

- [ ] **Step 1: Create directory structure**

```bash
cd ~/Dev/Ubuntu_Lawyers
mkdir -p daemon extension browser-extension/native-host review-app/views review-app/widgets tests
touch daemon/__init__.py review-app/__init__.py review-app/views/__init__.py review-app/widgets/__init__.py
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "ubuntu-lawyers"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydbus>=0.6",
    "PyYAML>=6.0",
    "inotify-simple>=1.3",
    "PyGObject>=3.44",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.setuptools.packages.find]
where = ["."]
include = ["daemon*", "review-app*"]
```

- [ ] **Step 3: Create stub `tests/conftest.py`**

```python
import pytest
import sqlite3
from daemon.db import init_schema

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()
```

- [ ] **Step 4: Install dev dependencies**

```bash
pip install -e ".[dev]"
```

Expected: installs without errors.

- [ ] **Step 5: Verify pytest runs (empty)**

```bash
pytest -v
```

Expected: `no tests ran`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml daemon/ review-app/ tests/ browser-extension/ extension/
git commit -m "feat: project scaffold with directory structure and pyproject.toml"
```

---

## Task 2: Data Models

**Files:**
- Create: `daemon/models.py`

- [ ] **Step 1: Write `daemon/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, Union


class MatterType(str, Enum):
    FEDERAL_CJA = "federal_cja"
    RETAINED_HOURLY = "retained_hourly"
    RETAINED_FLAT = "retained_flat"
    PRO_BONO = "pro_bono"
    CONSULTATION = "consultation"
    PROGRAM_ADMIN = "program_admin"


class MatterStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ON_HOLD = "on_hold"


class CJACategory(str, Enum):
    IN_COURT = "A"
    INTERVIEW = "B"
    INVESTIGATION = "C"
    RESEARCH = "D"
    TRAVEL = "E"
    OTHER = "F"


class AttributionSource(str, Enum):
    FILE_PATH = "file_path"
    CASE_NUMBER = "case_number"
    ALIAS = "alias"
    FOLDER_NAME = "folder_name"
    LAST_NAME = "last_name"
    MANUAL = "manual"


@dataclass
class ClientPerson:
    last: str
    first: str
    middle: str = ""
    dob: Optional[date] = None
    phone: str = ""
    email: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.last}, {self.first}"


@dataclass
class ClientOrg:
    organization: str
    contact_name: str = ""
    contact_phone: str = ""

    @property
    def display_name(self) -> str:
        return self.organization


@dataclass
class CourtInfo:
    name: str
    case_number: str
    judge: str = ""
    division: str = ""
    county: str = ""


@dataclass
class BillingInfo:
    flat_fee: Optional[float] = None
    hourly_rate: Optional[float] = None
    cja_rate: Optional[float] = None
    retainer_paid: float = 0.0
    underwater_threshold: float = 0.0


@dataclass
class Matter:
    id: int
    folder_path: str
    matter_type: MatterType
    status: MatterStatus
    client: Union[ClientPerson, ClientOrg]
    billing: BillingInfo
    aliases: list[str] = field(default_factory=list)
    court: Optional[CourtInfo] = None
    appointment_date: Optional[date] = None
    charges: list[str] = field(default_factory=list)
    co_counsel: list[dict] = field(default_factory=list)
    opposing_party: str = ""
    next_hearing: Optional[date] = None
    referral_source: str = ""
    notes: str = ""
    date_opened: Optional[date] = None
    date_closed: Optional[date] = None
    indexed_at: Optional[datetime] = None

    @property
    def display_name(self) -> str:
        return self.client.display_name


@dataclass
class MatchResult:
    matter: Matter
    score: int
    source: AttributionSource


@dataclass
class ActivityItem:
    app_id: str
    window_title: str
    tab_url: str
    duration_ms: int


@dataclass
class Session:
    id: int
    matter_id: int
    start_ts: datetime
    end_ts: Optional[datetime]
    attribution_score: int
    attribution_source: AttributionSource
    activity: list[ActivityItem] = field(default_factory=list)


@dataclass
class Entry:
    id: int
    matter_id: int
    date: date
    narrative: str
    cja_category: Optional[CJACategory]
    hours: float
    exported_at: Optional[datetime] = None


@dataclass
class Config:
    opencases_path: str = "~/OpenCases"
    idle_timeout_minutes: int = 5
    gap_threshold_minutes: int = 20
    events_log_retention_days: int = 30
    ollama_endpoint: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    notification_hour: int = 17
    non_matter_categories: list[str] = field(
        default_factory=lambda: ["Admin", "Marketing", "CLE", "Personal", "Break"]
    )
```

- [ ] **Step 2: Verify import**

```bash
python -c "from daemon.models import Matter, MatterType, Config; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add daemon/models.py
git commit -m "feat: data models for matters, sessions, entries, config"
```

---

## Task 3: Database Layer

**Files:**
- Create: `daemon/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing test `tests/test_db.py`**

```python
import sqlite3
from daemon.db import init_schema, get_connection


def test_init_schema_creates_tables(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row["name"] for row in cursor.fetchall()}
    assert tables == {"activity_trail", "entries", "events_log", "matters", "sessions"}


def test_wal_mode_enabled():
    conn = get_connection()
    row = conn.execute("PRAGMA journal_mode").fetchone()
    conn.close()
    assert row[0] == "wal"


def test_foreign_keys_enabled(db):
    row = db.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1


def test_insert_and_retrieve_matter(db):
    db.execute(
        """INSERT INTO matters (folder_path, last_name, first_name, matter_type, status, metadata_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("/home/user/OpenCases/Smith, John", "Smith", "John", "federal_cja", "active", "{}"),
    )
    db.commit()
    row = db.execute("SELECT * FROM matters WHERE last_name=?", ("Smith",)).fetchone()
    assert row["first_name"] == "John"
    assert row["matter_type"] == "federal_cja"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_db.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `daemon.db` does not exist yet.

- [ ] **Step 3: Write `daemon/db.py`**

```python
from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "ubuntu-lawyers" / "time.db"


def get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS matters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_path TEXT UNIQUE NOT NULL,
            last_name TEXT,
            first_name TEXT,
            organization TEXT,
            matter_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            metadata_json TEXT,
            indexed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER REFERENCES matters(id) ON DELETE CASCADE,
            start_ts TEXT NOT NULL,
            end_ts TEXT,
            attribution_score INTEGER DEFAULT 0,
            attribution_source TEXT DEFAULT 'manual'
        );

        CREATE TABLE IF NOT EXISTS activity_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            app_id TEXT DEFAULT '',
            window_title TEXT DEFAULT '',
            tab_url TEXT DEFAULT '',
            duration_ms INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER REFERENCES matters(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            narrative TEXT DEFAULT '',
            cja_category TEXT,
            hours REAL NOT NULL DEFAULT 0.0,
            exported_at TEXT,
            UNIQUE(matter_id, date)
        );

        CREATE TABLE IF NOT EXISTS events_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT
        );
    """)
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add daemon/db.py tests/test_db.py
git commit -m "feat: SQLite database layer with WAL mode and schema"
```

---

## Task 4: Config Loading

**Files:**
- Create: `daemon/config.py`

- [ ] **Step 1: Write `daemon/config.py`**

```python
from __future__ import annotations
import yaml
from pathlib import Path
from daemon.models import Config

CONFIG_PATH = Path.home() / ".config" / "ubuntu-lawyers" / "config.yaml"

DEFAULT_CONFIG: dict = {
    "opencases_path": "~/OpenCases",
    "idle_timeout_minutes": 5,
    "gap_threshold_minutes": 20,
    "events_log_retention_days": 30,
    "ollama_endpoint": "http://localhost:11434",
    "ollama_model": "qwen2.5:3b",
    "notification_hour": 17,
    "non_matter_categories": ["Admin", "Marketing", "CLE", "Personal", "Break"],
}


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config(**DEFAULT_CONFIG)
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    merged = {**DEFAULT_CONFIG, **data}
    # Expand ~ in paths
    merged["opencases_path"] = str(Path(merged["opencases_path"]).expanduser())
    return Config(**{k: v for k, v in merged.items() if k in Config.__dataclass_fields__})


def write_default_config(path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
```

- [ ] **Step 2: Verify**

```bash
python -c "from daemon.config import load_config; c = load_config(); print(c.idle_timeout_minutes)"
```

Expected: `5`

- [ ] **Step 3: Commit**

```bash
git add daemon/config.py
git commit -m "feat: config loading with defaults and YAML override"
```

---

## Task 5: Matter YAML Parser

**Files:**
- Create: `daemon/matter_indexer.py` (parsing portion)
- Create: `tests/test_matter_indexer.py`

- [ ] **Step 1: Write failing tests `tests/test_matter_indexer.py`**

```python
import pytest
from pathlib import Path
from datetime import date
from daemon.matter_indexer import parse_matter_yaml, parse_folder_name
from daemon.models import MatterType, MatterStatus, ClientPerson, ClientOrg


def test_parse_folder_name_person():
    client = parse_folder_name("Smith, John")
    assert isinstance(client, ClientPerson)
    assert client.last == "Smith"
    assert client.first == "John"


def test_parse_folder_name_no_comma_returns_none():
    result = parse_folder_name("Special Assignment - Ogemaw")
    assert result is None


def test_parse_minimal_yaml(tmp_path):
    yaml_content = ""
    yaml_file = tmp_path / ".matter.yaml"
    yaml_file.write_text(yaml_content)
    matter = parse_matter_yaml(tmp_path, matter_id=1)
    assert matter is not None
    assert matter.status == MatterStatus.ACTIVE


def test_parse_full_person_yaml(tmp_path):
    yaml_content = """
client:
  last: Smith
  first: John
  dob: 1985-03-14
matter_type: federal_cja
status: active
court:
  name: "U.S. District Court, W.D. Mich."
  case_number: "1:26-cr-00123"
  judge: "Hon. Jane Doe"
billing:
  cja_rate: 175.00
aliases:
  - Smith
  - "1:26-cr-00123"
opposing_party: "United States of America"
"""
    (tmp_path / ".matter.yaml").write_text(yaml_content)
    matter = parse_matter_yaml(tmp_path, matter_id=1)
    assert matter.matter_type == MatterType.FEDERAL_CJA
    assert isinstance(matter.client, ClientPerson)
    assert matter.client.last == "Smith"
    assert matter.court.case_number == "1:26-cr-00123"
    assert matter.billing.cja_rate == 175.00
    assert "Smith" in matter.aliases


def test_parse_org_yaml(tmp_path):
    yaml_content = """
client:
  organization: "Ogemaw County"
  contact_name: "County Admin"
matter_type: program_admin
billing:
  hourly_rate: 200.00
aliases:
  - "Special Assignment"
  - Ogemaw
"""
    (tmp_path / ".matter.yaml").write_text(yaml_content)
    matter = parse_matter_yaml(tmp_path, matter_id=2)
    assert matter.matter_type == MatterType.PROGRAM_ADMIN
    assert isinstance(matter.client, ClientOrg)
    assert matter.client.organization == "Ogemaw County"
    assert matter.billing.hourly_rate == 200.00


def test_parse_malformed_yaml_returns_none(tmp_path):
    (tmp_path / ".matter.yaml").write_text("{{invalid: yaml: [}")
    matter = parse_matter_yaml(tmp_path, matter_id=3)
    assert matter is None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_matter_indexer.py -v
```

Expected: `ImportError` — `matter_indexer` not defined.

- [ ] **Step 3: Write parsing functions in `daemon/matter_indexer.py`**

```python
from __future__ import annotations
import re
import yaml
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from daemon.models import (
    Matter, MatterType, MatterStatus, ClientPerson, ClientOrg,
    CourtInfo, BillingInfo, Config,
)

_NAME_RE = re.compile(r"^([^,]+),\s*(.+)$")


def parse_folder_name(folder_name: str) -> Optional[ClientPerson]:
    m = _NAME_RE.match(folder_name.strip())
    if not m:
        return None
    return ClientPerson(last=m.group(1).strip(), first=m.group(2).strip())


def _parse_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val))
    except ValueError:
        return None


def parse_matter_yaml(folder_path: Path, matter_id: int) -> Optional[Matter]:
    yaml_path = folder_path / ".matter.yaml"
    data: dict = {}
    if yaml_path.exists():
        try:
            loaded = yaml.safe_load(yaml_path.read_text()) or {}
            if isinstance(loaded, dict):
                data = loaded
        except yaml.YAMLError:
            return None

    # Parse client
    client_data = data.get("client", {}) or {}
    if "organization" in client_data:
        client = ClientOrg(
            organization=client_data["organization"],
            contact_name=client_data.get("contact_name", ""),
            contact_phone=client_data.get("contact_phone", ""),
        )
    else:
        person = parse_folder_name(folder_path.name)
        if person is None and ("last" not in client_data):
            person = ClientPerson(last=folder_path.name, first="")
        client = ClientPerson(
            last=client_data.get("last", person.last if person else folder_path.name),
            first=client_data.get("first", person.first if person else ""),
            middle=client_data.get("middle", ""),
            dob=_parse_date(client_data.get("dob")),
            phone=client_data.get("phone", ""),
            email=client_data.get("email", ""),
        )

    # Parse court
    court_data = data.get("court", {}) or {}
    court = CourtInfo(
        name=court_data.get("name", ""),
        case_number=court_data.get("case_number", ""),
        judge=court_data.get("judge", ""),
        division=court_data.get("division", ""),
        county=court_data.get("county", ""),
    ) if court_data else None

    # Parse billing
    billing_data = data.get("billing", {}) or {}
    billing = BillingInfo(
        flat_fee=billing_data.get("flat_fee"),
        hourly_rate=billing_data.get("hourly_rate"),
        cja_rate=billing_data.get("cja_rate"),
        retainer_paid=float(billing_data.get("retainer_paid", 0.0)),
        underwater_threshold=float(billing_data.get("underwater_threshold", 0.0)),
    )

    matter_type_str = data.get("matter_type", "retained_flat")
    try:
        matter_type = MatterType(matter_type_str)
    except ValueError:
        matter_type = MatterType.RETAINED_FLAT

    status_str = data.get("status", "active")
    try:
        status = MatterStatus(status_str)
    except ValueError:
        status = MatterStatus.ACTIVE

    return Matter(
        id=matter_id,
        folder_path=str(folder_path),
        matter_type=matter_type,
        status=status,
        client=client,
        billing=billing,
        court=court,
        appointment_date=_parse_date(data.get("appointment_date")),
        aliases=list(data.get("aliases", []) or []),
        charges=list(data.get("charges", []) or []),
        co_counsel=list(data.get("co_counsel", []) or []),
        opposing_party=data.get("opposing_party", ""),
        next_hearing=_parse_date(data.get("next_hearing")),
        referral_source=data.get("referral_source", ""),
        notes=data.get("notes", ""),
        date_opened=_parse_date(data.get("date_opened")),
        date_closed=_parse_date(data.get("date_closed")),
        indexed_at=datetime.now(),
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matter_indexer.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add daemon/matter_indexer.py tests/test_matter_indexer.py
git commit -m "feat: .matter.yaml parser and folder-name client parsing"
```

---

## Task 6: Matter Indexer (inotify watcher)

**Files:**
- Modify: `daemon/matter_indexer.py` (add MatterIndex class)

- [ ] **Step 1: Add failing test to `tests/test_matter_indexer.py`**

```python
from daemon.matter_indexer import MatterIndex

def test_index_scans_directory(tmp_path):
    # Two valid matter folders
    (tmp_path / "Smith, John").mkdir()
    (tmp_path / "Jones, Mary").mkdir()
    # One folder without a person name and no .matter.yaml — should be flagged
    (tmp_path / "Special Assignment").mkdir()

    index = MatterIndex(opencases_path=tmp_path)
    index.scan()

    assert len(index.matters) == 2
    assert len(index.unrecognized) == 1
    names = {m.client.display_name for m in index.matters.values()}
    assert "Smith, John" in names
    assert "Jones, Mary" in names


def test_index_org_folder_with_yaml(tmp_path):
    folder = tmp_path / "Special Assignment - Ogemaw"
    folder.mkdir()
    (folder / ".matter.yaml").write_text(
        "client:\n  organization: Ogemaw County\nmatter_type: program_admin\nbilling:\n  hourly_rate: 200.0\n"
    )
    index = MatterIndex(opencases_path=tmp_path)
    index.scan()
    assert len(index.matters) == 1
    assert len(index.unrecognized) == 0


def test_index_get_by_path(tmp_path):
    folder = tmp_path / "Smith, John"
    folder.mkdir()
    index = MatterIndex(opencases_path=tmp_path)
    index.scan()
    matter = index.get_by_path(str(folder))
    assert matter is not None
    assert matter.client.last == "Smith"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_matter_indexer.py::test_index_scans_directory -v
```

Expected: `ImportError` for `MatterIndex`.

- [ ] **Step 3: Append `MatterIndex` class to `daemon/matter_indexer.py`**

```python
class MatterIndex:
    def __init__(self, opencases_path: Path):
        self.opencases_path = Path(opencases_path)
        self.matters: dict[str, Matter] = {}   # folder_path -> Matter
        self.unrecognized: list[Path] = []
        self._next_id = 1

    def scan(self) -> None:
        self.matters.clear()
        self.unrecognized.clear()
        if not self.opencases_path.exists():
            return
        for folder in sorted(self.opencases_path.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            self._index_folder(folder)

    def _index_folder(self, folder: Path) -> None:
        matter = parse_matter_yaml(folder, matter_id=self._next_id)
        if matter is not None:
            self.matters[str(folder)] = matter
            self._next_id += 1
        else:
            # parse_matter_yaml returns None only on malformed YAML
            # Try folder-name parse as fallback
            client = parse_folder_name(folder.name)
            if client is not None:
                m = Matter(
                    id=self._next_id,
                    folder_path=str(folder),
                    matter_type=MatterType.RETAINED_FLAT,
                    status=MatterStatus.ACTIVE,
                    client=client,
                    billing=BillingInfo(),
                    indexed_at=datetime.now(),
                )
                self.matters[str(folder)] = m
                self._next_id += 1
            else:
                self.unrecognized.append(folder)

    def get_by_path(self, folder_path: str) -> Optional[Matter]:
        return self.matters.get(folder_path)

    def get_by_id(self, matter_id: int) -> Optional[Matter]:
        for m in self.matters.values():
            if m.id == matter_id:
                return m
        return None

    def all_active(self) -> list[Matter]:
        return [m for m in self.matters.values() if m.status == MatterStatus.ACTIVE]
```

- [ ] **Step 4: Add inotify live-watching to `MatterIndex`**

Append this method to the `MatterIndex` class in `daemon/matter_indexer.py`:

```python
    def start_watching(self, on_change: callable = None) -> None:
        """Start a daemon thread that re-scans OpenCases on filesystem changes."""
        import threading
        import inotify_simple

        def _watch():
            if not self.opencases_path.exists():
                return
            inotify = inotify_simple.INotify()
            flags = (inotify_simple.flags.CREATE | inotify_simple.flags.DELETE |
                     inotify_simple.flags.MODIFY | inotify_simple.flags.MOVED_TO)
            inotify.add_watch(str(self.opencases_path), flags)
            while True:
                events = inotify.read(timeout=5000)
                if events:
                    self.scan()
                    if on_change:
                        on_change()

        threading.Thread(target=_watch, daemon=True).start()
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_matter_indexer.py -v
```

Expected: all 10 passed.

- [ ] **Step 6: Commit**

```bash
git add daemon/matter_indexer.py tests/test_matter_indexer.py
git commit -m "feat: MatterIndex with directory scanning, get_by_id, and inotify live-watching"
```

---

## Task 7: Matter Matcher

**Files:**
- Create: `daemon/matter_matcher.py`
- Create: `tests/test_matter_matcher.py`

- [ ] **Step 1: Write failing tests `tests/test_matter_matcher.py`**

```python
import pytest
from pathlib import Path
from daemon.models import Matter, MatterType, MatterStatus, ClientPerson, BillingInfo, CourtInfo, AttributionSource
from daemon.matter_matcher import MatterMatcher, MatchResult

OPENCASES = "/home/user/OpenCases"

def make_matter(last, first, aliases=None, case_number=None, matter_id=1):
    court = CourtInfo(name="Test Court", case_number=case_number) if case_number else None
    return Matter(
        id=matter_id,
        folder_path=f"{OPENCASES}/{last}, {first}",
        matter_type=MatterType.FEDERAL_CJA,
        status=MatterStatus.ACTIVE,
        client=ClientPerson(last=last, first=first),
        billing=BillingInfo(),
        aliases=aliases or [],
        court=court,
    )

@pytest.fixture
def matters():
    return {
        "1": make_matter("Smith", "John", aliases=["Smith", "1:26-cr-00123", "Smith trafficking"], case_number="1:26-cr-00123", matter_id=1),
        "2": make_matter("Jones", "Mary", aliases=["Jones", "2:26-cr-00456"], case_number="2:26-cr-00456", matter_id=2),
    }

@pytest.fixture
def matcher(matters):
    return MatterMatcher(matters=list(matters.values()), opencases_path=OPENCASES)


def test_file_path_match_scores_100(matcher):
    result = matcher.match(
        window_title=f"{OPENCASES}/Smith, John/discovery.pdf - LibreOffice",
        tab_url="",
        app_id="libreoffice-writer"
    )
    assert result is not None
    assert result.score == 100
    assert result.source == AttributionSource.FILE_PATH
    assert result.matter.client.last == "Smith"


def test_case_number_match_scores_90(matcher):
    result = matcher.match(
        window_title="1:26-cr-00123 Motion to Suppress - Firefox",
        tab_url="",
        app_id="firefox"
    )
    assert result is not None
    assert result.score == 90
    assert result.source == AttributionSource.CASE_NUMBER


def test_alias_match_scores_70(matcher):
    result = matcher.match(
        window_title="Smith trafficking — Google Docs",
        tab_url="",
        app_id="firefox"
    )
    assert result is not None
    assert result.score == 70
    assert result.source == AttributionSource.ALIAS


def test_folder_name_match_scores_60(matcher):
    result = matcher.match(
        window_title="Smith, John - case notes.odt",
        tab_url="",
        app_id="libreoffice-writer"
    )
    assert result is not None
    assert result.score == 60
    assert result.source == AttributionSource.FOLDER_NAME


def test_last_name_only_scores_30(matcher):
    result = matcher.match(
        window_title="Smith medical records",
        tab_url="",
        app_id="evince"
    )
    assert result is not None
    assert result.score == 30
    assert result.source == AttributionSource.LAST_NAME


def test_no_match_returns_none(matcher):
    result = matcher.match(
        window_title="Firefox — New Tab",
        tab_url="about:newtab",
        app_id="firefox"
    )
    assert result is None


def test_url_also_checked(matcher):
    result = matcher.match(
        window_title="",
        tab_url="https://drive.google.com/drive/folders/smith-john-folder",
        app_id="chrome"
    )
    # tab_url contains "smith" — last_name match
    assert result is not None


def test_weak_match_below_50_flagged(matcher):
    result = matcher.match(
        window_title="John is here",
        tab_url="",
        app_id="gnome-terminal"
    )
    # "John" alone is not an alias or last name match — should be None or score < 50
    if result:
        assert result.score < 50
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_matter_matcher.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Write `daemon/matter_matcher.py`**

```python
from __future__ import annotations
import re
from typing import Optional
from daemon.models import Matter, AttributionSource, MatchResult


class MatterMatcher:
    def __init__(self, matters: list[Matter], opencases_path: str):
        self.matters = matters
        self.opencases_path = opencases_path.rstrip("/")

    def match(self, window_title: str, tab_url: str, app_id: str) -> Optional[MatchResult]:
        combined = f"{window_title} {tab_url}".lower()
        best: Optional[MatchResult] = None

        for matter in self.matters:
            result = self._score(matter, window_title, tab_url, combined)
            if result and (best is None or result.score > best.score):
                best = result

        return best

    def _score(self, matter: Matter, title: str, url: str, combined: str) -> Optional[MatchResult]:
        # Score 100: file path match
        if self.opencases_path.lower() in combined and matter.client.display_name.lower() in combined:
            return MatchResult(matter=matter, score=100, source=AttributionSource.FILE_PATH)

        # Score 90: case number match
        if matter.court and matter.court.case_number:
            cn = matter.court.case_number.lower()
            if cn in combined:
                return MatchResult(matter=matter, score=90, source=AttributionSource.CASE_NUMBER)

        # Score 70: alias match (whole word)
        for alias in matter.aliases:
            pattern = r"\b" + re.escape(alias.lower()) + r"\b"
            if re.search(pattern, combined):
                return MatchResult(matter=matter, score=70, source=AttributionSource.ALIAS)

        # Score 60: full folder name match "Lastname, Firstname"
        display = matter.client.display_name.lower()
        if display in combined:
            return MatchResult(matter=matter, score=60, source=AttributionSource.FOLDER_NAME)

        # Score 30: last name only (person matters)
        from daemon.models import ClientPerson
        if isinstance(matter.client, ClientPerson) and matter.client.last:
            pattern = r"\b" + re.escape(matter.client.last.lower()) + r"\b"
            if re.search(pattern, combined):
                return MatchResult(matter=matter, score=30, source=AttributionSource.LAST_NAME)

        return None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matter_matcher.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add daemon/matter_matcher.py tests/test_matter_matcher.py
git commit -m "feat: matter matcher with scored signal matching (path/case/alias/name)"
```

---

## Task 8: Timer State Machine

**Files:**
- Create: `daemon/timer.py`
- Create: `tests/test_timer.py`

- [ ] **Step 1: Write failing tests `tests/test_timer.py`**

```python
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from daemon.timer import TimerStateMachine, TimerState
from daemon.models import Matter, MatterType, MatterStatus, ClientPerson, BillingInfo, AttributionSource, MatchResult


def make_matter(matter_id=1, last="Smith"):
    return Matter(
        id=matter_id,
        folder_path=f"/home/user/OpenCases/{last}, John",
        matter_type=MatterType.FEDERAL_CJA,
        status=MatterStatus.ACTIVE,
        client=ClientPerson(last=last, first="John"),
        billing=BillingInfo(),
    )


def make_match(matter, score=70):
    return MatchResult(matter=matter, score=score, source=AttributionSource.ALIAS)


@pytest.fixture
def timer(db):
    return TimerStateMachine(db=db, idle_timeout_seconds=300, gap_threshold_seconds=1200)


def test_initial_state(timer):
    assert timer.state == TimerState.IDLE
    assert timer.current_session_id is None


def test_start_session_on_match(timer):
    matter = make_matter()
    timer.on_match(make_match(matter), ts=datetime(2026, 4, 16, 9, 0, 0))
    assert timer.state == TimerState.ACTIVE
    assert timer.active_matter_id == 1
    assert timer.current_session_id is not None


def test_idle_pauses_timer(timer):
    matter = make_matter()
    timer.on_match(make_match(matter), ts=datetime(2026, 4, 16, 9, 0, 0))
    timer.on_idle(ts=datetime(2026, 4, 16, 9, 5, 0))
    assert timer.state == TimerState.PAUSED


def test_resume_on_input_after_idle(timer):
    matter = make_matter()
    timer.on_match(make_match(matter), ts=datetime(2026, 4, 16, 9, 0, 0))
    timer.on_idle(ts=datetime(2026, 4, 16, 9, 5, 0))
    timer.on_input(ts=datetime(2026, 4, 16, 9, 7, 0))
    assert timer.state == TimerState.ACTIVE


def test_matter_switch_closes_session(timer, db):
    matter_a = make_matter(matter_id=1, last="Smith")
    matter_b = make_matter(matter_id=2, last="Jones")
    # Insert both matters into DB
    for m in [matter_a, matter_b]:
        db.execute(
            "INSERT INTO matters (id, folder_path, last_name, first_name, matter_type, status) VALUES (?,?,?,?,?,?)",
            (m.id, m.folder_path, m.client.last, m.client.first, m.matter_type.value, m.status.value)
        )
    db.commit()
    timer.on_match(make_match(matter_a), ts=datetime(2026, 4, 16, 9, 0, 0))
    timer.on_match(make_match(matter_b), ts=datetime(2026, 4, 16, 9, 30, 0))
    assert timer.active_matter_id == 2
    # First session should be closed
    row = db.execute("SELECT end_ts FROM sessions WHERE matter_id=1").fetchone()
    assert row is not None
    assert row["end_ts"] is not None


def test_lock_screen_closes_session(timer, db):
    matter = make_matter()
    db.execute(
        "INSERT INTO matters (id, folder_path, last_name, first_name, matter_type, status) VALUES (?,?,?,?,?,?)",
        (matter.id, matter.folder_path, matter.client.last, matter.client.first, matter.matter_type.value, matter.status.value)
    )
    db.commit()
    timer.on_match(make_match(matter), ts=datetime(2026, 4, 16, 9, 0, 0))
    timer.on_lock(ts=datetime(2026, 4, 16, 9, 30, 0))
    assert timer.state == TimerState.IDLE
    row = db.execute("SELECT end_ts FROM sessions").fetchone()
    assert row["end_ts"] is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_timer.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Write `daemon/timer.py`**

```python
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from enum import Enum
from typing import Optional
from daemon.models import MatchResult, AttributionSource


class TimerState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"


class TimerStateMachine:
    def __init__(self, db: sqlite3.Connection, idle_timeout_seconds: int = 300, gap_threshold_seconds: int = 1200):
        self.db = db
        self.idle_timeout_seconds = idle_timeout_seconds
        self.gap_threshold_seconds = gap_threshold_seconds
        self.state: TimerState = TimerState.IDLE
        self.active_matter_id: Optional[int] = None
        self.current_session_id: Optional[int] = None
        self._session_start: Optional[datetime] = None

    def on_match(self, match: MatchResult, ts: Optional[datetime] = None) -> None:
        ts = ts or datetime.now()
        if self.active_matter_id == match.matter.id and self.state == TimerState.ACTIVE:
            return  # Same matter, nothing to do
        if self.current_session_id is not None:
            self._close_session(ts)
        self._open_session(match, ts)

    def on_idle(self, ts: Optional[datetime] = None) -> None:
        if self.state != TimerState.ACTIVE:
            return
        self.state = TimerState.PAUSED

    def on_input(self, ts: Optional[datetime] = None) -> None:
        if self.state != TimerState.PAUSED:
            return
        self.state = TimerState.ACTIVE

    def on_lock(self, ts: Optional[datetime] = None) -> None:
        ts = ts or datetime.now()
        if self.current_session_id is not None:
            self._close_session(ts)
        self.state = TimerState.IDLE

    def on_no_match(self, ts: Optional[datetime] = None) -> None:
        ts = ts or datetime.now()
        if self.current_session_id is not None:
            self._close_session(ts)
        self.state = TimerState.IDLE

    def _open_session(self, match: MatchResult, ts: datetime) -> None:
        cursor = self.db.execute(
            "INSERT INTO sessions (matter_id, start_ts, attribution_score, attribution_source) VALUES (?,?,?,?)",
            (match.matter.id, ts.isoformat(), match.score, match.source.value),
        )
        self.db.commit()
        self.current_session_id = cursor.lastrowid
        self.active_matter_id = match.matter.id
        self._session_start = ts
        self.state = TimerState.ACTIVE

    def _close_session(self, ts: datetime) -> None:
        self.db.execute(
            "UPDATE sessions SET end_ts=? WHERE id=?",
            (ts.isoformat(), self.current_session_id),
        )
        self.db.commit()
        self.current_session_id = None
        self.active_matter_id = None
        self._session_start = None
        self.state = TimerState.IDLE
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_timer.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add daemon/timer.py tests/test_timer.py
git commit -m "feat: timer state machine with session open/close/pause/switch"
```

---

## Task 9: DBus Service + Daemon Entry Point

**Files:**
- Create: `daemon/dbus_service.py`
- Create: `daemon/__main__.py`
- Create: `ubuntu-lawyers-daemon.service`

- [ ] **Step 1: Write `daemon/dbus_service.py`**

```python
from __future__ import annotations
import json
import logging
from datetime import datetime
from gi.repository import GLib
from pydbus import SessionBus
from daemon.models import MatchResult, AttributionSource
from daemon.matter_matcher import MatterMatcher
from daemon.timer import TimerStateMachine

logger = logging.getLogger(__name__)

DBUS_NAME = "com.northcoastlegal.UbuntuLawyers1"
DBUS_PATH = "/com/northcoastlegal/UbuntuLawyers1"

DBUS_XML = """
<node>
  <interface name='com.northcoastlegal.UbuntuLawyers1'>
    <method name='FocusChanged'>
      <arg type='s' name='app_id' direction='in'/>
      <arg type='s' name='window_title' direction='in'/>
    </method>
    <method name='TabChanged'>
      <arg type='s' name='tab_title' direction='in'/>
      <arg type='s' name='tab_url' direction='in'/>
    </method>
    <method name='IdleStarted'/>
    <method name='IdleEnded'/>
    <method name='LockScreen'/>
    <method name='ManualSetMatter'>
      <arg type='i' name='matter_id' direction='in'/>
    </method>
    <method name='GetCurrentMatter'>
      <arg type='s' name='json' direction='out'/>
    </method>
    <signal name='MatterChanged'>
      <arg type='s' name='matter_json'/>
    </signal>
  </interface>
</node>
"""


class UbuntuLawyersService:
    dbus = DBUS_XML

    def __init__(self, matcher: MatterMatcher, timer: TimerStateMachine, index):
        self._matcher = matcher
        self._timer = timer
        self._index = index
        self._last_title = ""
        self._last_url = ""
        self._last_app = ""

    def FocusChanged(self, app_id: str, window_title: str) -> None:
        self._last_app = app_id
        self._last_title = window_title
        self._evaluate()

    def TabChanged(self, tab_title: str, tab_url: str) -> None:
        self._last_title = tab_title
        self._last_url = tab_url
        self._evaluate()

    def IdleStarted(self) -> None:
        self._timer.on_idle()

    def IdleEnded(self) -> None:
        self._timer.on_input()

    def LockScreen(self) -> None:
        self._timer.on_lock()

    def ManualSetMatter(self, matter_id: int) -> None:
        matter = self._index.get_by_id(matter_id)
        if matter:
            from daemon.models import MatchResult, AttributionSource
            result = MatchResult(matter=matter, score=100, source=AttributionSource.MANUAL)
            self._timer.on_match(result)
            self.MatterChanged(json.dumps({"id": matter.id, "name": matter.display_name}))

    def GetCurrentMatter(self) -> str:
        if self._timer.active_matter_id is None:
            return json.dumps(None)
        matter_id = self._timer.active_matter_id
        for m in self._index.matters.values():
            if m.id == matter_id:
                return json.dumps({"id": m.id, "name": m.display_name, "matter_type": m.matter_type.value})
        return json.dumps(None)

    def MatterChanged(self, matter_json: str) -> None:
        pass  # GLib signal — emitted via pydbus

    def _evaluate(self) -> None:
        result = self._matcher.match(
            window_title=self._last_title,
            tab_url=self._last_url,
            app_id=self._last_app,
        )
        if result is None:
            self._timer.on_no_match()
        else:
            self._timer.on_match(result)
```

- [ ] **Step 2: Write `daemon/__main__.py`**

```python
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from gi.repository import GLib, Notify
from pydbus import SessionBus
from daemon.config import load_config
from daemon.db import get_connection
from daemon.matter_indexer import MatterIndex
from daemon.matter_matcher import MatterMatcher
from daemon.timer import TimerStateMachine
from daemon.dbus_service import UbuntuLawyersService, DBUS_NAME, DBUS_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _schedule_eod_notification(db, config, loop):
    """Fire one GNOME notification at notification_hour if entries need narratives."""
    Notify.init("Ubuntu Lawyers")

    def _check_and_notify():
        now = datetime.now()
        if now.hour == config.notification_hour:
            today = now.date().isoformat()
            row = db.execute(
                "SELECT COUNT(*) as n FROM entries WHERE date=? AND (narrative IS NULL OR narrative='')",
                (today,)
            ).fetchone()
            count = row["n"] if row else 0
            if count > 0:
                n = Notify.Notification.new(
                    "Ubuntu Lawyers",
                    f"{count} entr{'y' if count == 1 else 'ies'} from today need narratives.",
                    "dialog-information"
                )
                n.show()
        return True  # keep GLib timeout alive

    # Check every 60 seconds; only notifies during the configured hour
    GLib.timeout_add_seconds(60, _check_and_notify)


def main():
    config = load_config()
    db = get_connection()

    index = MatterIndex(opencases_path=Path(config.opencases_path))
    index.scan()
    logger.info(f"Indexed {len(index.matters)} matters, {len(index.unrecognized)} unrecognized")

    matcher = MatterMatcher(matters=index.all_active(), opencases_path=config.opencases_path)
    timer = TimerStateMachine(
        db=db,
        idle_timeout_seconds=config.idle_timeout_minutes * 60,
        gap_threshold_seconds=config.gap_threshold_minutes * 60,
    )

    # Re-sync matcher when index changes (inotify)
    def _on_index_change():
        matcher.matters = index.all_active()

    index.start_watching(on_change=_on_index_change)

    service = UbuntuLawyersService(matcher=matcher, timer=timer, index=index)

    bus = SessionBus()
    bus.publish(DBUS_NAME, service)
    logger.info(f"Published DBus service: {DBUS_NAME}")

    loop = GLib.MainLoop()
    _schedule_eod_notification(db, config, loop)

    def handle_signal(signum, frame):
        logger.info("Shutting down")
        loop.quit()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        loop.run()
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write `ubuntu-lawyers-daemon.service`**

```ini
[Unit]
Description=Ubuntu Lawyers Time Tracker Daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.local/bin/ubuntu-lawyers-daemon
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target
```

- [ ] **Step 4: Verify daemon starts (manual test)**

```bash
pip install pydbus PyGObject
python -m daemon
```

Expected: logs `Indexed N matters` and `Published DBus service`, stays running.

- [ ] **Step 5: Commit**

```bash
git add daemon/dbus_service.py daemon/__main__.py ubuntu-lawyers-daemon.service
git commit -m "feat: DBus service and daemon entry point with systemd unit"
```

---

## Task 10: GNOME Shell Extension

**Files:**
- Create: `extension/metadata.json`
- Create: `extension/extension.js`
- Create: `extension/indicator.js`

- [ ] **Step 1: Write `extension/metadata.json`**

```json
{
  "name": "Ubuntu Lawyers",
  "description": "Passive time tracker for legal matters",
  "uuid": "ubuntu-lawyers@northcoastlegal.com",
  "version": 1,
  "shell-version": ["45", "46", "47"],
  "url": "https://github.com/michnaugh1/ubuntu-lawyers"
}
```

- [ ] **Step 2: Write `extension/indicator.js`**

```javascript
import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const DBUS_NAME = 'com.northcoastlegal.UbuntuLawyers1';
const DBUS_PATH = '/com/northcoastlegal/UbuntuLawyers1';

const IFACE_XML = `
<node>
  <interface name="com.northcoastlegal.UbuntuLawyers1">
    <method name="FocusChanged">
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="window_title" direction="in"/>
    </method>
    <method name="IdleStarted"/>
    <method name="IdleEnded"/>
    <method name="LockScreen"/>
    <method name="GetCurrentMatter">
      <arg type="s" name="json" direction="out"/>
    </method>
    <signal name="MatterChanged">
      <arg type="s" name="matter_json"/>
    </signal>
  </interface>
</node>`;

export const UbuntuLawyersIndicator = GObject.registerClass(
class UbuntuLawyersIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Ubuntu Lawyers');
        this._proxy = null;
        this._label = new St.Label({
            text: '⚖ —',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'ubuntu-lawyers-label',
        });
        this.add_child(this._label);
        this._buildMenu();
        this._connectProxy();
    }

    _buildMenu() {
        this._matterItem = new PopupMenu.PopupMenuItem('No active matter', { reactive: false });
        this.menu.addMenuItem(this._matterItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._openReviewItem = new PopupMenu.PopupMenuItem('Open Review App');
        this._openReviewItem.connect('activate', () => {
            Gio.AppInfo.launch_default_for_uri('ubuntu-lawyers-review://', null);
        });
        this.menu.addMenuItem(this._openReviewItem);
    }

    _connectProxy() {
        const ProxyClass = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);
        this._proxy = new ProxyClass(
            Gio.DBus.session,
            DBUS_NAME,
            DBUS_PATH,
            (proxy, error) => {
                if (error) {
                    this._label.text = '⚖ ●';
                    return;
                }
                this._proxy.connectSignal('MatterChanged', (p, s, [json]) => {
                    this._updateMatter(json);
                });
                this._refreshCurrentMatter();
            }
        );
    }

    _refreshCurrentMatter() {
        try {
            const json = this._proxy.GetCurrentMatterSync();
            this._updateMatter(json);
        } catch (_) { /* daemon not ready */ }
    }

    _updateMatter(json) {
        try {
            const matter = JSON.parse(json);
            if (matter) {
                this._label.text = `⚖ ${matter.name}`;
                this._matterItem.label.text = matter.name;
            } else {
                this._label.text = '⚖ —';
                this._matterItem.label.text = 'No active matter';
            }
        } catch (_) {}
    }

    sendFocus(appId, windowTitle) {
        if (!this._proxy) return;
        try {
            this._proxy.FocusChangedSync(appId, windowTitle);
        } catch (_) {}
    }

    sendIdle() {
        if (!this._proxy) return;
        try { this._proxy.IdleStartedSync(); } catch (_) {}
    }

    sendActive() {
        if (!this._proxy) return;
        try { this._proxy.IdleEndedSync(); } catch (_) {}
    }
});
```

- [ ] **Step 3: Write `extension/extension.js`**

```javascript
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { UbuntuLawyersIndicator } from './indicator.js';

let indicator = null;
let _focusId = null;

function _onFocusChanged() {
    const win = global.display.focus_window;
    if (!win || !indicator) return;
    const appId = win.get_wm_class() ?? '';
    const title = win.get_title() ?? '';
    indicator.sendFocus(appId, title);
}

export function enable() {
    indicator = new UbuntuLawyersIndicator();
    Main.panel.addToStatusArea('ubuntu-lawyers', indicator);
    _focusId = global.display.connect('notify::focus-window', _onFocusChanged);
}

export function disable() {
    if (_focusId) {
        global.display.disconnect(_focusId);
        _focusId = null;
    }
    if (indicator) {
        indicator.destroy();
        indicator = null;
    }
}
```

- [ ] **Step 4: Install extension for manual testing**

```bash
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/ubuntu-lawyers@northcoastlegal.com"
mkdir -p "$EXT_DIR"
cp extension/* "$EXT_DIR/"
gnome-extensions enable ubuntu-lawyers@northcoastlegal.com
```

- [ ] **Step 5: Manual test**

Start the daemon (`python -m daemon`), then open different windows. Top-bar should show the matter name when a matching window gets focus. Verify by checking `journalctl --user -u ubuntu-lawyers`.

- [ ] **Step 6: Commit**

```bash
git add extension/
git commit -m "feat: GNOME Shell extension with focus listener and top-bar indicator"
```

---

## Task 11: Browser Extension + Native Host

**Files:**
- Create: `browser-extension/manifest.json`
- Create: `browser-extension/background.js`
- Create: `browser-extension/native-host/host.py`
- Create: `browser-extension/native-host/com.northcoastlegal.ubuntu_lawyers.json`

- [ ] **Step 1: Write `browser-extension/manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "Ubuntu Lawyers",
  "version": "0.1.0",
  "description": "Reports active tab to the Ubuntu Lawyers time tracker",
  "permissions": ["tabs", "nativeMessaging"],
  "background": {
    "service_worker": "background.js"
  }
}
```

- [ ] **Step 2: Write `browser-extension/background.js`**

```javascript
const HOST_NAME = "com.northcoastlegal.ubuntu_lawyers";
let port = null;

function connect() {
    port = chrome.runtime.connectNative(HOST_NAME);
    port.onDisconnect.addListener(() => {
        port = null;
        setTimeout(connect, 5000);
    });
}

function sendTab(tab) {
    if (!port || !tab) return;
    try {
        port.postMessage({ tab_title: tab.title || "", tab_url: tab.url || "" });
    } catch (_) { port = null; }
}

chrome.tabs.onActivated.addListener(({ tabId }) => {
    chrome.tabs.get(tabId, tab => sendTab(tab));
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete") {
        chrome.tabs.query({ active: true, currentWindow: true }, ([active]) => {
            if (active && active.id === tabId) sendTab(tab);
        });
    }
});

connect();
```

- [ ] **Step 3: Write `browser-extension/native-host/host.py`**

```python
#!/usr/bin/env python3
"""Native messaging host: bridges browser extension to daemon via DBus."""
import json
import struct
import sys
import logging
from pydbus import SessionBus

logging.basicConfig(filename="/tmp/ubuntu-lawyers-host.log", level=logging.DEBUG)
logger = logging.getLogger(__name__)

DBUS_NAME = "com.northcoastlegal.UbuntuLawyers1"
DBUS_PATH = "/com/northcoastlegal/UbuntuLawyers1"


def read_message():
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len:
        return None
    msg_len = struct.unpack("=I", raw_len)[0]
    data = sys.stdin.buffer.read(msg_len)
    return json.loads(data.decode("utf-8"))


def write_message(msg):
    data = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def main():
    try:
        bus = SessionBus()
        proxy = bus.get(DBUS_NAME, DBUS_PATH)
    except Exception as e:
        logger.error(f"Could not connect to daemon: {e}")
        proxy = None

    while True:
        msg = read_message()
        if msg is None:
            break
        logger.debug(f"Received: {msg}")
        if proxy:
            try:
                proxy.TabChanged(msg.get("tab_title", ""), msg.get("tab_url", ""))
            except Exception as e:
                logger.warning(f"DBus error: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `browser-extension/native-host/com.northcoastlegal.ubuntu_lawyers.json`**

```json
{
  "name": "com.northcoastlegal.ubuntu_lawyers",
  "description": "Ubuntu Lawyers native messaging host",
  "path": "/home/PLACEHOLDER/.local/lib/ubuntu-lawyers/native-host/host.py",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://PLACEHOLDER_CHROME_ID/",
    "moz-extension://PLACEHOLDER_FIREFOX_UUID/"
  ]
}
```

Note: The `install.sh` script (Task 18) will replace `PLACEHOLDER` with real values and register this file at `~/.mozilla/native-messaging-hosts/` and `~/.config/google-chrome/NativeMessagingHosts/`.

- [ ] **Step 5: Make host executable and test standalone**

```bash
chmod +x browser-extension/native-host/host.py
python browser-extension/native-host/host.py &
# Send a test message (native messaging format: 4-byte length prefix + JSON)
python -c "
import struct, json, sys
msg = json.dumps({'tab_title': 'Smith, John - Google Docs', 'tab_url': 'https://docs.google.com/...'}).encode()
sys.stdout.buffer.write(struct.pack('=I', len(msg)) + msg)
sys.stdout.buffer.flush()
" | python browser-extension/native-host/host.py
```

Check `/tmp/ubuntu-lawyers-host.log` — should show received message and DBus call attempt.

- [ ] **Step 6: Commit**

```bash
git add browser-extension/
git commit -m "feat: browser extension and native messaging host for tab tracking"
```

---

## Task 12: CJA Export and Flat-Fee Calculator (Backend)

**Files:**
- Create: `daemon/export.py`
- Create: `tests/test_cja_export.py`
- Create: `tests/test_flat_fee.py`

- [ ] **Step 1: Write failing tests `tests/test_cja_export.py`**

```python
import csv
import io
from datetime import date
from daemon.export import generate_cja_csv, generate_practice_csv
from daemon.models import Entry, CJACategory


def make_entry(matter_id, entry_date, hours, narrative, category=CJACategory.RESEARCH, entry_id=1):
    return Entry(
        id=entry_id,
        matter_id=matter_id,
        date=entry_date,
        narrative=narrative,
        cja_category=category,
        hours=hours,
    )


def test_cja_csv_correct_columns():
    entries = [
        make_entry(1, date(2026, 4, 1), 2.5, "Reviewed discovery materials", CJACategory.RESEARCH),
        make_entry(1, date(2026, 4, 2), 1.0, "Client meeting at jail", CJACategory.INTERVIEW, entry_id=2),
    ]
    matter_info = {"case_number": "1:26-cr-00123", "defendant": "Smith, John"}
    output = io.StringIO()
    generate_cja_csv(entries, matter_info, output)
    output.seek(0)
    rows = list(csv.DictReader(output))
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-04-01"
    assert rows[0]["case_no"] == "1:26-cr-00123"
    assert rows[0]["defendant"] == "Smith, John"
    assert rows[0]["category"] == "D"
    assert rows[0]["description"] == "Reviewed discovery materials"
    assert float(rows[0]["hours"]) == 2.5


def test_cja_csv_missing_category_defaults_to_F():
    entries = [make_entry(1, date(2026, 4, 1), 1.0, "Misc work", category=None)]
    matter_info = {"case_number": "1:26-cr-00123", "defendant": "Smith, John"}
    output = io.StringIO()
    generate_cja_csv(entries, matter_info, output)
    output.seek(0)
    rows = list(csv.DictReader(output))
    assert rows[0]["category"] == "F"
```

- [ ] **Step 2: Write failing tests `tests/test_flat_fee.py`**

```python
from daemon.export import compute_flat_fee_analytics
from daemon.models import Matter, MatterType, MatterStatus, ClientPerson, BillingInfo


def make_flat_matter(flat_fee, underwater_threshold=150.0):
    return Matter(
        id=1,
        folder_path="/home/user/OpenCases/Smith, John",
        matter_type=MatterType.RETAINED_FLAT,
        status=MatterStatus.ACTIVE,
        client=ClientPerson(last="Smith", first="John"),
        billing=BillingInfo(flat_fee=flat_fee, underwater_threshold=underwater_threshold),
    )


def test_effective_rate():
    matter = make_flat_matter(5000.0)
    result = compute_flat_fee_analytics(matter, total_hours=10.0)
    assert result["effective_rate"] == 500.0
    assert result["is_underwater"] is False


def test_underwater_detection():
    matter = make_flat_matter(1500.0, underwater_threshold=200.0)
    result = compute_flat_fee_analytics(matter, total_hours=20.0)
    assert result["effective_rate"] == 75.0
    assert result["is_underwater"] is True


def test_zero_hours_no_crash():
    matter = make_flat_matter(5000.0)
    result = compute_flat_fee_analytics(matter, total_hours=0.0)
    assert result["effective_rate"] is None
    assert result["is_underwater"] is False
```

- [ ] **Step 3: Run to verify failures**

```bash
pytest tests/test_cja_export.py tests/test_flat_fee.py -v
```

Expected: `ImportError`.

- [ ] **Step 4: Write `daemon/export.py`**

```python
from __future__ import annotations
import csv
from io import StringIO
from typing import Optional, TextIO
from daemon.models import Entry, CJACategory, Matter


def generate_cja_csv(entries: list[Entry], matter_info: dict, output: TextIO) -> None:
    """Write CJA-20 formatted CSV to output stream."""
    writer = csv.DictWriter(
        output,
        fieldnames=["date", "case_no", "defendant", "category", "description", "hours"]
    )
    writer.writeheader()
    for entry in sorted(entries, key=lambda e: e.date):
        writer.writerow({
            "date": entry.date.isoformat(),
            "case_no": matter_info.get("case_number", ""),
            "defendant": matter_info.get("defendant", ""),
            "category": (entry.cja_category.value if entry.cja_category else CJACategory.OTHER.value),
            "description": entry.narrative,
            "hours": f"{entry.hours:.2f}",
        })


def generate_practice_csv(rows: list[dict], output: TextIO) -> None:
    """Write practice-wide time export CSV."""
    if not rows:
        return
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)


def compute_flat_fee_analytics(matter: Matter, total_hours: float) -> dict:
    flat_fee = matter.billing.flat_fee or 0.0
    threshold = matter.billing.underwater_threshold or 0.0
    if total_hours <= 0:
        return {"flat_fee": flat_fee, "total_hours": 0.0, "effective_rate": None, "is_underwater": False}
    effective_rate = flat_fee / total_hours
    is_underwater = threshold > 0 and effective_rate < threshold
    return {
        "flat_fee": flat_fee,
        "total_hours": total_hours,
        "effective_rate": round(effective_rate, 2),
        "is_underwater": is_underwater,
        "underwater_threshold": threshold,
    }
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_cja_export.py tests/test_flat_fee.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add daemon/export.py tests/test_cja_export.py tests/test_flat_fee.py
git commit -m "feat: CJA CSV export and flat-fee analytics calculator"
```

---

## Task 13: Ollama Narrative Suggestion Client

**Files:**
- Create: `review-app/ollama.py`

- [ ] **Step 1: Write `review-app/ollama.py`**

```python
from __future__ import annotations
import json
import urllib.request
import urllib.error
from typing import Optional


class OllamaClient:
    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "qwen2.5:3b"):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=2)
            return True
        except (urllib.error.URLError, OSError):
            return False

    def suggest_narrative(
        self,
        matter_name: str,
        matter_type: str,
        activity_trail: list[dict],
        max_tokens: int = 60,
    ) -> Optional[str]:
        """Return a one-line narrative suggestion or None on failure."""
        activity_summary = "; ".join(
            f"{item.get('app_id', '')} — {item.get('window_title', '')}"
            for item in activity_trail[:10]
        )
        prompt = (
            f"You are a legal billing assistant. Write ONE short billing narrative (max 15 words) "
            f"for work on a {matter_type} matter for {matter_name}.\n"
            f"Activity: {activity_summary}\n"
            f"Narrative:"
        )
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3},
        }).encode()
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                return result.get("response", "").strip()
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None
```

- [ ] **Step 2: Verify import**

```bash
python -c "from review_app.ollama import OllamaClient; print(OllamaClient().is_available())"
```

Expected: `True` if Ollama is running, `False` otherwise. No crash either way.

- [ ] **Step 3: Commit**

```bash
git add review-app/ollama.py
git commit -m "feat: Ollama HTTP client for AI narrative suggestions"
```

---

## Task 14: Review App — Skeleton + Today View

**Files:**
- Create: `review-app/main.py`
- Create: `review-app/window.py`
- Create: `review-app/views/today.py`
- Create: `review-app/widgets/entry_row.py`

- [ ] **Step 1: Write `review-app/main.py`**

```python
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio
from review_app.window import UbuntuLawyersWindow


class UbuntuLawyersApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.northcoastlegal.UbuntuLawyers.Review")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = UbuntuLawyersWindow(application=app)
        win.present()


def main():
    app = UbuntuLawyersApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `review-app/window.py`**

```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from daemon.db import get_connection
from daemon.config import load_config
from daemon.matter_indexer import MatterIndex
from pathlib import Path
from review_app.views.today import TodayView
from review_app.views.analytics import AnalyticsView
from review_app.views.export import ExportView


class UbuntuLawyersWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Ubuntu Lawyers — Time Review")
        self.set_default_size(900, 650)

        self._config = load_config()
        self._db = get_connection()
        self._index = MatterIndex(opencases_path=Path(self._config.opencases_path))
        self._index.scan()

        self._build_ui()

    def _build_ui(self):
        split = Adw.NavigationSplitView()
        self.set_content(split)

        # Sidebar
        sidebar_page = Adw.NavigationPage(title="Ubuntu Lawyers")
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        sidebar_box.append(header)

        list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        list_box.set_css_classes(["navigation-sidebar"])
        for label in ["Today", "Analytics", "Export"]:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=label, xalign=0, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8))
            list_box.append(row)
        list_box.connect("row-selected", self._on_nav_selected)
        sidebar_box.append(list_box)
        sidebar_page.set_child(sidebar_box)
        split.set_sidebar(sidebar_page)

        # Content area
        self._content_page = Adw.NavigationPage(title="Today")
        self._stack = Gtk.Stack()
        self._stack.add_named(TodayView(db=self._db, index=self._index, config=self._config), "today")
        self._stack.add_named(AnalyticsView(db=self._db, index=self._index), "analytics")
        self._stack.add_named(ExportView(db=self._db, index=self._index), "export")
        self._content_page.set_child(self._stack)
        split.set_content(self._content_page)

        list_box.select_row(list_box.get_row_at_index(0))

    def _on_nav_selected(self, list_box, row):
        if row is None:
            return
        pages = ["today", "analytics", "export"]
        self._stack.set_visible_child_name(pages[row.get_index()])
```

- [ ] **Step 3: Write `review-app/views/today.py`**

```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from datetime import date
from daemon.db import get_connection
from daemon.models import CJACategory, MatterType
from review_app.widgets.entry_row import EntryRow


class TodayView(Gtk.Box):
    def __init__(self, db, index, config):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._db = db
        self._index = index
        self._config = config

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Today", subtitle=date.today().strftime("%A, %B %-d")))
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda _: self._load_entries())
        header.pack_end(refresh_btn)
        self.append(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._list.set_css_classes(["boxed-list"])
        self._list.set_margin_top(12)
        self._list.set_margin_bottom(12)
        self._list.set_margin_start(12)
        self._list.set_margin_end(12)
        scroll.set_child(self._list)
        self.append(scroll)

        self._load_entries()

    def _load_entries(self):
        while self._list.get_first_child():
            self._list.remove(self._list.get_first_child())

        today = date.today().isoformat()
        rows = self._db.execute(
            "SELECT e.*, m.last_name, m.first_name, m.organization, m.matter_type "
            "FROM entries e JOIN matters m ON e.matter_id = m.id WHERE e.date=? ORDER BY m.last_name",
            (today,)
        ).fetchall()

        if not rows:
            placeholder = Adw.ActionRow(title="No entries for today", subtitle="Time capture will populate entries automatically")
            self._list.append(placeholder)
            return

        for row in rows:
            entry_row = EntryRow(row=row, db=self._db, on_save=self._load_entries)
            self._list.append(entry_row)
```

- [ ] **Step 4: Write `review-app/widgets/entry_row.py`**

```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from daemon.models import CJACategory, MatterType
from review_app.ollama import OllamaClient

CJA_CATEGORIES = [
    ("A — In-court", "A"),
    ("B — Interview/Conference", "B"),
    ("C — Investigation", "C"),
    ("D — Research & Brief Writing", "D"),
    ("E — Travel", "E"),
    ("F — Other", "F"),
]

TEMPLATES = {
    "federal_cja": [
        "Reviewed discovery materials",
        "Client meeting",
        "Court appearance",
        "Legal research",
        "Motion drafting",
        "Record review",
    ],
    "retained_hourly": ["Client consultation", "Drafted correspondence", "Legal research", "Court appearance"],
    "retained_flat": ["Case preparation", "Client meeting", "Filed motion", "Court appearance"],
    "program_admin": ["Panel coordination", "County correspondence", "Attorney placement", "Administrative review"],
}


class EntryRow(Adw.ExpanderRow):
    def __init__(self, row, db, on_save):
        name = row["organization"] or f"{row['last_name']}, {row['first_name']}"
        hours = row["hours"]
        super().__init__(
            title=name,
            subtitle=f"{hours:.2f} h",
        )
        self._row = row
        self._db = db
        self._on_save = on_save
        self._ollama = OllamaClient()
        self._build()

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)

        # Narrative
        self._narrative = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, height_request=60)
        buf = self._narrative.get_buffer()
        buf.set_text(self._row["narrative"] or "")
        frame = Gtk.Frame()
        frame.set_child(self._narrative)
        box.append(frame)

        # Template + Ollama row
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tmpl_btn = Gtk.MenuButton(label="Templates")
        tmpl_menu = Gtk.PopoverMenu.new_from_model(self._build_template_menu())
        tmpl_btn.set_popover(tmpl_menu)
        btn_row.append(tmpl_btn)

        if self._ollama.is_available():
            suggest_btn = Gtk.Button(label="Suggest (AI)")
            suggest_btn.connect("clicked", self._on_suggest)
            btn_row.append(suggest_btn)

        box.append(btn_row)

        # CJA category (only for federal_cja)
        if self._row["matter_type"] == "federal_cja":
            cja_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            cja_box.append(Gtk.Label(label="CJA Category:", xalign=0))
            self._cja_combo = Gtk.DropDown()
            strings = Gtk.StringList()
            for label, _ in CJA_CATEGORIES:
                strings.append(label)
            self._cja_combo.set_model(strings)
            current = self._row["cja_category"] or "F"
            idx = next((i for i, (_, v) in enumerate(CJA_CATEGORIES) if v == current), 5)
            self._cja_combo.set_selected(idx)
            cja_box.append(self._cja_combo)
            box.append(cja_box)
        else:
            self._cja_combo = None

        # Save button
        save_btn = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save_btn.connect("clicked", self._on_save_clicked)
        box.append(save_btn)

        self.add_row(Gtk.ListBoxRow(child=box, activatable=False))

    def _build_template_menu(self):
        menu = Gtk.StringList()
        templates = TEMPLATES.get(self._row["matter_type"], [])
        for t in templates:
            menu.append(t)
        return menu

    def _on_suggest(self, _btn):
        trail = self._db.execute(
            "SELECT app_id, window_title FROM activity_trail at "
            "JOIN sessions s ON at.session_id=s.id WHERE s.matter_id=? LIMIT 10",
            (self._row["matter_id"],)
        ).fetchall()
        suggestion = self._ollama.suggest_narrative(
            matter_name=self._row["last_name"] or self._row["organization"],
            matter_type=self._row["matter_type"],
            activity_trail=[dict(r) for r in trail],
        )
        if suggestion:
            self._narrative.get_buffer().set_text(suggestion)

    def _on_save_clicked(self, _btn):
        buf = self._narrative.get_buffer()
        narrative = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        cja_cat = None
        if self._cja_combo is not None:
            idx = self._cja_combo.get_selected()
            cja_cat = CJA_CATEGORIES[idx][1]
        self._db.execute(
            "UPDATE entries SET narrative=?, cja_category=? WHERE id=?",
            (narrative, cja_cat, self._row["id"])
        )
        self._db.commit()
        if self._on_save:
            self._on_save()
```

- [ ] **Step 5: Create stub views to avoid import errors**

```bash
cat > review-app/views/analytics.py << 'EOF'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class AnalyticsView(Gtk.Box):
    def __init__(self, db, index):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Analytics"))
        self.append(header)
        self.append(Gtk.Label(label="Replaced in Task 15.", vexpand=True))
EOF

cat > review-app/views/export.py << 'EOF'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class ExportView(Gtk.Box):
    def __init__(self, db, index):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Export"))
        self.append(header)
        self.append(Gtk.Label(label="Replaced in Task 15.", vexpand=True))
EOF
```

- [ ] **Step 6: Manual test — launch review app**

```bash
python review-app/main.py
```

Expected: Window opens with sidebar nav (Today / Analytics / Export). Today view shows entries or the "no entries" placeholder.

- [ ] **Step 7: Commit**

```bash
git add review-app/
git commit -m "feat: review app skeleton with today view, entry rows, narrative editing, and Ollama suggestion"
```

---

## Task 15: Analytics View + Export View

**Files:**
- Modify: `review-app/views/analytics.py`
- Modify: `review-app/views/export.py`

- [ ] **Step 1: Replace `review-app/views/analytics.py`**

```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from daemon.export import compute_flat_fee_analytics
from daemon.models import MatterType


class AnalyticsView(Gtk.Box):
    def __init__(self, db, index):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._db = db
        self._index = index

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Flat-Fee Analytics"))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.connect("clicked", lambda _: self._load())
        header.pack_end(refresh)
        self.append(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self._list.set_margin_top(12)
        self._list.set_margin_bottom(12)
        self._list.set_margin_start(12)
        self._list.set_margin_end(12)
        scroll.set_child(self._list)
        self.append(scroll)
        self._load()

    def _load(self):
        while self._list.get_first_child():
            self._list.remove(self._list.get_first_child())

        flat_matters = [
            m for m in self._index.all_active()
            if m.matter_type == MatterType.RETAINED_FLAT and m.billing.flat_fee
        ]

        if not flat_matters:
            self._list.append(Adw.ActionRow(title="No flat-fee matters found"))
            return

        for matter in sorted(flat_matters, key=lambda m: m.display_name):
            row_data = self._db.execute(
                "SELECT COALESCE(SUM(hours), 0) as total FROM entries WHERE matter_id=?",
                (matter.id,)
            ).fetchone()
            total_hours = row_data["total"] if row_data else 0.0
            analytics = compute_flat_fee_analytics(matter, total_hours)

            effective = analytics["effective_rate"]
            rate_text = f"${effective:.2f}/hr" if effective is not None else "No time logged"
            subtitle = f"${analytics['flat_fee']:,.2f} flat fee · {total_hours:.1f} h logged · {rate_text}"

            row = Adw.ActionRow(title=matter.display_name, subtitle=subtitle)
            if analytics["is_underwater"]:
                row.set_css_classes(["error"])
                row.add_suffix(Gtk.Label(label="⚠ Underwater", css_classes=["error"]))
            self._list.append(row)
```

- [ ] **Step 2: Replace `review-app/views/export.py`**

```python
import csv
import io
import os
import subprocess
from datetime import date
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
from daemon.export import generate_cja_csv
from daemon.models import MatterType


class ExportView(Gtk.Box):
    def __init__(self, db, index):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._db = db
        self._index = index

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Export"))
        self.append(header)

        prefs = Adw.PreferencesGroup(title="CJA-20 Export", margin_top=16,
                                     margin_start=12, margin_end=12)

        # Matter picker for CJA export
        self._cja_matter_combo = Gtk.DropDown()
        cja_matters = [m for m in index.all_active() if m.matter_type == MatterType.FEDERAL_CJA]
        strings = Gtk.StringList()
        self._cja_matter_list = cja_matters
        for m in cja_matters:
            strings.append(m.display_name)
        self._cja_matter_combo.set_model(strings)
        matter_row = Adw.ActionRow(title="Matter")
        matter_row.add_suffix(self._cja_matter_combo)
        prefs.add(matter_row)

        # Month picker
        self._month_entry = Gtk.Entry(text=date.today().strftime("%Y-%m"), placeholder_text="YYYY-MM")
        month_row = Adw.ActionRow(title="Month")
        month_row.add_suffix(self._month_entry)
        prefs.add(month_row)

        export_cja_btn = Gtk.Button(label="Export CJA CSV", css_classes=["suggested-action"],
                                    margin_top=8, margin_start=12, margin_end=12)
        export_cja_btn.connect("clicked", self._on_export_cja)

        hourly_group = Adw.PreferencesGroup(title="Hourly Invoice", margin_top=16,
                                            margin_start=12, margin_end=12)
        hourly_matters = [m for m in index.all_active() if m.matter_type == MatterType.RETAINED_HOURLY]
        hourly_strings = Gtk.StringList()
        self._hourly_matter_list = hourly_matters
        for m in hourly_matters:
            hourly_strings.append(m.display_name)
        self._hourly_matter_combo = Gtk.DropDown()
        self._hourly_matter_combo.set_model(hourly_strings)
        hourly_row = Adw.ActionRow(title="Matter")
        hourly_row.add_suffix(self._hourly_matter_combo)
        hourly_group.add(hourly_row)
        export_inv_btn = Gtk.Button(label="Generate Invoice PDF", margin_top=8,
                                    margin_start=12, margin_end=12)
        export_inv_btn.connect("clicked", self._on_export_invoice)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.append(prefs)
        inner.append(export_cja_btn)
        inner.append(hourly_group)
        inner.append(export_inv_btn)
        scroll.set_child(inner)
        self.append(scroll)

        self._toast_overlay = Adw.ToastOverlay()
        self.append(self._toast_overlay)

    def _on_export_cja(self, _btn):
        idx = self._cja_matter_combo.get_selected()
        if not self._cja_matter_list or idx >= len(self._cja_matter_list):
            return
        matter = self._cja_matter_list[idx]
        month = self._month_entry.get_text().strip()
        rows = self._db.execute(
            "SELECT * FROM entries WHERE matter_id=? AND date LIKE ?",
            (matter.id, f"{month}%")
        ).fetchall()
        from daemon.models import Entry, CJACategory
        from datetime import date as ddate
        entries = []
        for r in rows:
            entries.append(Entry(
                id=r["id"], matter_id=r["matter_id"],
                date=ddate.fromisoformat(r["date"]),
                narrative=r["narrative"] or "",
                cja_category=CJACategory(r["cja_category"]) if r["cja_category"] else None,
                hours=r["hours"],
            ))
        matter_info = {
            "case_number": matter.court.case_number if matter.court else "",
            "defendant": matter.display_name,
        }
        out_dir = Path(matter.folder_path) / "billing"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"cja-{month}.csv"
        with open(out_path, "w", newline="") as f:
            generate_cja_csv(entries, matter_info, f)
        self._show_toast(f"Saved: {out_path}")

    def _on_export_invoice(self, _btn):
        idx = self._hourly_matter_combo.get_selected()
        if not self._hourly_matter_list or idx >= len(self._hourly_matter_list):
            return
        matter = self._hourly_matter_list[idx]
        month = self._month_entry.get_text().strip()
        rows = self._db.execute(
            "SELECT * FROM entries WHERE matter_id=? AND date LIKE ? ORDER BY date",
            (matter.id, f"{month}%")
        ).fetchall()
        from daemon.models import Entry
        from datetime import date as ddate
        entries = [
            Entry(id=r["id"], matter_id=r["matter_id"], date=ddate.fromisoformat(r["date"]),
                  narrative=r["narrative"] or "", cja_category=None, hours=r["hours"])
            for r in rows
        ]
        out_dir = Path(matter.folder_path) / "billing"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"invoice-{month}.html"
        total = sum(e.hours for e in entries)
        rate = matter.billing.hourly_rate or 0.0
        lines = "\n".join(
            f"<tr><td>{e.date}</td><td>{e.narrative}</td><td>{e.hours:.2f}</td>"
            f"<td>${e.hours * rate:,.2f}</td></tr>"
            for e in entries
        )
        html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>body{{font-family:sans-serif;margin:40px}}table{{width:100%;border-collapse:collapse}}
th,td{{border:1px solid #ccc;padding:8px;text-align:left}}th{{background:#f5f5f5}}</style></head>
<body><h2>Invoice — {matter.display_name}</h2><p>Period: {month}</p>
<table><tr><th>Date</th><th>Description</th><th>Hours</th><th>Amount</th></tr>
{lines}
<tr><td colspan='2'><strong>Total</strong></td><td><strong>{total:.2f}</strong></td>
<td><strong>${total * rate:,.2f}</strong></td></tr></table>
<p>Rate: ${rate:.2f}/hr</p></body></html>"""
        out_path.write_text(html)
        # Convert to PDF using LibreOffice headless
        import subprocess
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(out_path)],
            capture_output=True, timeout=30
        )
        pdf_path = out_dir / f"invoice-{month}.pdf"
        if result.returncode == 0 and pdf_path.exists():
            self._show_toast(f"Saved: {pdf_path}")
        else:
            self._show_toast(f"HTML saved (LibreOffice PDF conversion failed): {out_path}")

    def _on_export_practice_csv(self, _btn):
        """Export all matters × all entries to ~/Documents/time-exports/YYYY-MM.csv."""
        from daemon.export import generate_practice_csv
        import io
        month = self._month_entry.get_text().strip()
        rows = self._db.execute(
            """SELECT e.date, m.last_name, m.first_name, m.organization, m.matter_type,
                      e.hours, e.narrative, e.cja_category
               FROM entries e JOIN matters m ON e.matter_id = m.id
               WHERE e.date LIKE ? ORDER BY e.date, m.last_name""",
            (f"{month}%",)
        ).fetchall()
        out_dir = Path.home() / "Documents" / "time-exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{month}-all-matters.csv"
        with open(out_path, "w", newline="") as f:
            generate_practice_csv([dict(r) for r in rows], f)
        self._show_toast(f"Saved: {out_path}")

    def _show_toast(self, message: str):
        toast = Adw.Toast(title=message, timeout=4)
        self._toast_overlay.add_toast(toast)
```

- [ ] **Step 3: Add practice-wide export button to `ExportView.__init__`**

After `export_inv_btn`, add:

```python
practice_group = Adw.PreferencesGroup(title="Practice-Wide Export", margin_top=16,
                                      margin_start=12, margin_end=12)
inner.append(practice_group)
export_practice_btn = Gtk.Button(label="Export All Matters CSV", margin_top=8,
                                 margin_start=12, margin_end=12)
export_practice_btn.connect("clicked", self._on_export_practice_csv)
inner.append(export_practice_btn)
```

(This button shares the `_month_entry` field already in the view.)

- [ ] **Step 5: Manual test**

```bash
python review-app/main.py
```

- Navigate to Analytics — should show flat-fee matters with effective rates and underwater flags.
- Navigate to Export — CJA, hourly invoice, and practice-wide buttons all visible.
- Export a CJA CSV; verify file appears in `~/OpenCases/<matter>/billing/cja-YYYY-MM.csv`.
- Export practice-wide CSV; verify file appears in `~/Documents/time-exports/`.
- Export hourly invoice; verify HTML and PDF appear in `~/OpenCases/<matter>/billing/`.

- [ ] **Step 6: Commit**

```bash
git add review-app/views/analytics.py review-app/views/export.py
git commit -m "feat: analytics view, CJA/invoice/practice-wide export UI with LibreOffice PDF"
```

---

## Task 16: rclone Mount Service + Install Script

**Files:**
- Create: `rclone-opencases.service`
- Create: `install.sh`
- Create: `docs/test-matrix.md`

- [ ] **Step 1: Write `rclone-opencases.service`**

```ini
[Unit]
Description=rclone mount: Google Drive OpenCases
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStartPre=/bin/mkdir -p %h/OpenCases
ExecStart=/usr/bin/rclone mount gdrive:"Open Cases" %h/OpenCases \
    --vfs-cache-mode full \
    --vfs-cache-max-size 20G \
    --vfs-cache-max-age 72h \
    --dir-cache-time 30m \
    --log-level INFO \
    --poll-interval 30s
ExecStop=/bin/fusermount -u %h/OpenCases
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Write `install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$HOME/.local/lib/ubuntu-lawyers"
BIN_DIR="$HOME/.local/bin"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/ubuntu-lawyers@northcoastlegal.com"
SYSTEMD_DIR="$HOME/.config/systemd/user"
NATIVE_HOST_DIR="$LIB_DIR/native-host"

echo "==> Installing Ubuntu Lawyers Time Tracker"

# Python package
echo "==> Installing Python package"
pip install -e "$REPO_DIR" --quiet

# Daemon entry point
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/ubuntu-lawyers-daemon" << EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "$REPO_DIR")
from daemon.__main__ import main
main()
EOF
chmod +x "$BIN_DIR/ubuntu-lawyers-daemon"

# Review app entry point
cat > "$BIN_DIR/ubuntu-lawyers-review" << EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "$REPO_DIR")
from review_app.main import main
main()
EOF
chmod +x "$BIN_DIR/ubuntu-lawyers-review"

# GNOME Shell extension
echo "==> Installing GNOME Shell extension"
mkdir -p "$EXT_DIR"
cp -r "$REPO_DIR/extension/"* "$EXT_DIR/"

# Native messaging host
echo "==> Installing native messaging host"
mkdir -p "$NATIVE_HOST_DIR"
cp "$REPO_DIR/browser-extension/native-host/host.py" "$NATIVE_HOST_DIR/"
chmod +x "$NATIVE_HOST_DIR/host.py"

CHROME_EXT_ID="${UBUNTU_LAWYERS_CHROME_ID:-PLACEHOLDER_CHROME_ID}"
FF_UUID="${UBUNTU_LAWYERS_FF_UUID:-PLACEHOLDER_FIREFOX_UUID}"

HOST_JSON="$NATIVE_HOST_DIR/com.northcoastlegal.ubuntu_lawyers.json"
sed \
  -e "s|PLACEHOLDER|$HOME|g" \
  -e "s|PLACEHOLDER_CHROME_ID|$CHROME_EXT_ID|g" \
  -e "s|PLACEHOLDER_FIREFOX_UUID|$FF_UUID|g" \
  "$REPO_DIR/browser-extension/native-host/com.northcoastlegal.ubuntu_lawyers.json" \
  > "$HOST_JSON"

mkdir -p "$HOME/.mozilla/native-messaging-hosts"
cp "$HOST_JSON" "$HOME/.mozilla/native-messaging-hosts/"
mkdir -p "$HOME/.config/google-chrome/NativeMessagingHosts"
cp "$HOST_JSON" "$HOME/.config/google-chrome/NativeMessagingHosts/"

# systemd units
echo "==> Installing systemd user units"
mkdir -p "$SYSTEMD_DIR"
cp "$REPO_DIR/ubuntu-lawyers-daemon.service" "$SYSTEMD_DIR/"
cp "$REPO_DIR/rclone-opencases.service" "$SYSTEMD_DIR/"
systemctl --user daemon-reload

echo ""
echo "==> Done. Next steps:"
echo "  1. Set up rclone remote named 'gdrive': rclone config"
echo "  2. Enable rclone mount: systemctl --user enable --now rclone-opencases"
echo "  3. Enable daemon: systemctl --user enable --now ubuntu-lawyers-daemon"
echo "  4. Enable GNOME extension: gnome-extensions enable ubuntu-lawyers@northcoastlegal.com"
echo "  5. Load browser extension in Firefox/Chrome from: $REPO_DIR/browser-extension/"
echo "  6. Launch review app: ubuntu-lawyers-review"
```

- [ ] **Step 3: Make install.sh executable**

```bash
chmod +x install.sh
```

- [ ] **Step 4: Write `docs/test-matrix.md`**

```markdown
# Manual Test Matrix

Run this checklist after each significant change to the capture layer.

## Pre-conditions
- rclone mount active: `ls ~/OpenCases/` shows at least 2 matter folders
- Daemon running: `systemctl --user status ubuntu-lawyers-daemon`
- GNOME extension enabled: `gnome-extensions list --enabled | grep ubuntu-lawyers`
- Browser extension loaded in Firefox and Chrome

## Test Cases

### TC-1: Three-matter switch
1. Open a LibreOffice document from `~/OpenCases/Smith, John/`
2. Verify top-bar shows "Smith, John"
3. Switch focus to a doc from `~/OpenCases/Jones, Mary/`
4. Verify top-bar updates to "Jones, Mary"
5. Open Review App → Today view; verify two separate time entries exist

**Pass criteria:** Both entries show ≥ 1 minute, correct matter attribution.

### TC-2: Idle timeout and resume
1. Start working on a matter (confirm in top-bar)
2. Leave keyboard/mouse idle for > 5 minutes
3. Verify top-bar indicator dims or changes (paused state)
4. Move mouse / press a key
5. Verify timer resumes

**Pass criteria:** Review App shows pause gap in session trail; total hours exclude idle time.

### TC-3: Browser tab flip
1. In Firefox, navigate to Google Docs with "Smith" in document title
2. Verify matter attribution switches to Smith
3. Open a new tab (about:newtab)
4. Verify top-bar shows no confident match (amber) or retains last matter

**Pass criteria:** Matter correctly inferred from Google Docs tab title; no crash on about:newtab.

### TC-4: Zoom call nudge
1. Open Zoom and join a meeting
2. Verify top-bar shows amber nudge: "Still on [last matter]?"
3. Click to confirm or switch matter

**Pass criteria:** Manual confirmation records correct matter for Zoom duration.

### TC-5: .matter.yaml live re-index
1. Create a new folder `~/OpenCases/Test, Client/`
2. Within 60 seconds, verify matter appears in Review App matter list
3. Add `.matter.yaml` with aliases
4. Verify aliases take effect on next match event

**Pass criteria:** New matter indexed without daemon restart.

### TC-6: Daemon restart recovery
1. Start a timer session (working on a matter)
2. Kill the daemon: `systemctl --user stop ubuntu-lawyers-daemon`
3. Restart: `systemctl --user start ubuntu-lawyers-daemon`
4. Open Review App; verify orphaned session is marked "system interruption"

**Pass criteria:** No data loss; orphaned session visible in today's entry trail.
```

- [ ] **Step 5: Commit**

```bash
git add install.sh rclone-opencases.service docs/test-matrix.md
git commit -m "feat: install script, rclone mount service, and manual test matrix"
```

---

## Task 17: Full Test Suite + Final Wiring

**Files:**
- Modify: `tests/conftest.py` (add matter fixtures)
- Run full suite

- [ ] **Step 1: Update `tests/conftest.py` with matter fixtures**

```python
import pytest
import sqlite3
from pathlib import Path
from daemon.db import init_schema
from daemon.models import (
    Matter, MatterType, MatterStatus, ClientPerson, ClientOrg, BillingInfo, CourtInfo
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def federal_cja_matter(db):
    db.execute(
        "INSERT INTO matters (id, folder_path, last_name, first_name, matter_type, status) VALUES (?,?,?,?,?,?)",
        (1, "/home/user/OpenCases/Smith, John", "Smith", "John", "federal_cja", "active")
    )
    db.commit()
    return Matter(
        id=1,
        folder_path="/home/user/OpenCases/Smith, John",
        matter_type=MatterType.FEDERAL_CJA,
        status=MatterStatus.ACTIVE,
        client=ClientPerson(last="Smith", first="John"),
        billing=BillingInfo(cja_rate=175.0),
        court=CourtInfo(name="U.S. District Court, W.D. Mich.", case_number="1:26-cr-00123"),
        aliases=["Smith", "1:26-cr-00123"],
    )


@pytest.fixture
def flat_fee_matter(db):
    db.execute(
        "INSERT INTO matters (id, folder_path, last_name, first_name, matter_type, status) VALUES (?,?,?,?,?,?)",
        (2, "/home/user/OpenCases/Jones, Mary", "Jones", "Mary", "retained_flat", "active")
    )
    db.commit()
    return Matter(
        id=2,
        folder_path="/home/user/OpenCases/Jones, Mary",
        matter_type=MatterType.RETAINED_FLAT,
        status=MatterStatus.ACTIVE,
        client=ClientPerson(last="Jones", first="Mary"),
        billing=BillingInfo(flat_fee=5000.0, underwater_threshold=150.0),
        aliases=["Jones"],
    )
```

- [ ] **Step 2: Run full test suite**

```bash
pytest -v --tb=short
```

Expected: all tests pass. Fix any failures before proceeding.

- [ ] **Step 3: Run with coverage**

```bash
pytest --cov=daemon --cov-report=term-missing
```

Expected: ≥ 80% coverage on `daemon/matter_matcher.py`, `daemon/timer.py`, `daemon/export.py`.

- [ ] **Step 4: Final commit**

```bash
git add tests/conftest.py
git commit -m "test: full test suite with shared fixtures, all tests passing"
```

---

## Summary: Build Order

```
Task 1  → scaffold
Task 2  → models
Task 3  → db
Task 4  → config
Task 5  → matter yaml parser
Task 6  → matter indexer (inotify)
Task 7  → matter matcher          ← core inference logic
Task 8  → timer state machine     ← core time logic
Task 9  → dbus service + daemon entry
Task 10 → GNOME shell extension
Task 11 → browser extension + native host
Task 12 → CJA export + flat-fee calculator
Task 13 → Ollama client
Task 14 → review app skeleton + today view
Task 15 → analytics + export views
Task 16 → rclone service + install script
Task 17 → full test suite
```

Each task produces working, committable code. Tasks 1–9 can be verified without a running GNOME session (pure Python + tests). Tasks 10–11 require a GNOME Wayland session. Tasks 14–15 require GTK4/libadwaita.
