# KyMol 0.7.0rc2 verification

Validated on Windows with PyMOL 3.1.8, Python 3.10.20, Qt 5.15.15 and synthetic structures. No private structures are included in this repository or its package.

## Automated regression suite

All **112 tests pass** on both Windows Qt and the Qt offscreen backend. Run with a Python environment that provides PyMOL and Qt:

```console
python -m unittest discover -s tests -q
```

The suite covers selection and active-target behavior, alignment preflight, literal chain selectors, native PyMOL alignment/export, compact UI and search, source metadata, and upgrades while the plugin is loaded. Tests that require PyMOL/Qt are skipped if those dependencies are absent; a dependency-free run is not equivalent to the full validation.

## Real installer upgrade validation

The PyMOL installer was exercised in fresh, isolated desktop sessions using its actual `installPluginFromFile` and `PluginInfo.load(force=1)` paths. Only confirmation dialogs were automated; module loading was not mocked.

| Initial state | Result |
| --- | --- |
| 0.6.2 already loaded | rc2 installs and opens correctly |
| 0.6.2 followed by the failed rc1 upgrade | rc2 recovers and opens correctly |
| rc1 loaded in a fresh process | rc2 installs and opens correctly |
| No KyMol loaded | rc2 installs and opens correctly |

Each path also repeats installation. Across the four scenarios, 212 explicit assertions verify current module/class identities, retirement of old timers and source hooks, one menu entry, preserved panel selection/window size/history, native undo/redo, unchanged coordinates and display/view state, and working source tracking after upgrade.

The rc1 failure was reproduced before the fix: PyMOL reloaded the package entry point but retained the old `core` and `ui` modules, leaving a controller without `sources`. The initial rc1 validation covered cold startup and missed this path. `tests/test_plugin_reload.py` now covers the parent-only reload failure and recovery using a small legacy interface fixture, without needing old release files.

## Functional and scientific limits

- Automatic chain ranking uses `SequenceMatcher(autojunk=False)` as a heuristic, not biological identity or binding evidence. Ties are reported; verify important chain/entity mappings independently.
- Alignment performs native rigid fitting, not docking or an affinity calculation. Known invalid batches are rejected before movement; arbitrary native runtime failures are not guaranteed to roll back transactionally.
- Source paths come from observed supported loads or explicit user association. Older objects and custom loaders may have unknown provenance. PSE files can retain local source paths in object metadata.
- Export protects recorded inputs and checks that its target/atom membership did not change while the dialog was open. It does not detect every possible same-name/same-index replacement or coordinate edit.
- Other PyMOL/Qt versions, very large sessions and arbitrary third-party loader-hook combinations remain unverified. Embedded double quotes in chain/object identifiers are explicitly unsupported.

## Package

`python tools/build_plugin.py` creates the deterministic ZIP and its SHA-256 manifest from an explicit allowlist. The package contains only four plugin modules, the MIT license, English/Chinese usage instructions and this verification summary. Tests, caches, internal audit files, structures and sessions are excluded.
