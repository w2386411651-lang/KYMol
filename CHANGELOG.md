# Changelog

All notable KYMol releases are listed here.

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
