# KyMol

KyMol is an open-source PyMOL plugin for reviewing many molecular structures with a Blender-style active-object workflow.

**Author:** RuoyuLiu  
**License:** MIT  
**Current release:** 0.6.1

## What KyMol adds

- A separate, resizable structure-review panel; PyMOL remains the 3D viewport.
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
- Automatic one-second chain color/visibility refresh while chain mode is open.
- A `Tab` hotbox that switches between object mode and chain mode.
- Colored multi-select chain tiles with copy and cut actions and editable default names.
- An always-on-top pushpin in the panel's upper-right corner.
- Native PyMOL groups for P1/P2/P3-style organization, including drag-and-drop.
- Active-object or selection export to PDB/mmCIF.
- Selected-region or whole-chain FASTA display and clipboard copy.
- Standard PyMOL objects, groups, colors, and PSE output for seamless handoff.

## Installation

1. Download [`KyMol-0.6.1.zip`](dist/KyMol-0.6.1.zip) or open [Releases](../../releases/latest).
2. In PyMOL, open **Plugin > Plugin Manager > Install New Plugin**.
3. Select the ZIP file without extracting it.
4. Restart PyMOL.
5. Open **Plugin > KyMol: Structure Review Panel**.

If an old `KYPyMol` version is installed, uninstall it first to avoid duplicate menu entries.

## Main shortcuts

Shortcuts work while the KyMol panel or object list has focus unless marked global.

| Shortcut | Action |
|---|---|
| Click | Select one object and make it active |
| `Ctrl` + click | Add an object or remove an already-selected object |
| `Shift` + click | Select the continuous range from the anchor |
| Blank-space click | Clear the selection and active target |
| `Tab` | Open the object/chain mode hotbox |
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

## Chain mode

Press `Tab`, then choose the right-hand **Chain mode** tile (or press the right arrow). Each object shows stable colored chain tiles such as A, B, C, and D. Select any number of tiles, then:

- Every tile reads the current representative atom color from PyMOL, so its color matches the rendered chain after chain coloring, copy, or cut.
- A crossed-eye icon appears to the left of a chain letter when that chain has no visible representation or its whole object is disabled.
- External PyMOL hide/show changes are reflected automatically while chain mode is open.

- **Copy chains** creates a new object and keeps the source unchanged.
- **Cut chains** moves the selected chains into a new object.
- A single-source operation suggests a safe editable name such as `il13_m1_A_copy` or `il13_m1_AB_cut`.
- Multi-source operations create one result per source object.

Both actions are undoable. The new object can also be renamed later with `F2` or the object context menu.

## Native groups and PSE handoff

Press `M` after selecting objects. KyMol suggests unique names such as `P1`, `P2`, and `P3`; names already used in the current session are skipped. The groups are ordinary PyMOL groups, so they persist in `.pse` sessions and can be opened by users who do not have KyMol installed.

## Development and tests

The test suite covers controller logic and panel behavior:

```text
python -m pytest -q
```

The 0.6.1 suite contains 48 tests and has also been checked in a real PyMOL 3.1.8 headless runtime.

## Version history

- `v0.1.0` — first KYPyMol MVP.
- `v0.1.1` — Qt signal compatibility fix.
- `v0.2.0` — renamed to KYMol; panel-centered workflow, display/delete/rename actions, and original PyMOL chain colors.
- `v0.3.0` — native grouping, drag-and-drop organization, unique P1/P2/P3 names, and expanded tests.
- `v0.4.0` — sequence-aware independent alignment, Blender-style selection, visibility toggle, context menus, and focus shortcut.
- `v0.5.0` — undo/redo, Tab hotbox, chain selection/copy/cut, panel pinning, and safety fixes.
- `v0.6.0` — KyMol branding, true PyMOL chain colors, hidden-chain indicators, and live visual refresh.
- `v0.6.1` — fixed-height, scrollable status output that can no longer squeeze the chain list.

See [CHANGELOG.md](CHANGELOG.md) for details.

## License

[MIT](LICENSE) — Copyright © 2026 RuoyuLiu.
