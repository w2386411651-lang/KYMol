# KYMol

KYMol is an open-source PyMOL plugin for reviewing many molecular structures with a Blender-style active-object workflow.

**Author:** RuoyuLiu  
**License:** MIT  
**Current release:** 0.3.0

## What KYMol adds

- A separate, resizable structure-review panel; PyMOL remains the 3D viewport.
- `Ctrl`/`Shift` multi-selection and a gold last-selected active target.
- Batch alignment of all other selected objects to the active target.
- `align`, `super`, and `cealign` methods, with common-chain, whole-object, or current-selection scopes.
- PyMOL's original 40-color `util.cbc` chain-color sequence.
- Show, hide, isolate, focus, rename, and confirmed deletion actions.
- Native PyMOL groups for P1/P2/P3-style organization, including drag-and-drop.
- Active-object or selection export to PDB/mmCIF.
- Selected-region or whole-chain FASTA display and clipboard copy.
- Standard PyMOL objects, groups, colors, and PSE output for seamless handoff.

## Installation

1. Download `KYMol-0.3.0.zip` from [Releases](../../releases/latest).
2. In PyMOL, open **Plugin > Plugin Manager > Install New Plugin**.
3. Select the ZIP file without extracting it.
4. Restart PyMOL.
5. Open **Plugin > KYMol: Structure Review Panel**.

If an old `KYPyMol` version is installed, uninstall it first to avoid duplicate menu entries.

## Main shortcuts

Shortcuts work while the KYMol panel or object list has focus unless marked global.

| Shortcut | Action |
|---|---|
| `Ctrl`/`Shift` + click | Select one or more rows |
| `Shift+Alt+A` | Align selected non-active objects to the gold active target |
| `Alt+A` | Global PyMOL fallback for alignment |
| `Alt+C` | Color selected/current group by chain |
| `H` | Hide selected/current group |
| `Alt+H` | Show all molecular objects |
| `/` | Isolate selected/current group |
| `M` | Create a native PyMOL group |
| `F2` | Rename the active object |
| `X` or `Delete` | Delete selected objects after confirmation |

## Active-target behavior

PyMOL does not expose a reliable public API for the last object clicked in its native object tree. KYMol therefore maintains selection and the gold active target inside its own panel. Plain click/drag is reserved for group organization; hold `Ctrl` or `Shift` to change the multi-selection.

## Alignment options

- **Method:** `align`, `super`, or `cealign`.
- **Scope:** automatically use a common chain, use whole objects, or use the current PyMOL selection when available.
- **Shared chain:** optionally force a chain ID such as `A`.

Only the moving objects are transformed. The gold active target remains fixed.

## Native groups and PSE handoff

Press `M` after selecting objects. KYMol suggests unique names such as `P1`, `P2`, and `P3`; names already used in the current session are skipped. The groups are ordinary PyMOL groups, so they persist in `.pse` sessions and can be opened by users who do not have KYMol installed.

## Development and tests

The test suite covers controller logic and panel behavior:

```text
python -m pytest -q
```

The 0.3.0 suite contains 18 tests and has also been checked in a real PyMOL headless runtime.

## Version history

- `v0.1.0` — first KYPyMol MVP.
- `v0.1.1` — Qt signal compatibility fix.
- `v0.2.0` — renamed to KYMol; panel-centered workflow, display/delete/rename actions, and original PyMOL chain colors.
- `v0.3.0` — native grouping, drag-and-drop organization, unique P1/P2/P3 names, and expanded tests.

See [CHANGELOG.md](CHANGELOG.md) for details.

## License

[MIT](LICENSE) — Copyright © 2026 RuoyuLiu.
