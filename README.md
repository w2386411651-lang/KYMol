# KyMol

KyMol is an open-source PyMOL plugin for reviewing many molecular structures with a Blender-style active-object workflow.

**Author:** RuoyuLiu  
**License:** MIT  
**Latest version:** 0.7.0rc2 (pre-release)

## What KyMol adds

- A resizable structure-review panel with a draggable divider and independently scrolling tools; PyMOL remains the 3D viewport.
- Model-name search with previous/next matches, group expansion and location outlines, preserving selection and the active target.
- Blender-style click, Ctrl-toggle, Shift-range, and blank-click-clear selection.
- A gold last-selected active target.
- Independent batch alignment of every other selected object to the active target.
- Automatic best sequence-matching chain detection for multi-chain targets.
- `align`, `super`, and `cealign` methods, with common-chain, whole-object, or current-selection scopes.
- PyMOL's original 40-color `util.cbc` chain-color sequence.
- Visibility toggle, isolate, focus, context-menu rename, and confirmed deletion actions.
- Native undo/redo for KyMol edits, including alignment, deletion, naming, grouping, display, and chain operations.
- Chain tiles that use the actual current PyMOL atom color instead of an unrelated fixed palette.
- Per-chain hidden indicators that follow PyMOL representation visibility and object enable/disable state.
- Incremental chain color/visibility refresh: one object per tick while KyMol is active, paused completely while the PyMOL viewport has focus.
- Chain tools visible by default, a **Show chains** switch, and an optional `Tab` hotbox in the model tree.
- Stable-height model rows with horizontally scrolling chain strips and full chain labels.
- Colored multi-select chain tiles with copy and cut actions and editable default names.
- An always-on-top pushpin in the panel's upper-right corner.
- Native PyMOL groups for P1/P2/P3-style organization, including drag-and-drop.
- Active-object or selection export to PDB/mmCIF, defaulting to its recorded source folder and protecting source files.
- Selected-region or whole-chain FASTA display and clipboard copy.
- Standard PyMOL objects, groups, colors, and PSE output for seamless handoff.

## Installation

1. Download [`KyMol-0.7.0rc2.zip`](https://github.com/w2386411651-lang/KYMol/releases/tag/v0.7.0rc2), also available in [dist](dist/KyMol-0.7.0rc2.zip).
2. In PyMOL, open **Plugin > Plugin Manager > Install New Plugin**.
3. Select the ZIP file without extracting it.
4. Accept replacement of the existing KyMol plugin, if prompted. This version refreshes its loaded modules during installation.
5. Open **Plugin > KyMol: Structure Review Panel**.

Version rc2 fixes rc1's in-session upgrade error, `'KYMolController' object has no attribute 'sources'`. PyMOL reloads only a plugin's package entry point; rc2 also replaces its cached private modules and retires the old panel timer and source observer. Installation preserves molecular objects and the panel's model selection. The exact failed-rc1 recovery path is covered by an isolated native PyMOL installer regression. Other PyMOL/Qt versions remain unverified; save your PSE before restarting if a restart is needed.

If an old `KYPyMol` version is installed, uninstall it first to avoid duplicate menu entries.

## Main shortcuts

Shortcuts work while the KyMol panel or object list has focus unless marked global.

| Shortcut | Action |
|---|---|
| Click | Select one object and make it active |
| `Ctrl` + click | Add an object or remove an already-selected object |
| `Shift` + click | Select the continuous range from the anchor |
| Blank-space click | Clear the selection and active target |
| `Ctrl+F` | Find models without changing selection |
| `Enter` / `Shift+Enter` in search | Next / previous match |
| `Escape` in search | Clear search |
| `Tab` in the model tree | Open the optional object/chain mode hotbox |
| `Ctrl+Z` | Undo the last PyMOL/KyMol action |
| `Ctrl+Shift+Z` or `Ctrl+Y` | Redo the last undone action |
| `Shift+Alt+A` | Align selected non-active objects to the gold active target |
| `Alt+A` | Global PyMOL fallback for alignment |
| `Alt+C` | Color selected/current group by chain |
| `H` | Toggle selected/current group hidden or shown |
| `Alt+H` | Show all molecular objects |
| `/` | Isolate selected/current group |
| `F` | Focus the active object |
| `M` | Create a native PyMOL group |
| `F2` | Rename the active object |
| `X` or `Delete` | Delete selected objects after confirmation |

## Active-target behavior

PyMOL does not expose a reliable public API for the last object clicked in its native object tree. KyMol therefore maintains selection and the gold active target inside its own panel. A short plain click selects an object; holding and moving the mouse starts folder drag-and-drop.

## Alignment options

- **Method:** `align` (default), `super`, or `cealign`.
- **Scope:** automatically choose the best sequence-matching chain pair, require a same-ID common chain, use whole objects, or use the current PyMOL selection.
- **Target chain:** optionally restrict automatic matching to a target chain ID such as `A`.

Every non-active object is matched and transformed separately. The gold active target remains fixed.

Alignment requests are checked for every mobile before any model moves. Missing explicit target chains, missing common chains, invalid methods/scopes, and empty selection scopes are errors; they never silently switch to whole-object fitting. `cealign` requires at least 16 CA atoms per side under PyMOL's default window.

Automatic chain ranking retains the previous `SequenceMatcher(autojunk=False)` heuristic. Its score is not sequence identity, a calibrated homology score, or binding evidence. Tied best chain pairs are reported; specify a target chain when biological identity matters. Selection expressions escape supported literal chain operators such as `*`, `+`, and comma. Chain IDs containing embedded double quotes are explicitly unsupported, rather than silently matching different chains.

## Chain mode

Chain controls appear immediately. Use **Show chains** to hide/reopen them; `Tab` remains an optional shortcut in the model tree. Each object shows compact colored chain tiles such as A, B, C, and D. Use strip arrows, the wheel over a strip, or keyboard focus to reach additional chains. Model-row height is unchanged when chain controls are toggled. Select any number of tiles, then:

- Every tile reads the current representative atom color from PyMOL, so its color matches the rendered chain after chain coloring, copy, or cut.
- A crossed-eye icon appears to the left of a chain letter when that chain has no visible representation or its whole object is disabled.
- External PyMOL hide/show changes are reflected incrementally when the KyMol panel is active. Polling pauses while you work in the PyMOL viewport, so large sessions do not add background lag.
- A tooltip says **color / visibility pending** until that object's native visual state has been read. A refresh reads at most one object's atom state; searching does not scan atoms.

- **Copy chains** creates a new object and keeps the source unchanged.
- **Cut chains** moves the selected chains into a new object.
- A single-source operation suggests a safe editable name such as `il13_m1_A_copy` or `il13_m1_AB_cut`.
- Multi-source operations create one result per source object.

Both actions are undoable. The new object can also be renamed later with `F2` or the object context menu.

## Source folders and export

PDB/CIF export operates on the **gold active model**, even when several models are selected. The optional PyMOL selection mode restricts export to selected atoms inside that model. The title names the active model. A new `_export` filename is suggested, existing filenames are skipped, and recorded source files are protected against overwriting.

The plugin records local file paths from subsequent File > Open, `cmd.load`, and PyMOL `load` commands. Object-owned metadata follows renaming, grouping, KyMol chain copy/cut and PSE save/reload. A source folder must still exist and be writable. A model assembled from different source folders, incomplete provenance, or an unavailable folder uses a clearly explained fallback: last successful export folder, Documents, home, working folder, then the system temporary folder, choosing the first writable option.

PyMOL does not expose a reliable original path for objects loaded before tracking starts. Old unannotated sessions, in-memory/custom loaders, and some multiplex replacements therefore remain **unknown**. Use **Associate source…** to identify the original file yourself; this records a user association, not structural identity verification. Saved PSE object metadata contains those local source paths. Source metadata does not affect coordinates or predicted scores.

## Native groups and PSE handoff

Press `M` after selecting objects. KyMol suggests unique names such as `P1`, `P2`, and `P3`; names already used in the current session are skipped. The groups are ordinary PyMOL groups, so they persist in `.pse` sessions and can be opened by users who do not have KyMol installed.

## Development and tests

The test suite covers controller logic, native PyMOL data operations, provenance and Qt behavior. Run with the Python environment containing PyMOL and PyQt5:

```text
python -m unittest discover -s tests -v
```

The suite is also compatible with `python -m pytest -q` when pytest is installed. Windows layout verification uses `QT_QPA_PLATFORM=windows`; offscreen tests cannot substitute for native font and geometry checks. Validation used an isolated PyMOL 3.1.8 desktop and synthetic models. See [verification and limits](VERIFICATION.md) for the test scope and upgrade regression results.

Build a deterministic create-only package with `python tools/build_plugin.py`. The allowlist packages plugin modules, license and installation documents only; it excludes tests, sessions, structures and Git history.

## Version history

- `v0.1.0` — first KYPyMol MVP.
- `v0.1.1` — Qt signal compatibility fix.
- `v0.2.0` — renamed to KYMol; panel-centered workflow, display/delete/rename actions, and original PyMOL chain colors.
- `v0.3.0` — native grouping, drag-and-drop organization, unique P1/P2/P3 names, and expanded tests.
- `v0.4.0` — sequence-aware independent alignment, Blender-style selection, visibility toggle, context menus, and focus shortcut.
- `v0.5.0` — undo/redo, Tab hotbox, chain selection/copy/cut, panel pinning, and safety fixes.
- `v0.6.0` — KyMol branding, true PyMOL chain colors, hidden-chain indicators, and live visual refresh.
- `v0.6.1` — fixed-height, scrollable status output that can no longer squeeze the chain list.

- `v0.6.2` — incremental chain-state polling that stays responsive in large AlphaFold sessions and pauses while PyMOL has focus.
- `v0.7.0rc1` — split layout, search, default compact chain tools, source-aware export and controller correctness fixes.
- `v0.7.0rc2` — fixes upgrades while an older KyMol version is already loaded; preserves panel state and retires old timers and source observers.

See [CHANGELOG.md](CHANGELOG.md) for details.

## License

[MIT](LICENSE) — Copyright © 2026 RuoyuLiu.
