# Attorney Time Tracker — Design Spec

**Date:** 2026-04-16
**Project:** Ubuntu_Lawyers (sub-project 1 of a larger suite)
**Status:** Approved design, ready for implementation planning

## 1. Overview

A desktop-integrated time and activity capture tool for attorneys running Ubuntu/GNOME on Wayland. The system watches what the user is working on — which documents, which browser tabs, which apps — and attributes that time to the correct legal matter, producing structured output for federal CJA reimbursement, hourly invoicing, and flat-fee profitability analysis.

The tool is the first of an intended suite of Linux-native tools for legal practice, starting here because time capture is the highest-leverage pain point for solo and small-firm attorneys.

## 2. Goals & Non-Goals

**Goals**

- Passive capture of working time with minimal friction, defensible for CJA-20 reimbursement.
- Per-matter flat-fee profitability analytics (effective hourly rate, "underwater" alerts).
- Hourly invoice generation for retained hourly matters.
- Google Calendar awareness (V2) to auto-attribute scheduled events.
- Local-only data by default; no telemetry, no cloud analytics.
- Works with cloud-primary matter storage via `rclone mount` of Google Drive.

**Non-goals (V1)**

- Multi-user / multi-attorney installations.
- Cross-device sync.
- Direct e-filing or eVoucher submission automation (CSV export only).
- KDE / XFCE / macOS / Windows support.
- Trust accounting or payment processing.
- Native Google Drive client (we use `rclone mount` as a prerequisite; building a Drive client is a separate project).

## 3. Users & Context

Primary user: solo or small-firm attorney on Ubuntu with GNOME/Wayland, using LibreOffice, Firefox/Chrome, Evince/Okular, Zoom, Google Meet (in browser), and occasionally a terminal. Mix of federal CJA panel work and state retained work (hourly and flat-fee).

Matter storage convention: `Open Cases / Lastname, Firstname / ...`, primarily on Google Drive, accessed via `rclone mount` so it appears as a real filesystem path (e.g. `~/OpenCases/Smith, John/`).

## 4. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Desktop (Wayland)                      │
│                                                             │
│  ┌────────────────────┐      ┌─────────────────────────┐    │
│  │ GNOME Shell        │      │ Browser Extension       │    │
│  │ Extension          │      │ (Firefox + Chrome)      │    │
│  │ • focus events     │      │ • active tab title+URL  │    │
│  │ • top-bar indicator│      │                         │    │
│  └────────┬───────────┘      └────────────┬────────────┘    │
│           │    DBus / Unix socket         │                 │
│           └──────────────┬─────────────────┘                │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │ Daemon (Python)       │  ←── systemd --user  │
│              │ • event router        │                      │
│              │ • matter matcher      │                      │
│              │ • timer state machine │                      │
│              │ • idle detector       │                      │
│              └──────┬───────────┬────┘                      │
│                     │           │                           │
│              ┌──────▼──┐    ┌───▼────────────────┐          │
│              │ SQLite  │    │ Matter Indexer     │          │
│              │ time.db │    │ scans OpenCases/   │          │
│              └─────────┘    │ (rclone mount)     │          │
│                             └────────────────────┘          │
│                                                             │
│  ┌─────────────────────────────────────────────┐            │
│  │ Review App (GTK4 / libadwaita)              │            │
│  │ • daily timeline + narrative editing        │            │
│  │ • flat-fee analytics                        │            │
│  │ • CJA/invoice export                        │            │
│  └─────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

**Key properties**

- Three capture sources (shell extension, browser extension, filesystem indexer) feed one Python daemon. Capture components stay dumb; the daemon owns all matching logic and state.
- Daemon runs as a `systemd --user` service. Auto-starts on login, survives extension reloads, logs to `journalctl --user`.
- Review app is a separate GTK4/libadwaita binary. Hot path (capture) stays small and stable; editing/export evolves independently.
- Nothing leaves the machine. Optional localhost calls to Ollama for AI narrative assistance. Google Calendar integration (V2) uses OAuth with tokens stored in GNOME Keyring.
- Communication: daemon exposes a DBus service on the user session bus. Shell extension and review app use DBus; browser extension uses a native-messaging bridge to a small Unix-socket relay that forwards into the daemon.

## 5. Matter Identity & Metadata Model

Each `~/OpenCases/Lastname, Firstname/` folder *is* a matter. The daemon indexes the mount on startup and watches for changes via inotify.

**Minimum viable matter:** folder name alone. Time can be attributed to `Smith, John` the moment the folder exists.

**Enriched metadata:** optional `.matter.yaml` sidecar in the matter folder.

```yaml
client:
  last: Smith
  first: John
matter_type: federal_cja        # federal_cja | retained_hourly | retained_flat | pro_bono | consultation
status: active                  # active | closed | on_hold
court:
  name: "U.S. District Court, W.D. Mich."
  case_number: "1:26-cr-00123"
  judge: "Hon. Jane Doe"
appointment_date: 2026-02-14    # federal_cja only
billing:
  # Exactly one of the following:
  flat_fee: 5000.00             # retained_flat
  # hourly_rate: 350.00         # retained_hourly
  # cja_rate: 175.00            # federal_cja — verify current year's non-capital rate at uscourts.gov/cja-guidelines; user-configurable
  underwater_threshold: 150.00  # retained_flat only: alert when effective $/hr drops below this
aliases:                        # strings used for matter inference in titles/URLs
  - "Smith"
  - "1:26-cr-00123"
  - "Smith trafficking"
opposing_party: "United States of America"
notes: "Suppression motion due 2026-05-10"
```

**Why a YAML sidecar, not a central DB**

- Moves with the folder if reorganized.
- Human-readable and git-friendly.
- Survives uninstall of the time tracker.
- Matches the user's existing "folder per matter" mental model.

**Trade-off accepted:** `.matter.yaml` syncs to Google Drive with the rest of the matter folder, meaning flat-fee amounts and billing rates live in cloud sync. User has accepted this trade-off for the portability benefit.

## 6. Capture & Inference

### 6.1 Event sources

| Source | Emits | Rate |
|---|---|---|
| GNOME Shell extension | `(app_id, window_title, ts)` on window focus change | ~1/sec while active |
| Browser extension | `(browser, tab_title, tab_url, ts)` on tab/URL change | per nav |
| Idle signal | `(idle_start, idle_end, reason)` where reason ∈ {input_timeout, lock, suspend} | threshold-driven |
| Matter indexer | `(matter_added, matter_changed, matter_removed)` | inotify on `~/OpenCases/` |

### 6.2 Matter matching (priority order)

For each incoming event, the matcher scores against the matter index:

1. **File path match** — title or URL contains `~/OpenCases/<matter>/…` → definitive (score 100).
2. **Case number match** — regex for federal (`N:NN-XX-NNNNN`) or state (`CR-YYYY-NNNNNN`) case numbers that match an indexed matter's `court.case_number` → definitive (score 90).
3. **Alias match** — any string in `.matter.yaml` `aliases` matched as a whole word in title/URL (score 70).
4. **Folder-name match** — literal "Lastname, Firstname" in title (score 60).
5. **Last name only** — single-token last name match (score 30); tie-broken by most-recently-active matter.

Matches below score 50 are treated as weak; the top-bar indicator shows an amber "guessing" state and the user can confirm or correct with one click. Matches ≥ 50 transition automatically.

### 6.3 Time model

- **Session**: a continuous stretch of activity attributed to one matter, bounded by matter switch or idle-beyond-threshold.
- **Entry**: the billable unit. By default, all sessions for the same matter on the same calendar date merge into one entry with a single narrative. Individual sessions are preserved in SQLite for audit.
- **Activity trail**: per-session list of (app, title, url, duration) tuples retained for audit and for feeding AI narrative suggestions.

### 6.4 Idle and gap handling

- No input for **5 minutes** (configurable) → timer pauses.
- Gap > **20 minutes** → session closes; on review, user is asked "what was the gap? (break / other matter / forgot to switch)".
- Lock screen or suspend → hard stop; session closes.

### 6.5 Zoom / Meet handling (V1)

Zoom and Google Meet rarely expose client identity in window titles. V1 strategy:

- **Manual nudge**: when a video-conferencing app gains focus and the current matter has had no recent activity, the indicator blinks amber and prompts "still on *Smith, John*?". One click to confirm or pick a different matter.
- **Fallback**: user picks from the top-bar matter list.

V2 adds Google Calendar integration: an event happening now whose title or description contains a matter alias auto-sets the active matter for the event's duration.

## 7. Review & Output

### 7.1 Review app (GTK4 / libadwaita)

**Today view (default)**

- Horizontal timeline bar: colored segments per matter, grey for non-matter activity, hatched for idle.
- Entry list grouped by matter: `Smith, John — 2h 15m — [narrative text field] — [CJA category dropdown for federal_cja matters]`.
- One click expands an entry into its constituent sessions and activity trail for audit.

**Narratives — three fill methods**

1. **Template picker**: dropdown of common activities per matter type. For `federal_cja`: "Client meeting", "Court appearance", "Motion drafting", "Record review", "Legal research", etc. One click inserts and user tweaks.
2. **AI suggestion (opt-in)**: if Ollama is running, a "Suggest" button sends the session's activity trail (file paths, tab titles, durations, matter metadata) to a local model (default `qwen2.5:3b`, configurable) which returns a one-line draft. User edits before saving.
3. **Freeform typing**: always available.

Narratives fill lazily. No review gate blocks the daemon; the user cleans up whenever they're about to bill or submit.

**CJA-20 category tagging (federal_cja only)**

Each entry gets a category dropdown:

- A — In-court
- B — Out-of-court interview and conference
- C — Out-of-court investigation
- D — Legal research and brief writing
- E — Travel
- F — Other

Default is inferred from the activity trail:

- LibreOffice Writer dominant → D
- Firefox/Chrome with research sites (westlaw, fastcase, courtlistener) → D
- Zoom during a calendar event containing matter alias → B (V2; V1 leaves default as Other)
- Zoom/Meet plus court-designated domain → A
- User can override every default.

### 7.2 Outputs

| Type | Format | Destination |
|---|---|---|
| CJA-20 export | CSV: `date, case_no, defendant, category, description, hours` | `~/OpenCases/<matter>/billing/cja-YYYY-MM.csv` |
| Hourly invoice | PDF via LibreOffice template merge | `~/OpenCases/<matter>/billing/invoice-YYYY-MM.pdf` |
| Flat-fee analytics | In-app dashboard, no file export | Review app |
| Practice-wide roll-up | Weekly/monthly CSV | `~/Documents/time-exports/` |

### 7.3 Flat-fee analytics dashboard

For each `retained_flat` matter:

- Flat fee (from `.matter.yaml`).
- Total hours logged (from SQLite).
- Effective $/hr = flat_fee / hours.
- Underwater flag (red) when effective rate < `underwater_threshold` (per-matter configurable).
- Practice-wide: list of flat-fee matters sorted by effective rate, highlighting underwater cases.

### 7.4 Notification cadence

Optional gentle GNOME notification at 17:00 local time: "N entries from today are missing narratives." No hard nudge, no modal, dismissible.

## 8. Operations

### 8.1 Storage

| File | Location | Contents |
|---|---|---|
| Time DB | `~/.local/share/ubuntu-lawyers/time.db` | SQLite (WAL mode): sessions, entries, activity trail, events log |
| Global config | `~/.config/ubuntu-lawyers/config.yaml` | Idle thresholds, non-matter categories, Ollama endpoint and model, default CJA rate, notification preferences |
| Matter metadata | `~/OpenCases/<matter>/.matter.yaml` | Billing, court info, aliases, underwater threshold |
| Exports | `~/OpenCases/<matter>/billing/` | CSV/PDF outputs |
| Daemon logs | `journalctl --user -u ubuntu-lawyers` | Structured logs |

**SQLite schema (key tables)**

- `matters`: id, folder_path, last_name, first_name, matter_type, status, metadata_json, indexed_at
- `sessions`: id, matter_id, start_ts, end_ts, attribution_score, attribution_source
- `activity_trail`: id, session_id, app_id, window_title, tab_url, duration_ms
- `entries`: id, matter_id, date, narrative, cja_category, hours, exported_at
- `events_log`: id, ts, source, payload_json (raw event stream, retained for 30 days by default, configurable)

### 8.2 Privacy

- No telemetry, no analytics, no crash reporting to any remote endpoint.
- Network calls limited to:
  - `localhost:11434` (Ollama, opt-in, only when user clicks "Suggest").
  - Google Calendar API (V2 only, opt-in; OAuth tokens in GNOME Keyring via `libsecret`).
- Browser extension scopes: active tab title and URL only. Never reads page content.
- Ollama prompts contain matter metadata (client name, case number, matter type) and activity trail (file paths, tab titles) — user should be aware that these fields are passed to their local LLM.

### 8.3 Packaging (V1)

Single git repo with `./install.sh` wiring all components:

- Python daemon → `~/.local/lib/ubuntu-lawyers/` plus systemd user unit.
- GNOME Shell extension → `~/.local/share/gnome-shell/extensions/<uuid>/`.
- Firefox `.xpi` (unsigned, loaded as temporary addon or via developer mode) and Chrome unpacked extension, both shipped in-repo.
- GTK4 review app → `~/.local/bin/ubuntu-lawyers-review` with `.desktop` launcher.
- `rclone-mount.service` user unit template, documented in README. User supplies rclone config.

**Dependencies**

- Python 3.12+
- GTK4, libadwaita (Ubuntu 24.04+ defaults)
- GNOME Shell 45+ (Ubuntu 24.04 ships 46)
- rclone
- Ollama (optional)

Flatpak or `.deb` packaging deferred to post-V1 once shape is stable.

### 8.4 Error handling and graceful degradation

- **Capture source failures degrade independently.** If the GNOME extension is unloaded, browser capture keeps working. If browser extension is missing, window-title inference continues at coarser granularity. Top-bar indicator shows amber when any source is down.
- **Daemon not reachable** → top-bar indicator red; shell extension queues events locally (bounded) and flushes on reconnect.
- **Orphaned sessions** (daemon restart mid-session) → recovered from SQLite on startup; open session gets a "system interruption" marker for user review.
- **rclone mount missing** → matter indexer retries with backoff; surfaces in indicator diagnostics panel. Daemon remains functional with last-known matter index.
- **Malformed `.matter.yaml`** → matter falls back to folder-name-only identity; warning logged; review app shows a validation error on that matter.
- **Invalid config.yaml** → daemon refuses to start with a clear error message pointing at the offending key.

### 8.5 Testing strategy

**Unit tests (pytest)** — all pure functions, high coverage target:

- Matter matcher scoring (given title/URL + matter index, correct match and score).
- Idle state machine (transitions on input / timeout / lock / suspend events).
- Session → entry aggregator (correct daily rollup, correct narrative merging).
- CJA CSV exporter (correct shape, correct category mapping).
- Flat-fee calculator (effective $/hr, underwater detection).
- `.matter.yaml` parser (minimal folder, full sidecar, malformed YAML).

**Integration tests**

- Simulated event stream drives daemon end-to-end; assertions on SQLite state and exported artifacts.
- Round-trip: event stream → daemon → review-app read path → export file.

**Manual test matrix** (Wayland + GNOME extension behavior is not fully automatable):

1. Three-matter switch scenario: focus cycles A→B→C→A; verify correct attribution and session boundaries.
2. Idle timeout and resume: verify pause at threshold and resume on input.
3. Zoom-during-calendar-event (V2).
4. Browser tab flips within a single window focus: verify reattribution.
5. `.matter.yaml` added/edited/removed while daemon runs: verify live re-index.
6. Daemon kill + restart mid-session: verify recovery and "system interruption" marker.

Checklist committed to `docs/test-matrix.md`.

**Dev environment**

GNOME Wayland VM recommended for shell-extension iteration to avoid destabilizing the live session.

## 9. V1 / V2 Split

**V1 ships with:**

- GNOME Shell extension (focus capture + top-bar indicator)
- Browser extensions (Firefox + Chrome)
- Python daemon (matching, timing, idle, SQLite)
- Matter indexer (rclone mount watcher)
- Review app (today view, narrative editing, CJA categories, CSV export, flat-fee dashboard, hourly invoice PDF)
- Ollama-backed narrative suggestions (opt-in)
- Manual Zoom/Meet nudge
- Packaged install script

**V2 adds:**

- Google Calendar integration (auto-attribute during scheduled events)
- Advanced CJA-20 form-filling (PDF output matching federal form layout, potentially eVoucher-compatible XML)
- Weekly/monthly invoice batch export
- Possible KDE/non-GNOME portability exploration via AT-SPI

## 10. Open Questions & Known Risks

**Open questions deferred to implementation**

- Exact DBus service name and method signatures (pick during daemon scaffolding).
- Chrome extension distribution: sideload vs internal Chrome Web Store listing — decide once V1 is usable.
- Whether to support multiple `OpenCases` roots (e.g. active + archived directories) or require one canonical root.

**Known risks**

- **GNOME Shell version churn.** Extensions break across major GNOME releases. Mitigation: keep the extension minimal (focus events + top-bar UI only); all logic in the daemon, which is version-independent. Plan for a `shell-version` metadata bump per LTS upgrade.
- **Wayland policy tightening.** If GNOME further restricts window-title access to unprivileged extensions, we fall back to AT-SPI (already on the roadmap as a portability option).
- **rclone mount reliability.** Mount drops (network, auth expiry) will freeze the matter indexer. Mitigation: graceful degradation with last-known index; clear indicator state.
- **Ollama resource footprint.** A 3B model uses ~3GB RAM. Acceptable on developer hardware; document requirement. Suggestion feature stays opt-in.
- **Matter name ambiguity.** Common last names (Smith, Johnson) collide. Mitigation: matching priority favors case numbers and explicit aliases; confirmation UI surfaces ambiguity.
- **Billing data in Drive-synced `.matter.yaml`.** Flat-fee amounts and hourly rates travel with the matter folder on Google Drive. Accepted trade-off; can be revisited if a concern emerges.

## 11. Success Criteria

V1 is considered successful when, after two weeks of daily use:

- ≥ 80% of working time is correctly attributed to a matter (or correctly tagged as non-matter) without user intervention beyond the initial confirmation.
- The user can, in under 10 minutes, produce a defensible CJA-20 CSV for a month of federal panel work.
- The flat-fee dashboard surfaces at least one "underwater" matter the user had not consciously identified.
- The user opens the review app no more than once per day in normal operation.
