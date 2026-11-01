# remnant2-save-toolkit

Find your Remnant 2 saves on Steam and on the Microsoft Store / Xbox app, and back one up with hash verification before you touch it.

It does not convert a Steam save to Xbox format, or an Xbox save to Steam format. Nothing in this project proves those formats are interchangeable, and nothing here pretends otherwise. WGS save sets are also not labelled "profile" or "game" by size: the tool shows paths, files, and sizes, and you decide what each set is.

<!-- TODO(image): docs/assets/screenshots/gui-home.png — GUI Home screen after "Find all saves" on the fictional demo tree, showing one Steam and one WGS location with the no-conversion note visible. Capture on Windows at 1280x800 before publishing; never use real saves or a real Steam ID. -->

## Description

`remnant2-save-toolkit` is a Python command line tool and optional PyQt6 GUI that finds Remnant 2 save locations and copies one save directory into a new, timestamped, SHA-256-verified backup that never overwrites an earlier backup. The core has no third-party dependencies; PyQt6 is an optional extra used only by the GUI.

Supported layouts: Steam Saved Games (`%USERPROFILE%\Saved Games\Remnant2\Steam\<steam-id>\`) and Steam userdata (`<Steam>\userdata\<user-id>\1282100\remote\`, preferring `remote\SAVED\SaveGames`), plus Microsoft Store / Xbox WGS (`%LOCALAPPDATA%\Packages\<PerfectWorldEntertainment...>\SystemAppData\wgs`). There is no restore command yet, no save editing, and no cloud sync.

## Prerequisites

- Python 3.10 or later (3.10, 3.11, 3.12, and 3.13 are tested in CI).
- Windows for real Xbox / WGS discovery and for real Steam registry discovery. The core runs on Linux and macOS, but WGS discovery is skipped there unless you point it at a copied `Packages` tree with `--packages-dir`.
- Remnant 2 installed on Steam and/or the Microsoft Store / Xbox app, if you want to find real saves. The demo tree works without the game.
- Git and the GitHub CLI (`gh`) only if you are contributing or publishing a release, not for everyday use.

## Installation

From a checkout, in a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install .
```

With the GUI:

```powershell
pip install ".[gui]"
remnant2-saves gui
```

To try it without touching real saves, use the fictional demo tree:

```powershell
remnant2-saves find --user-profile examples/demo --packages-dir examples/demo/Packages
remnant2-saves backup "examples/demo/Saved Games/Remnant2/Steam/76561198000000001" --backup-root ./backups --dry-run
```

<!-- TODO(image): docs/assets/demo.gif — terminal recording (about 25 seconds, looping) of `find` on the demo tree, `backup --dry-run`, `backup`, and the resulting manifest. Record against the fictional demo tree only; do not edit the output. -->

## Local Development

<!-- TODO(image): docs/assets/architecture.svg — CLI and GUI on top, feeding one core box split into Steam discovery, WGS discovery, and the VDF parser, feeding one backup box split into copy, hash-verify, and manifest, with an arrow to disk and a side box for platform defaults and the registry. -->

Project layout: `src/remnant2_save_toolkit/` holds `core.py` (discovery), `backup.py` (verified backups), `cli.py`, and `gui.py` (PyQt6, optional). Tests live in `tests/` and use fictional trees built in `tests/conftest.py`; `examples/demo/` is the same idea as a runnable fixture.

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests && ruff format --check src tests && mypy src tests
```

Or `make test` and `make lint`. GUI tests are marked `gui`, need PyQt6, and run offscreen; on Linux they skip cleanly if PyQt6's system libraries (notably libEGL) are absent, and Windows CI is their gate. Real-save and on-screen GUI behaviour still need a Windows machine with the game installed.

## Deployment

There is no automated release yet, and no PyPI package. CI runs tests and lint only, plus a packaging smoke check (`python -m build` and a wheel-existence check). To cut a release manually: bump `__version__` in `src/remnant2_save_toolkit/__init__.py` — the single source of version, which `pyproject.toml` reads dynamically — tag the commit (`git tag v2.0.1`), build with `python -m build`, and attach the wheel and sdist to a GitHub Release. If PyPI publishing is added later, it should be a separate tag-triggered workflow with trusted publishing, not an extension of the test workflow. The GitHub Pages freeze used by sibling projects does not apply here: this is a desktop tool, not a web dashboard.

## Commands

| Command | What it does |
|---|---|
| `find [--user-profile DIR] [--steam-root DIR ...] [--packages-dir DIR] [--json]` | List Steam and Xbox/WGS save locations. `--steam-root` adds to the defaults; it does not replace them. |
| `inspect PATH [--json]` | List the files in one save directory. The platform is reported as `unknown` because this command does not guess. |
| `backup SOURCE --backup-root DIR [--timestamp TS] [--dry-run] [--json]` | Copy one save directory into a new timestamped folder, hash-verified. |
| `gui [--user-profile DIR] [--steam-root DIR ...] [--packages-dir DIR]` | Open the PyQt6 interface. |

Exit codes: `0` for success, including `find` with no locations found; `2` for a refused or failed `inspect`/`backup` or a GUI that cannot start. JSON output carries `schema_version: 1`. Global flags `--verbose` and `--quiet` control logging; warnings (including permission-denied directory skips) are shown by default.

## How detection works

**Steam.** Saved Games first, one location per numeric account folder that holds files; if the `Steam` folder itself holds files but has no numeric children with files, it is reported as a location. Empty folders are not reported as locations. Then userdata, preferring `remote\SAVED\SaveGames` when it holds files. Custom libraries are found by parsing `steamapps\libraryfolders.vdf` in both its nested and flat forms, plus the Windows registry Steam path; a malformed or absurdly nested VDF file is ignored rather than crashing discovery.

**Xbox / WGS.** `%LOCALAPPDATA%\Packages` folders containing `PerfectWorldEntertainment`, under `SystemAppData\wgs`. Containers are every subdirectory except `t`. Each child directory of a container is one save set, and the files listed for it are its top-level files with no extension, which is how WGS stores save blobs; the reported size is the set's recursive total, so the container view and the `find` view agree. If several matching packages exist, all of their containers are reported, with containers-holding packages first.

## Backups

A backup is a full copy of one save directory into `<backup-root>/<folder-name>-<timestamp>/`, with a `backup_manifest.json` listing every file's size and SHA-256 hash. The manifest is written only after every copied file's hash matches the original. A timestamp collision never overwrites: the second backup gets a `-2`, `-3`, and so on. The backup root must not sit inside the directory being backed up, symlinked files and directories are refused rather than followed, and `--dry-run` reports what would be copied without writing anything. Any copy, verification, or manifest failure removes the partial destination and is reported as a failed backup, not a traceback.

<!-- TODO(image): docs/assets/backup-flow.svg — flowchart: source, hash, copy, re-hash, mismatch deletes the partial backup, match writes the manifest. -->

<!-- TODO(image): docs/assets/screenshots/gui-steam-backup.png — Steam screen with one location selected and the hash-verified status message after a backup of the demo tree. Caption it with the close-the-game warning below. -->

Close the game before backing up real saves: a backup taken while the game is running can capture a half-written save pair. Hash verification proves the copy matches the source at copy time, not that the source was stable.

The manifest format is: `source`, `destination`, `timestamp`, `verified: true`, and `files` (each with `relative_path`, `size_bytes`, and `sha256`). There is no restore command: to restore, copy a backup directory back by hand, after backing up the current saves first.

## Troubleshooting

- **"No save locations found" on Windows:** check the game has actually created saves, and that Steam is installed in a standard location or passed with `--steam-root`. WGS saves appear only for the Microsoft Store / Xbox version.
- **"No save locations found" on Linux/macOS:** expected for WGS unless you pass `--packages-dir` pointing at a copied tree. Steam Saved Games discovery uses your home directory.
- **A location you expect is missing:** a permission-denied directory is skipped with a warning (visible by default; `--quiet` suppresses it). Run from an account that can read the save folders.
- **Backup refused:** the source must be a directory, the backup root must not be inside it, symlinks are refused, and timestamps may contain only letters, digits, `.`, `_`, and `-` (up to 64 characters).
- **GUI will not start:** install the extra with `pip install ".[gui]"`. On Linux, missing system libraries (notably libEGL) will prevent PyQt6 from importing at all; Windows is the supported GUI platform.

## Contributing

Keep the core dependency-free, keep the GUI optional, and never add save conversion without a verified format specification and a test against real (backed-up) saves. Run `pytest -q` and the lint gates before opening a pull request, and add a regression test for any bug fix. See [CHANGELOG.md](CHANGELOG.md) for the release history.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

Unofficial fan utility. Not affiliated with or endorsed by Gunfire Games, Gearbox Publishing, Perfect World Entertainment, Valve, or Microsoft. Remnant 2 and all related marks belong to their owners.
