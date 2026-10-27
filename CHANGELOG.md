# Changelog

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
