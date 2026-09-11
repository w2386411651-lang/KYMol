# Changelog

All notable KyMol releases are listed here.

## 0.7.0rc2 — In-session upgrade repair (2026-09-11)

- Fixed rc1 initialization failure when PyMOL reloads the package while an older controller/UI remains cached (`KYMolController` missing `sources`). Refresh the private modules together and recreate the controller with the current interface.
- Retire same-package old dialogs, timers, shortcuts and source observers; recover selection, active model, window geometry and controller history, including the dialog reference lost by a failed rc1 install.
- Reuse the existing same-package menu callback and keep one current source observer on repeated installs. Molecular objects and source metadata remain in PyMOL.
- Added actual in-session installer regression using the frozen 0.6.2 package, delivered rc1 and synthetic structures. The earlier rc1 verification covered cold startup and missed this upgrade path.

## 0.7.0rc1 — Review panel update (2026-09-11)

- Added a draggable model/tools divider, independently scrolling tools and a compact usable window.
- Added case-insensitive model search with previous/next navigation, group expansion and location outlines, preserving active target, selection and object visibility.
- Made chain tools visible by default and kept model rows stable with accessible horizontal chain strips.
- Recorded source-file provenance on standard loads and preserved it through rename, group, chain copy/cut and PSE handoff; exports use an explained writable directory and protect recorded source files.
- Fixed silent whole-object alignment fallback, missing `sele` export, unsafe literal chain selectors, invalid batch preflight and initial dialog selection loss. Preserved the existing chain-ranking heuristic with explicit tie reporting and request-scoped caching.
- Added native PyMOL, Windows Qt and export regressions, verified with synthetic data.

## 0.6.2

- Replaced the once-per-second all-object atom scan with round-robin, one-object-at-a-time chain-state refreshes.
- Paused chain-state polling completely whenever the KyMol panel is not the active window, eliminating background polling while the user manipulates the PyMOL viewport.
- Reduced the median refresh cost in a real PyMOL 3.1.8 session with ten AlphaFold 3 CIF models (94,370 atoms) from 107.3 ms for one global scan to 12.0 ms per incremental tick; an inactive-panel tick takes approximately 0.002 ms.
- Added regression tests for incremental polling and inactive-window suspension; the suite now contains 50 tests.

## 0.6.1

- Kept the bottom status output available for errors and operation feedback while fixing it to a stable, scrollable height.
- Reserved a usable minimum height for the object/chain list in chain mode, so long or rapid output cannot squeeze chain tiles out of view.
- Added regression coverage for repeated multi-line status output; the suite now contains 48 tests.

## 0.6.0

- Updated all user-visible branding, menus, titles, console output, and package names to `KyMol`.
- Replaced hashed chain-tile colors with the actual representative atom colors currently used by PyMOL.
- Added a crossed-eye icon to every hidden chain tile, including per-chain hide/isolate and whole-object disable states.
- Added lightweight one-second color and visibility refresh while chain mode is visible.
- Added contrast-aware chain label text and hidden icons for dark and light PyMOL colors.
- Expanded automated coverage to 47 tests and verified color/visibility behavior in PyMOL 3.1.8.

## 0.5.0

- Added PyMOL-native undo and redo for KYMol structure, display, grouping, naming, and view operations.
- Added `Ctrl+Z`, `Ctrl+Shift+Z`, and `Ctrl+Y`, plus visible undo/redo controls.
- Added a `Tab` hotbox for switching between object mode and chain mode.
- Added stable colored A/B/C/... chain tiles with multi-selection.
- Added undoable chain copy and cut operations with safe default names and editable names.
- Added a pushpin control that keeps the KYMol panel always on top.
- Fixed active-object loss while rebuilding the object tree after undo/redo.
- Added clear errors and safe suggestions for invalid or reserved PyMOL names.
- Added quoted blank-chain support and empty-history handling.
- Expanded automated coverage to 43 tests and verified chain history in PyMOL 3.1.8.

## 0.4.0

- Fixed batch alignment so every non-active object is independently aligned to the gold target.
- Changed the default method from `super` to PyMOL's sequence-aware `align`.
- Added automatic best sequence-matching chain-pair detection for multi-chain targets.
- Made numeric object names such as `3bpo` unambiguous with explicit `model` selections.
- Added Blender-style plain-click, Ctrl-toggle, Shift-range, and blank-click-clear behavior.
- Changed `H` to toggle selected objects between hidden and shown.
- Added `F` to focus the active object.
- Moved Rename and Delete from the home panel to each object's right-click menu.
- Expanded automated coverage to 23 tests.

## 0.3.0

- Added native PyMOL group creation with `M`.
- Added unique default group names (`P1`, `P2`, `P3`, ...).
- Added drag-and-drop object organization in the KYMol panel.
- Added group-aware show, hide, and isolate operations.
- Added group double-click selection.
- Expanded automated coverage to 18 tests.

## 0.2.0

- Renamed KYPyMol to KYMol.
- Moved selection and structure actions into the KYMol panel.
- Added `H`, `Alt+H`, `/`, `X`, `Delete`, and `F2` shortcuts.
- Added a resizable/minimizable window.
- Matched PyMOL's original `util.cbc` 40-color chain sequence.
- Added safer confirmed deletion.

## 0.1.1

- Fixed Qt signal handling for button callbacks on PyMOL builds that pass a boolean click argument.

## 0.1.0

- Initial KYPyMol MVP.
- Added a gold active target, batch alignment, chain coloring, PDB/mmCIF export, and FASTA copy.
