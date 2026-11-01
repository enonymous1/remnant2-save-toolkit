# Changelog

## [2.0.2] - 2026-11-01

### Fixed

- **The GUI could not open at all in v2.0.1.** The close-game-note
  edit in v2.0.1 accidentally deleted the
  `self.find_button = QPushButton("Find saves")` line from
  `FinderScreen.__init__`, so constructing any finder screen raised
  `AttributeError: 'FinderScreen' object has no attribute
  'find_button'`. Windows CI caught it as 8 errored GUI tests; the
  local gates could not, because the GUI tests skip on this box
  (PyQt6's libEGL is absent) and Windows CI is their gate. The line
  is restored, and the fix was verified with a throwaway stub-Qt
  harness that constructs `FinderScreen` and runs a find (the harness
  reproduces the exact v2.0.1 `AttributeError` on the old code and
  passes on the fixed code; it is not shipped, because a stub test
  suite would be more fragile than the Windows CI gate it imitates).
  This was not a test-only failure: in v2.0.1 the GUI itself crashed
  on open, so do not ship or tag v2.0.1 on its own — v2.0.2
  supersedes it.

## [2.0.1] - 2026-10-31

Staff-review fixes to v2.0.0. No behaviour is removed; two behaviours
change deliberately and are called out below.

### Fixed

- **Backup failures are now always `BackupError`, never a traceback.**
  A `mkdir` failure, a copy failure, or a manifest-write failure used
  to escape as a bare `OSError` (and a manifest failure left a
  destination with verified files but no manifest). All three paths now
  convert to `BackupError` and remove the partial destination.
- **Backups no longer follow symlinks.** A symlinked file inside a save
  folder used to be copied as a regular file containing the target's
  contents. Symlinked files and directories are now refused, at
  collection time and again at copy time.
- **Deep VDF nesting no longer crashes discovery.** The recursive VDF
  parser is capped at 64 levels and `parse_libraryfolders_vdf` returns
  `{}` for over-deep or otherwise unparseable documents.
- **`--steam-root` is additive, not a replacement.** Passing one custom
  root used to drop every default root (Program Files, registry, and
  the Linux defaults). Extra roots are now searched first, then the
  defaults, then VDF-declared libraries.
- **WGS sizes now agree between views.** A WGS location's `size_bytes`
  is the set's recursive total, matching the container view, instead of
  the sum of only the top-level blobs. `SaveLocation` carries this as
  `total_size_bytes`; Steam locations are unaffected.
- **GUI labels no longer imply conversion.** The navigation and screen
  titles were `XBOX >>> STEAM` / `STEAM >>> XBOX`; they are now
  `Xbox (WGS) saves` / `Steam saves`, matching the no-conversion note
  that was already on the screens.
- **Empty folders are no longer reported as locations.** An empty
  Steam account folder, an empty userdata `remote`, or an empty WGS
  set used to appear in `find` output with zero files.
- **A second WGS package is no longer dropped.** `find_wgs_containers`
  used to return containers from only the first matching package;
  it now returns containers from every matching package.
- **Duplicate locations are deduplicated by path**, not by full
  dataclass equality, so the same directory reached via two routes
  (or re-scanned after a file changed) appears once.

### Added

- Exception hierarchy in `backup.py`: `InvalidBackupError` for bad
  input and `BackupVerificationError` for a failed hash check, both
  subclasses of `BackupError` so existing callers are unaffected.
- Timestamp length cap (64 characters) in `validate_timestamp`.
- `schema_version: 1` in `find` / `inspect` / `backup` JSON output.
- `--verbose` / `--quiet` flags on the CLI, and a warnings channel:
  permission-denied directories are logged as warnings instead of
  silently returning no results.
- Docstrings for previously undocumented public functions and "why"
  comments for the `t` exclusion, the container-preference rule, the
  double hash, the 100-suffix cap, and the naive-local timestamp.
- `find_wgs_directories` (plural); `find_wgs_directory` is kept as a
  backwards-compatible wrapper returning the first directory.
- A close-the-game warning in the GUI finder screens and in the README:
  a backup taken while the game is running can capture a half-written
  save pair.
- Single-source version: `pyproject.toml` reads the version from
  `remnant2_save_toolkit.__version__` dynamically.
- CI now tests Python 3.10 (the claimed floor), caches pip, runs
  `mypy` on `tests` as well as `src`, and adds a packaging smoke
  check (`python -m build` plus a wheel-existence check).
- Ruff rules expanded from `E,F,I,W` to `E,F,I,W,B,UP,SIM`.
- `.gitignore` now explicitly lists `.mypy_cache/`, `.ruff_cache/`,
  `.idea/`, `.DS_Store`, and `Thumbs.db`.

### Deferred, not done

- **Restore** is still not implemented; it is a v2.1 feature and needs
  the destination-safety design from the review, not a quick copy back.
- **GUI backup still runs on the UI thread**, and `core.py` is still
  one module (the `models.py` / `vdf.py` / `steam.py` / `wgs.py` /
  `platforms.py` split from the review is not done). Both are
  deliberate scope control for a patch release.
- **Actions are still pinned to major tags**, not SHAs, in CI. Pinning
  to a SHA that was not verified against the action's releases would
  be worse than the major tag, so this stays open until the SHAs are
  checked from the actions' own release pages.

## [2.0.0] - 2026-10-27

Modernization of the original single-commit `ss-remnant2` utility
(2026-07-19), rebuilt as a sanitized public export under the name
`remnant2-save-toolkit`. No original history, save data, or credentials
were carried over. All demo data is fictional.

### Added

- Installable `remnant2_save_toolkit` package with a `remnant2-saves`
  CLI: `find`, `inspect`, `backup`, and `gui`.
- Steam discovery over `pathlib`: Saved Games locations plus userdata
  locations, with custom libraries found by parsing
  `libraryfolders.vdf` (nested and flat forms) and the Windows registry
  Steam path.
- Xbox/WGS discovery: package search, containers excluding `t`, and
  per-save-set file lists, with no size-based labelling.
- Verified backups: full copy into a new timestamped directory, SHA-256
  verification of every file, a `backup_manifest.json` written only on
  success, `--dry-run`, and never-overwrite timestamp collisions.
- A working PyQt6 GUI (optional `[gui]` extra) over the same finders
  and backup code as the CLI, with real status labels and wired buttons.
- Fictional demo tree under `examples/demo/` so `find` and `backup`
  can be tried without real saves.
- Test suite, ruff + mypy gates, and GitHub Actions CI (core gates on
  Ubuntu and Windows; GUI tests on Windows, offscreen).
- MIT LICENSE, landing-page README, and this changelog.

### Fixed

- **The GUI's Steam path no longer doubles `Saved Games`.** v1 passed
  `Saved Games\Remnant2` into a finder that prepended `Saved Games`
  again, and read `relative_save_path` instead of calling a finder.
- **Finder methods are actually wired up.** v1's `find_xbox_save` /
  `find_steam_save` were never called and referenced status labels
  that were never created.
- **Dependencies are real.** v1's `requirements.txt` was a 128-line
  global-environment freeze that omitted PyQt6, the only imported
  third-party package, and pulled in unused Pymem, Selenium, MoviePy,
  and more. v2's core has no third-party dependencies; PyQt6 is an
  optional extra.
- **Python floor is honest.** v1 claimed Python 3.8+ while using
  `str | None`, which needs 3.10+. v2 requires `>=3.10`.
- **Backslash paths replaced with `pathlib`**, so the discovery code
  no longer fails on non-Windows platforms when pointed at a tree.

### Removed

- All Steam <-> Xbox save conversion and sync claims: no such code
  existed in v1, and none is claimed in v2.
- The destructive `.old` rename/backup behaviour, which overwrote the
  previous backup in place.
- The size-based `profile_save` / `game_save_N` labelling of WGS sets,
  which was never verified.
