# remnant2-save-toolkit

Find your Remnant 2 saves on Steam and on the Microsoft Store / Xbox app, and back one up with hash verification before you touch it. That's the whole job, and it's stated plainly because the first version of this project promised more than it did.

The original `ss-remnant2` (July 2026) was a GUI shell: two screens with a label and a Back button, finder methods that were never called, and no code that copied or converted anything. This rebuild keeps the finder idea, fixes the paths and the wiring, and adds the one write operation a save tool should have: a verified backup that never overwrites an earlier one.

## What it does not do

It does **not** convert a Steam save to Xbox format, or an Xbox save to Steam format. Nothing in the original project proved those formats are interchangeable, and nothing here pretends otherwise. If you copy a save across platforms by hand, that is your call, on a backup you made first. WGS save sets are also not labelled "profile" or "game" by size: the tool shows you paths, files, and sizes, and you decide what each set is.

## Quick start

```bash
pip install .
remnant2-saves find
```

Try it on the fictional demo tree first, no real saves needed:

```bash
remnant2-saves find --user-profile examples/demo --packages-dir examples/demo/Packages
# [steam] .../Saved Games/Remnant2/Steam/76561198000000001 (2 files, ...)
# [xbox-wgs] .../SystemAppData/wgs/000901F4A1B2C3D4/11111111-... (2 files, ...)
```

Back up the demo Steam set, with a dry run first:

```bash
remnant2-saves backup "examples/demo/Saved Games/Remnant2/Steam/76561198000000001" --backup-root ./backups --dry-run
remnant2-saves backup "examples/demo/Saved Games/Remnant2/Steam/76561198000000001" --backup-root ./backups
# Backed up ... to ./backups/76561198000000001-20260101-120000 (2 files, hash-verified).
```

Open the GUI (needs the optional PyQt6 extra):

```bash
pip install ".[gui]"
remnant2-saves gui
```

The GUI uses the same finders and the same backup code as the CLI. Double-click a result to open its folder.

## Commands

| Command | What it does |
|---|---|
| `find [--user-profile DIR] [--steam-root DIR ...] [--packages-dir DIR] [--json]` | List Steam and Xbox/WGS save locations. |
| `inspect PATH [--json]` | List the files in one save directory, without guessing its platform. |
| `backup SOURCE --backup-root DIR [--timestamp TS] [--dry-run] [--json]` | Copy one save directory into a new timestamped folder, hash-verified. |
| `gui [--user-profile DIR] [--steam-root DIR ...] [--packages-dir DIR]` | Open the PyQt6 interface. |

`find` with no options searches your real home directory, the usual Steam install locations (plus the registry path and any libraries declared in `libraryfolders.vdf`), and `%LOCALAPPDATA%\Packages` on Windows. Pass `--user-profile`, `--steam-root`, or `--packages-dir` to point it at a copied tree instead, which is how the demo and the tests work on any platform.

## How detection works

**Steam.** Saved Games first: `%USERPROFILE%\Saved Games\Remnant2\Steam\<steam-id>\`, one location per numeric account folder. Then Steam userdata: `<Steam>\userdata\<user-id>\1282100\remote\`, preferring `remote\SAVED\SaveGames` when it exists. Custom libraries are found by parsing `steamapps\libraryfolders.vdf` in both its current (nested) and older (flat) forms; a malformed VDF file is ignored rather than crashing discovery.

**Xbox / WGS.** `%LOCALAPPDATA%\Packages` folders containing `PerfectWorldEntertainment`, under `SystemAppData\wgs`. Containers are every subdirectory except `t`. Each child directory of a container is one save set, and the files listed for it are its top-level files with no extension, which is how WGS stores save blobs.

All paths are built with `pathlib`. The original used backslash string literals, which broke its Linux branch and doubled `Saved Games` in the GUI's Steam path.

## Backups

A backup is a full copy of one save directory into `<backup-root>/<folder-name>-<timestamp>/`, with a `backup_manifest.json` listing every file's size and SHA-256 hash. The manifest is written only after every copied file's hash matches the original. A timestamp collision never overwrites: the second backup gets a `-2`, `-3`, ... suffix. The backup root must not sit inside the directory being backed up, and `--dry-run` reports what would be copied without writing anything.

This replaces the original's `.old` behaviour, which copied or renamed over a single `<name>.old` file in place and destroyed the previous backup on a second run. There is no rename or in-place overwrite operation in v2.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests && ruff format --check src tests && mypy src
```

GUI tests are marked `gui`, need PyQt6, and run offscreen. CI runs the core gates on Ubuntu and Windows (Python 3.11-3.13) and the GUI tests on Windows only.

Real-save behaviour still needs a Windows machine with the game installed: the Linux box this was built on can only exercise fake trees, and the GUI was verified offscreen, not by eye. Back up your real saves before letting any tool near them, including this one.

## Disclaimer

Unofficial fan utility. Not affiliated with or endorsed by Gunfire Games, Gearbox Publishing, Perfect World Entertainment, Valve, or Microsoft. Remnant 2 and all related marks belong to their owners.

## License

MIT. See [LICENSE](LICENSE).
