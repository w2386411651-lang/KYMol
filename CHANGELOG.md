# Changelog

All notable KyMol releases are listed here.

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
