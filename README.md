# KYMol 0.2.0

KYMol is a PyMOL structure-review plugin with a Blender-style active-object workflow.

Author: RuoyuLiu

## Highlights

- All selection and object actions are available inside the KYMol panel.
- The last selected row is the gold active target.
- `Shift+Alt+A` aligns the other selected objects to the active target.
- `Alt+C` uses PyMOL's original `util.cbc` chain-color sequence.
- `H` hides selected objects, `Alt+H` shows hidden objects, and `/` isolates selected objects.
- `X` or `Delete` removes selected objects after confirmation.
- `F2` renames the active object.
- Export the active object or selection to PDB/mmCIF.
- Copy the selected or whole-chain sequence as FASTA.
- The panel is resizable and can be minimized.

## Installation

Install `KYMol-0.2.0.zip` from **Plugin > Plugin Manager > Install New Plugin**.
Then open **Plugin > KYMol: Structure Review Panel**.

## Compatibility

KYMol creates standard PyMOL objects, selections, colors, groups, and PSE sessions.
Recipients do not need KYMol installed to open a saved PSE project.

## License

MIT
