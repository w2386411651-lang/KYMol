"""PyMOL-independent controller logic for KYMol.

The only PyMOL-specific dependency is injected as ``cmd``.  This makes the
selection and alignment policy testable without launching a graphical PyMOL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple


# Exact cycle used by this PyMOL installation's pymol.util.cbc/color_chains.
PYMOL_CHAIN_COLOR_CYCLE = (
    26, 5, 154, 6, 9, 29, 11, 13, 10, 5262,
    12, 36, 5271, 124, 17, 18, 5270, 20, 5272, 52,
    5258, 5274, 5257, 5256, 15, 5277, 5279, 5276, 53, 5278,
    5275, 5269, 22, 5266, 5280, 5267, 5268, 104, 23, 51,
)


class KYMolError(RuntimeError):
    pass


@dataclass
class ActiveObjectState:
    selected: List[str] = field(default_factory=list)
    active: Optional[str] = None


class KYMolController:
    """Maintain KYMol's ordered multi-selection and active target."""

    def __init__(self, cmd, reporter: Callable[[str], None] = print):
        self.cmd = cmd
        self.reporter = reporter
        self.state = ActiveObjectState()
        self._group_name_history = set()

    def report(self, message: str) -> None:
        self.reporter("[KYMol] " + message)

    def molecular_objects(self) -> List[str]:
        return list(self.cmd.get_names_of_type("object:molecule"))

    def group_names(self) -> List[str]:
        return list(self.cmd.get_names_of_type("object:group"))

    def group_members(self, group_name: str) -> List[str]:
        molecular = set(self.molecular_objects())
        return [
            name
            for name in self.cmd.get_names("objects", selection="?{}".format(group_name))
            if name in molecular
        ]

    def next_group_name(self, prefix: str = "P") -> str:
        existing = set(self.cmd.get_names("all")) | self._group_name_history
        index = 1
        while "{}{}".format(prefix, index) in existing:
            index += 1
        return "{}{}".format(prefix, index)

    def _validate_new_name(self, name: str, kind: str) -> str:
        name = name.strip()
        if not name:
            raise KYMolError("{} name cannot be empty.".format(kind))
        if any(character.isspace() for character in name):
            raise KYMolError("{} name cannot contain whitespace.".format(kind))
        if name in self.cmd.get_names("all"):
            raise KYMolError("The name '{}' already exists.".format(name))
        return name

    def assign_objects_to_group(self, object_names: Iterable[str], group_name: str) -> List[str]:
        if group_name not in self.group_names():
            raise KYMolError("The group '{}' does not exist.".format(group_name))
        existing = set(self.molecular_objects())
        members = []
        for name in object_names:
            if name in existing and name not in members:
                members.append(name)
        if not members:
            raise KYMolError("Choose at least one existing object to move into the group.")
        self.cmd.group(group_name, " ".join(members), action="add")
        self.report("Moved {} object(s) into group {}.".format(len(members), group_name))
        return members

    def create_group(self, group_name: str = "") -> str:
        existing = set(self.molecular_objects())
        selected = [name for name in self.state.selected if name in existing]
        if not selected:
            raise KYMolError("Select at least one object before creating a group.")
        requested_name = (group_name or self.next_group_name()).strip()
        if requested_name in self._group_name_history:
            raise KYMolError("The group name '{}' was already used in this session.".format(requested_name))
        group_name = self._validate_new_name(requested_name, "Group")
        self.cmd.group(group_name, " ".join(selected), action="add")
        self._group_name_history.add(group_name)
        self.report("Created group {} with {} object(s).".format(group_name, len(selected)))
        return group_name

    def select_group(self, group_name: str) -> ActiveObjectState:
        members = self.group_members(group_name)
        if not members:
            raise KYMolError("The group '{}' contains no molecular objects.".format(group_name))
        return self.set_selection(members, active=members[-1])

    def display_group(self, group_name: str, mode: str) -> List[str]:
        members = self.group_members(group_name)
        if not members:
            raise KYMolError("The group '{}' contains no molecular objects.".format(group_name))
        if mode == "only":
            self.cmd.disable("all")
            for name in members:
                self.cmd.enable(name)
        elif mode == "show":
            for name in members:
                self.cmd.enable(name)
        elif mode == "hide":
            for name in members:
                self.cmd.disable(name)
        else:
            raise KYMolError("Display mode must be show, hide, or only.")
        self.report("{} group {} ({} object(s)).".format(mode.title(), group_name, len(members)))
        return members

    def set_selection(self, object_names: Iterable[str], active: Optional[str] = None) -> ActiveObjectState:
        valid = set(self.molecular_objects())
        chosen = []
        for name in object_names:
            if name in valid and name not in chosen:
                chosen.append(name)
        if active not in chosen:
            active = chosen[-1] if chosen else None
        self.state = ActiveObjectState(chosen, active)
        self.report(self.status_text())
        return self.state

    def set_active(self, object_name: str) -> ActiveObjectState:
        if object_name not in self.state.selected:
            self.state.selected.append(object_name)
        self.state.active = object_name
        self.report(self.status_text())
        return self.state

    def status_text(self) -> str:
        if not self.state.selected:
            return "No KYMol objects selected. Select objects in the panel or import a PyMOL selection."
        return "Selected: {}; active target: {}".format(
            ", ".join(self.state.selected), self.state.active or "none"
        )

    def sync_from_pymol_selection(self) -> ActiveObjectState:
        # ``sele`` is an unordered atom selection; PyMOL has no public active-object API.
        objects = list(self.cmd.get_object_list("(sele)"))
        if not objects:
            raise KYMolError("PyMOL selection 'sele' contains no molecular objects.")
        self.set_selection(objects, active=self.state.active if self.state.active in objects else objects[-1])
        self.report("Synced from PyMOL 'sele'. Choose the gold active item in the panel before aligning.")
        return self.state

    def _assert_alignment_ready(self) -> Tuple[List[str], str]:
        active = self.state.active
        mobiles = [name for name in self.state.selected if name != active]
        if active is None or active not in self.molecular_objects():
            raise KYMolError("Choose an existing active target in the KYMol panel.")
        if not mobiles:
            raise KYMolError("Select the active target and at least one mobile object.")
        return mobiles, active

    def _chain_selection(self, object_name: str, chain: str) -> str:
        return "({} and chain {} and polymer.protein and name CA)".format(object_name, chain)

    def _common_chain(self, mobile: str, target: str, preferred: str = "") -> Optional[str]:
        mobile_chains = set(self.cmd.get_chains(mobile))
        target_chains = set(self.cmd.get_chains(target))
        if preferred:
            return preferred if preferred in mobile_chains and preferred in target_chains else None
        common = sorted(mobile_chains & target_chains)
        return common[0] if common else None

    def _current_selection_pair(self, mobile: str, target: str) -> Optional[Tuple[str, str]]:
        mobile_sel = "({} and sele and polymer.protein and name CA)".format(mobile)
        target_sel = "({} and sele and polymer.protein and name CA)".format(target)
        if self.cmd.count_atoms(mobile_sel) >= 3 and self.cmd.count_atoms(target_sel) >= 3:
            return mobile_sel, target_sel
        return None

    def _alignment_pair(self, mobile: str, target: str, scope: str, chain: str) -> Tuple[str, str, str]:
        if scope not in ("auto", "selection", "common_chain", "whole_object"):
            raise KYMolError("Unknown alignment scope: {}".format(scope))
        if scope == "selection":
            pair = self._current_selection_pair(mobile, target)
            if pair:
                return pair[0], pair[1], "current selection"
            raise KYMolError("Current selection needs at least 3 protein CA atoms in every object.")
        if scope in ("auto", "common_chain"):
            shared = self._common_chain(mobile, target, chain)
            if shared:
                return self._chain_selection(mobile, shared), self._chain_selection(target, shared), "common chain {}".format(shared)
            if scope == "common_chain":
                requested = " '{}'".format(chain) if chain else ""
                raise KYMolError("No shared chain{} between {} and {}.".format(requested, mobile, target))
        return "({} and polymer.protein and name CA)".format(mobile), "({} and polymer.protein and name CA)".format(target), "whole object CA atoms"

    def align_selected(self, method: str = "super", scope: str = "auto", chain: str = "") -> Dict[str, object]:
        if method not in ("align", "super", "cealign"):
            raise KYMolError("Method must be align, super, or cealign.")
        mobiles, target = self._assert_alignment_ready()
        results = {}
        for mobile in mobiles:
            mobile_sel, target_sel, reason = self._alignment_pair(mobile, target, scope, chain.strip())
            self.report("Aligning {} -> {} using {} ({}, {}).".format(mobile, target, method, reason, mobile_sel))
            # PyMOL's cealign reverses the target/mobile parameter order.
            if method == "cealign":
                results[mobile] = self.cmd.cealign(target_sel, mobile_sel)
            else:
                results[mobile] = getattr(self.cmd, method)(mobile_sel, target_sel)
        self.report("Alignment complete: {} mobile object(s) -> {}.".format(len(mobiles), target))
        return results

    def color_selected_by_chain(self) -> Dict[str, List[str]]:
        objects = self.state.selected
        if not objects:
            raise KYMolError("Select at least one KYMol object before coloring.")
        selection = "(" + " or ".join("model {}".format(name) for name in objects) + ")"
        chains = list(self.cmd.get_chains(selection))
        for index, chain in enumerate(chains):
            chain_token = '"{}"'.format(chain) if len(chain.split()) != 1 else chain
            self.cmd.color(
                PYMOL_CHAIN_COLOR_CYCLE[index % len(PYMOL_CHAIN_COLOR_CYCLE)],
                "(chain {} and ({}))".format(chain_token, selection),
            )
        colored = {name: list(self.cmd.get_chains(name)) for name in objects}
        self.report("Colored chains in {} object(s).".format(len(objects)))
        return colored

    def display_selected(self, mode: str) -> List[str]:
        existing = set(self.molecular_objects())
        selected = [name for name in self.state.selected if name in existing]
        if not selected:
            raise KYMolError("Select at least one existing KYMol object.")
        if mode == "only":
            self.cmd.disable("all")
            for name in selected:
                self.cmd.enable(name)
        elif mode == "show":
            for name in selected:
                self.cmd.enable(name)
        elif mode == "hide":
            for name in selected:
                self.cmd.disable(name)
        else:
            raise KYMolError("Display mode must be show, hide, or only.")
        self.report("{} {} selected object(s).".format(mode.title(), len(selected)))
        return selected

    def show_all_objects(self) -> List[str]:
        objects = self.molecular_objects()
        for name in objects:
            self.cmd.enable(name)
        self.report("Showed all {} molecular object(s).".format(len(objects)))
        return objects

    def focus_active(self) -> str:
        active = self.state.active
        if active not in self.molecular_objects():
            raise KYMolError("Choose an existing active object first.")
        self.cmd.orient(active)
        self.report("Focused the PyMOL view on {}.".format(active))
        return active

    def rename_active(self, new_name: str) -> str:
        active = self.state.active
        if active not in self.molecular_objects():
            raise KYMolError("Choose an existing active object before renaming.")
        new_name = new_name.strip()
        if not new_name:
            raise KYMolError("Object name cannot be empty.")
        if any(character.isspace() for character in new_name):
            raise KYMolError("Object name cannot contain whitespace.")
        if new_name == active:
            return active
        if new_name in self.cmd.get_names("all"):
            raise KYMolError("The name '{}' already exists.".format(new_name))
        self.cmd.set_name(active, new_name)
        self.state.selected = [
            new_name if name == active else name for name in self.state.selected
        ]
        self.state.active = new_name
        self.report("Renamed {} to {}.".format(active, new_name))
        return new_name

    def delete_selected(self) -> List[str]:
        existing = set(self.molecular_objects())
        deleted = [name for name in self.state.selected if name in existing]
        if not deleted:
            raise KYMolError("Select at least one existing KYMol object before deleting.")
        for name in deleted:
            self.cmd.delete(name)
        self.state = ActiveObjectState()
        self.report("Deleted {} object(s) from the current PyMOL session.".format(len(deleted)))
        return deleted

    def active_selection(self, whole_chain: bool = False, chain: str = "") -> str:
        active = self.state.active
        if not active:
            raise KYMolError("Choose an active object first.")
        if chain:
            return "({} and chain {})".format(active, chain)
        if whole_chain:
            return active
        if self.cmd.count_atoms("({} and sele)".format(active)):
            return "({} and sele)".format(active)
        return active

    def export_active(self, filename: str, file_format: str, whole_chain: bool = False, chain: str = "") -> str:
        file_format = file_format.lower()
        if file_format not in ("pdb", "cif"):
            raise KYMolError("Export format must be pdb or cif.")
        selection = self.active_selection(whole_chain=whole_chain, chain=chain)
        self.cmd.save(filename, selection, format=file_format)
        self.report("Exported {} as {}.".format(selection, filename))
        return selection

    def fasta_active(self, whole_chain: bool = False, chain: str = "") -> str:
        selection = self.active_selection(whole_chain=whole_chain, chain=chain)
        fasta = self.cmd.get_fastastr(selection)
        if not fasta.strip():
            raise KYMolError("No polymer sequence was found in {}.".format(selection))
        self.report("Prepared FASTA from {}.".format(selection))
        return fasta
