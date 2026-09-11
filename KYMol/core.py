"""PyMOL-independent controller logic for KyMol.

The only PyMOL-specific dependency is injected as ``cmd``.  This makes the
selection and alignment policy testable without launching a graphical PyMOL.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from contextlib import nullcontext
import re
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .provenance import get_tracker


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


@dataclass(frozen=True)
class ChainVisualState:
    color_hex: str
    hidden: bool


@dataclass
class HistoryEntry:
    label: str
    before_state: ActiveObjectState
    after_state: ActiveObjectState
    before_group_names: set
    after_group_names: set


class KYMolController:
    """Maintain KyMol's ordered multi-selection and active target."""

    def __init__(self, cmd, reporter: Callable[[str], None] = print):
        self.cmd = cmd
        self.reporter = reporter
        self.state = ActiveObjectState()
        self._group_name_history = set()
        self._undo_history: List[HistoryEntry] = []
        self._redo_history: List[HistoryEntry] = []
        self._history_serial = 0
        self.sources = get_tracker(cmd)

    def report(self, message: str) -> None:
        self.reporter("[KyMol] " + message)

    def _copy_state(self) -> ActiveObjectState:
        return ActiveObjectState(list(self.state.selected), self.state.active)

    def _run_undoable(self, description: str, operation):
        self._history_serial += 1
        label = "KyMol {}: {}".format(self._history_serial, description)
        before_state = self._copy_state()
        before_groups = set(self._group_name_history)
        context_factory = getattr(self.cmd, "UndoSessionCM", None)
        context = context_factory(label) if context_factory else nullcontext()
        with context:
            value = operation()
        self._undo_history.append(
            HistoryEntry(
                label,
                before_state,
                self._copy_state(),
                before_groups,
                set(self._group_name_history),
            )
        )
        self._redo_history.clear()
        return value

    def _native_history_labels(self) -> Tuple[str, str]:
        inspect_history = getattr(self.cmd, "undo_current_undo_redo", None)
        if inspect_history is None:
            return "", ""
        labels = inspect_history()
        if not labels:
            return "", ""
        return labels[0] or "", labels[1] or ""

    def _restore_history_entry(self, entry: HistoryEntry, use_after: bool) -> None:
        requested = entry.after_state if use_after else entry.before_state
        existing = set(self.molecular_objects())
        selected = [name for name in requested.selected if name in existing]
        active = requested.active if requested.active in selected else (
            selected[-1] if selected else None
        )
        self.state = ActiveObjectState(selected, active)
        self._group_name_history = set(
            entry.after_group_names if use_after else entry.before_group_names
        )

    def undo(self) -> str:
        native_undo = getattr(self.cmd, "undo", None)
        if native_undo is None:
            raise KYMolError("This PyMOL build does not provide undo support.")
        can_inspect = getattr(self.cmd, "undo_current_undo_redo", None) is not None
        next_undo, _ = self._native_history_labels()
        if can_inspect and not next_undo:
            raise KYMolError("Nothing to undo.")
        native_undo()
        description = next_undo or "the last PyMOL action"
        if self._undo_history and (
            not can_inspect or self._undo_history[-1].label == next_undo
        ):
            entry = self._undo_history.pop()
            self._restore_history_entry(entry, use_after=False)
            self._redo_history.append(entry)
        else:
            self.set_selection(self.state.selected, self.state.active)
        self.report("Undid {}.".format(description))
        return description

    def redo(self) -> str:
        native_redo = getattr(self.cmd, "redo", None)
        if native_redo is None:
            raise KYMolError("This PyMOL build does not provide redo support.")
        can_inspect = getattr(self.cmd, "undo_current_undo_redo", None) is not None
        _, next_redo = self._native_history_labels()
        if can_inspect and not next_redo:
            raise KYMolError("Nothing to redo.")
        native_redo()
        description = next_redo or "the last undone PyMOL action"
        if self._redo_history and (
            not can_inspect or self._redo_history[-1].label == next_redo
        ):
            entry = self._redo_history.pop()
            self._restore_history_entry(entry, use_after=True)
            self._undo_history.append(entry)
        else:
            self.set_selection(self.state.selected, self.state.active)
        self.report("Redid {}.".format(description))
        return description

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

    @staticmethod
    def _rgb_to_hex(rgb) -> str:
        channels = [max(0, min(255, round(float(value) * 255))) for value in rgb]
        return "#{:02x}{:02x}{:02x}".format(*channels)

    def chain_visual_states(
        self, object_names: Optional[Iterable[str]] = None
    ) -> Dict[Tuple[str, str], ChainVisualState]:
        existing = self.molecular_objects()
        requested = (
            [name for name in object_names if name in existing]
            if object_names is not None
            else existing
        )
        if not requested:
            return {}
        selection = "(" + " or ".join(
            "model {}".format(self._selection_value(name)) for name in requested
        ) + ")"
        rows = []
        self.cmd.iterate(
            selection,
            "rows.append((model, chain, color, reps))",
            space={"rows": rows},
        )
        grouped = defaultdict(list)
        for object_name, chain, color_index, reps in rows:
            grouped[(object_name, chain)].append((int(color_index), int(reps)))
        enabled = set(self.cmd.get_names("objects", enabled_only=1))
        color_cache = {}
        states = {}
        for object_name in requested:
            for chain in self.cmd.get_chains(object_name):
                chain_rows = grouped.get((object_name, chain), [])
                visible_rows = [row for row in chain_rows if row[1]]
                color_rows = visible_rows or chain_rows
                if color_rows:
                    color_index = Counter(row[0] for row in color_rows).most_common(1)[0][0]
                    if color_index not in color_cache:
                        color_cache[color_index] = self._rgb_to_hex(
                            self.cmd.get_color_tuple(color_index)
                        )
                    color_hex = color_cache[color_index]
                else:
                    color_hex = "#808080"
                hidden = object_name not in enabled or not any(
                    reps for _, reps in chain_rows
                )
                states[(object_name, chain)] = ChainVisualState(color_hex, hidden)
        return states

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
        legalize = getattr(self.cmd, "get_legal_name", None)
        if legalize is not None:
            legal_name = legalize(name)
            if legal_name != name:
                suggestion = legal_name or "{}_1".format(kind.lower())
                raise KYMolError(
                    "{} name '{}' is not valid in PyMOL. Try '{}'.".format(
                        kind, name, suggestion
                    )
                )
        if name in self.cmd.get_names("all"):
            raise KYMolError("The name '{}' already exists.".format(name))
        return name

    def _unique_object_name(self, base_name: str) -> str:
        existing = set(self.cmd.get_names("all"))
        if base_name not in existing:
            return base_name
        index = 2
        while "{}_{}".format(base_name, index) in existing:
            index += 1
        return "{}_{}".format(base_name, index)

    @staticmethod
    def _selection_value(value: str) -> str:
        # PyMOL still interprets *, + and comma as pattern/list operators
        # inside quotes. Escape them so an actual mmCIF chain ID such as A+B
        # cannot silently select chains A and B during a cut or export.
        if '"' in value:
            raise KYMolError("Identifiers containing double quotes cannot be safely selected by KyMol; rename that identifier before this operation.")
        escaped = value.replace("\\", "\\\\")
        for character in "*+,":
            escaped = escaped.replace(character, "\\" + character)
        return '"' + escaped + '"'

    def _normalize_chain_map(
        self, chain_map: Dict[str, Iterable[str]]
    ) -> Dict[str, List[str]]:
        existing = set(self.molecular_objects())
        normalized = {}
        for object_name, requested_chains in chain_map.items():
            if object_name not in existing:
                raise KYMolError(
                    "The source object '{}' no longer exists.".format(object_name)
                )
            available = list(self.cmd.get_chains(object_name))
            chosen = []
            for chain in requested_chains:
                if chain not in available:
                    raise KYMolError(
                        "Chain {!r} in '{}' no longer exists; refresh the chain selection.".format(
                            chain, object_name
                        )
                    )
                if chain not in chosen:
                    chosen.append(chain)
            if chosen:
                # Validate literal identifiers for the entire request before
                # copying or cutting the first object's atoms.
                self._chain_object_selection(object_name, chosen)
                normalized[object_name] = chosen
        if not normalized:
            raise KYMolError("Choose at least one chain before copying.")
        return normalized

    def _chain_object_selection(
        self, object_name: str, chains: Iterable[str]
    ) -> str:
        chain_terms = [
            "chain {}".format(self._selection_value(chain)) for chain in chains
        ]
        return '(model {} and ({}))'.format(
            self._selection_value(object_name), " or ".join(chain_terms)
        )

    def _default_chain_result_name(
        self, object_name: str, chains: Iterable[str], operation: str
    ) -> str:
        suffix = "_".join(
            re.sub(r"[^A-Za-z0-9]+", "", chain) or "blank" for chain in chains
        )
        return "{}_{}_{}".format(object_name, suffix, operation)

    def copy_chains(
        self,
        chain_map: Dict[str, Iterable[str]],
        requested_name: str = "",
    ) -> List[str]:
        normalized = self._normalize_chain_map(chain_map)
        if requested_name and len(normalized) != 1:
            raise KYMolError(
                "A custom name can only be used when copying chains from one object."
            )

        def operation():
            created = []
            for object_name, chains in normalized.items():
                source_record = self.sources.capture([object_name])
                if requested_name:
                    new_name = self._validate_new_name(requested_name, "Object")
                else:
                    base_name = self._default_chain_result_name(
                        object_name, chains, "copy"
                    )
                    new_name = self._unique_object_name(base_name)
                self.cmd.create(
                    new_name,
                    self._chain_object_selection(object_name, chains),
                    zoom=-1,
                )
                self.sources.apply(new_name, source_record)
                created.append(new_name)
            self.state = ActiveObjectState(created, created[-1])
            self.report("Copied chains into {} new object(s).".format(len(created)))
            return created

        return self._run_undoable("Copy chains", operation)

    def cut_chains(
        self,
        chain_map: Dict[str, Iterable[str]],
        requested_name: str = "",
    ) -> List[str]:
        normalized = self._normalize_chain_map(chain_map)
        if requested_name and len(normalized) != 1:
            raise KYMolError(
                "A custom name can only be used when cutting chains from one object."
            )

        def operation():
            created = []
            for object_name, chains in normalized.items():
                source_record = self.sources.capture([object_name])
                if requested_name:
                    new_name = self._validate_new_name(requested_name, "Object")
                else:
                    base_name = self._default_chain_result_name(
                        object_name, chains, "cut"
                    )
                    new_name = self._unique_object_name(base_name)
                self.cmd.extract(
                    new_name,
                    self._chain_object_selection(object_name, chains),
                    zoom=-1,
                )
                self.sources.apply(new_name, source_record)
                created.append(new_name)
            self.state = ActiveObjectState(created, created[-1])
            self.report("Cut chains into {} new object(s).".format(len(created)))
            return created

        return self._run_undoable("Cut chains", operation)

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
        def operation():
            self.cmd.group(group_name, " ".join(members), action="add")
            self.report(
                "Moved {} object(s) into group {}.".format(
                    len(members), group_name
                )
            )
            return members

        return self._run_undoable("Move objects to group", operation)

    def create_group(self, group_name: str = "") -> str:
        existing = set(self.molecular_objects())
        selected = [name for name in self.state.selected if name in existing]
        if not selected:
            raise KYMolError("Select at least one object before creating a group.")
        requested_name = (group_name or self.next_group_name()).strip()
        if requested_name in self._group_name_history:
            raise KYMolError("The group name '{}' was already used in this session.".format(requested_name))
        group_name = self._validate_new_name(requested_name, "Group")
        def operation():
            self.cmd.group(group_name, " ".join(selected), action="add")
            self._group_name_history.add(group_name)
            self.report(
                "Created group {} with {} object(s).".format(
                    group_name, len(selected)
                )
            )
            return group_name

        return self._run_undoable("Create group", operation)

    def select_group(self, group_name: str) -> ActiveObjectState:
        members = self.group_members(group_name)
        if not members:
            raise KYMolError("The group '{}' contains no molecular objects.".format(group_name))
        return self.set_selection(members, active=members[-1])

    def display_group(self, group_name: str, mode: str) -> List[str]:
        members = self.group_members(group_name)
        if not members:
            raise KYMolError("The group '{}' contains no molecular objects.".format(group_name))
        if mode not in ("only", "show", "hide"):
            raise KYMolError("Display mode must be show, hide, or only.")

        def operation():
            if mode == "only":
                self.cmd.disable("all")
                for name in members:
                    self.cmd.enable(name)
            elif mode == "show":
                for name in members:
                    self.cmd.enable(name)
            else:
                for name in members:
                    self.cmd.disable(name)
            self.report(
                "{} group {} ({} object(s)).".format(
                    mode.title(), group_name, len(members)
                )
            )
            return members

        return self._run_undoable(
            "{} group".format(mode.title()), operation
        )

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
        if object_name not in self.molecular_objects():
            raise KYMolError("Choose an existing molecular object as the active target.")
        if object_name not in self.state.selected:
            self.state.selected.append(object_name)
        self.state.active = object_name
        self.report(self.status_text())
        return self.state

    def status_text(self) -> str:
        if not self.state.selected:
            return "No KyMol objects selected. Select objects in the panel or import a PyMOL selection."
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
        existing = set(self.molecular_objects())
        mobiles = [name for name in self.state.selected if name != active]
        if active is None or active not in existing or active not in self.state.selected:
            raise KYMolError("Choose an existing active target in the KyMol panel.")
        if not mobiles:
            raise KYMolError("Select the active target and at least one mobile object.")
        for mobile in mobiles:
            if mobile not in existing:
                raise KYMolError("The mobile object '{}' no longer exists; refresh the selection.".format(mobile))
        return mobiles, active

    def _chain_selection(self, object_name: str, chain: str) -> str:
        return "(model {} and chain {} and polymer.protein and name CA)".format(
            self._selection_value(object_name), self._selection_value(chain)
        )

    def _chain_sequence(self, object_name: str, chain: str) -> str:
        fasta = self.cmd.get_fastastr(self._chain_selection(object_name, chain))
        return "".join(
            line.strip()
            for line in fasta.splitlines()
            if line.strip() and not line.startswith(">")
        )

    def _best_sequence_chain_pair(
        self, mobile: str, target: str, preferred_target_chain: str = "",
        sequence_cache: Optional[Dict[Tuple[str, str], str]] = None,
    ) -> Optional[Tuple[str, str, float]]:
        # This cache lasts only for one explicit alignment request. It avoids
        # repeated target atom traversal, without stale sequence reuse after edits.
        cache = sequence_cache if sequence_cache is not None else {}
        def sequence(object_name, chain):
            key = (object_name, chain)
            if key not in cache:
                cache[key] = self._chain_sequence(object_name, chain)
            return cache[key]
        mobile_chains = list(self.cmd.get_chains(mobile))
        target_chains = list(self.cmd.get_chains(target))
        if preferred_target_chain:
            target_chains = [
                chain for chain in target_chains if chain == preferred_target_chain
            ]
        best = None
        best_count = 0
        for mobile_chain in mobile_chains:
            mobile_sequence = sequence(mobile, mobile_chain)
            if not mobile_sequence:
                continue
            for target_chain in target_chains:
                target_sequence = sequence(target, target_chain)
                if not target_sequence:
                    continue
                score = SequenceMatcher(
                    None, mobile_sequence, target_sequence, autojunk=False
                ).ratio()
                candidate = (mobile_chain, target_chain, score)
                if best is None or score > best[2]:
                    best = candidate
                    best_count = 1
                elif score == best[2]:
                    best_count += 1
        if best_count > 1:
            self.report(
                "Ambiguous automatic chain match: {} pairs share the best heuristic score for {} -> {}; "
                "using {!r} -> {!r} in PyMOL chain order. Use a target-chain restriction, common-chain "
                "or current-selection scope to resolve the intended mapping.".format(
                    best_count, mobile, target, best[0], best[1]
                )
            )
        return best

    def _common_chain(self, mobile: str, target: str, preferred: str = "") -> Optional[str]:
        mobile_chains = set(self.cmd.get_chains(mobile))
        target_chains = set(self.cmd.get_chains(target))
        if preferred:
            return preferred if preferred in mobile_chains and preferred in target_chains else None
        common = sorted(mobile_chains & target_chains)
        return common[0] if common else None

    def _current_selection_pair(self, mobile: str, target: str) -> Optional[Tuple[str, str]]:
        mobile_sel = "(model {} and ?sele and polymer.protein and name CA)".format(self._selection_value(mobile))
        target_sel = "(model {} and ?sele and polymer.protein and name CA)".format(self._selection_value(target))
        if self.cmd.count_atoms(mobile_sel) >= 3 and self.cmd.count_atoms(target_sel) >= 3:
            return mobile_sel, target_sel
        return None

    def _alignment_pair(self, mobile: str, target: str, scope: str, chain: str,
                        sequence_cache=None) -> Tuple[str, str, str]:
        if scope not in ("auto", "selection", "common_chain", "whole_object"):
            raise KYMolError("Unknown alignment scope: {}".format(scope))
        if scope == "selection":
            pair = self._current_selection_pair(mobile, target)
            if pair:
                return pair[0], pair[1], "current selection"
            raise KYMolError("Current selection needs at least 3 protein CA atoms in every object.")
        if scope == "auto":
            best = self._best_sequence_chain_pair(mobile, target, chain, sequence_cache)
            if best:
                mobile_chain, target_chain, score = best
                return (
                    self._chain_selection(mobile, mobile_chain),
                    self._chain_selection(target, target_chain),
                    "best sequence chains {!r} -> {!r} ({:.1%} heuristic sequence-match ratio)".format(
                        mobile_chain, target_chain, score
                    ),
                )
            raise KYMolError(
                "No protein chain pair between {} and {}{}; choose a valid chain or explicitly choose whole-object scope.".format(
                    mobile, target, " for target chain {!r}".format(chain) if chain else ""
                )
            )
        if scope == "common_chain":
            shared = self._common_chain(mobile, target, chain)
            if shared is not None:
                return self._chain_selection(mobile, shared), self._chain_selection(target, shared), "common chain {}".format(shared)
            requested = " '{}'".format(chain) if chain else ""
            raise KYMolError("No shared chain{} between {} and {}.".format(requested, mobile, target))
        return "(model {} and polymer.protein and name CA)".format(self._selection_value(mobile)), "(model {} and polymer.protein and name CA)".format(self._selection_value(target)), "whole object CA atoms"

    def align_selected(self, method: str = "align", scope: str = "auto", chain: str = "") -> Dict[str, object]:
        if method not in ("align", "super", "cealign"):
            raise KYMolError("Method must be align, super, or cealign.")
        mobiles, target = self._assert_alignment_ready()
        # Resolve every scope before applying the first transform. A stale or
        # invalid later mobile must not leave an earlier mobile already moved.
        sequence_cache = {}
        pairs = {}
        for mobile in mobiles:
            pair = self._alignment_pair(mobile, target, scope, chain.strip(), sequence_cache)
            # PyMOL CE uses a default window of 8 and requires 2 * window atoms.
            minimum = 16 if method == "cealign" else 3
            if min(self.cmd.count_atoms(pair[0]), self.cmd.count_atoms(pair[1])) < minimum:
                raise KYMolError("{} needs at least {} protein CA atoms in both {} and {}.".format(method, minimum, mobile, target))
            pairs[mobile] = pair

        def operation():
            results = {}
            for mobile in mobiles:
                mobile_sel, target_sel, reason = pairs[mobile]
                self.report(
                    "Aligning {} -> {} using {} ({}, {}).".format(
                        mobile, target, method, reason, mobile_sel
                    )
                )
                # PyMOL's cealign reverses the target/mobile parameter order.
                if method == "cealign":
                    results[mobile] = self.cmd.cealign(target_sel, mobile_sel)
                else:
                    results[mobile] = getattr(self.cmd, method)(
                        mobile_sel, target_sel
                    )
            self.report(
                "Alignment complete: {} mobile object(s) -> {}.".format(
                    len(mobiles), target
                )
            )
            return results

        return self._run_undoable("Align objects", operation)

    def color_selected_by_chain(self) -> Dict[str, List[str]]:
        objects = self.state.selected
        if not objects:
            raise KYMolError("Select at least one KyMol object before coloring.")
        selection = "(" + " or ".join("model {}".format(self._selection_value(name)) for name in objects) + ")"
        chains = list(self.cmd.get_chains(selection))
        chain_tokens = [self._selection_value(chain) for chain in chains]

        def operation():
            for index, chain_token in enumerate(chain_tokens):
                self.cmd.color(
                    PYMOL_CHAIN_COLOR_CYCLE[index % len(PYMOL_CHAIN_COLOR_CYCLE)],
                    "(chain {} and ({}))".format(chain_token, selection),
                )
            colored = {
                name: list(self.cmd.get_chains(name)) for name in objects
            }
            self.report("Colored chains in {} object(s).".format(len(objects)))
            return colored

        return self._run_undoable("Color chains", operation)

    def display_selected(self, mode: str) -> List[str]:
        existing = set(self.molecular_objects())
        selected = [name for name in self.state.selected if name in existing]
        if not selected:
            raise KYMolError("Select at least one existing KyMol object.")
        if mode not in ("only", "show", "hide"):
            raise KYMolError("Display mode must be show, hide, or only.")

        def operation():
            if mode == "only":
                self.cmd.disable("all")
                for name in selected:
                    self.cmd.enable(name)
            elif mode == "show":
                for name in selected:
                    self.cmd.enable(name)
            else:
                for name in selected:
                    self.cmd.disable(name)
            self.report(
                "{} {} selected object(s).".format(
                    mode.title(), len(selected)
                )
            )
            return selected

        return self._run_undoable("{} objects".format(mode.title()), operation)

    def toggle_objects_visibility(self, object_names: Iterable[str]) -> List[str]:
        existing = set(self.molecular_objects())
        objects = [name for name in object_names if name in existing]
        if not objects:
            raise KYMolError("Select at least one existing KyMol object.")
        enabled = set(self.cmd.get_names("objects", enabled_only=1))
        should_hide = any(name in enabled for name in objects)

        def action():
            operation = self.cmd.disable if should_hide else self.cmd.enable
            for name in objects:
                operation(name)
            self.report(
                "{} {} object(s).".format(
                    "Hid" if should_hide else "Showed", len(objects)
                )
            )
            return objects

        return self._run_undoable("Toggle visibility", action)

    def toggle_selected_visibility(self) -> List[str]:
        return self.toggle_objects_visibility(self.state.selected)

    def toggle_group_visibility(self, group_name: str) -> List[str]:
        members = self.group_members(group_name)
        if not members:
            raise KYMolError("The group '{}' contains no molecular objects.".format(group_name))
        return self.toggle_objects_visibility(members)

    def show_all_objects(self) -> List[str]:
        objects = self.molecular_objects()

        def operation():
            for name in objects:
                self.cmd.enable(name)
            self.report(
                "Showed all {} molecular object(s).".format(len(objects))
            )
            return objects

        return self._run_undoable("Show all objects", operation)

    def focus_active(self) -> str:
        active = self.state.active
        if active not in self.molecular_objects():
            raise KYMolError("Choose an existing active object first.")

        def operation():
            self.cmd.orient(active)
            self.report("Focused the PyMOL view on {}.".format(active))
            return active

        return self._run_undoable("Focus active object", operation)

    def rename_active(self, new_name: str) -> str:
        active = self.state.active
        if active not in self.molecular_objects():
            raise KYMolError("Choose an existing active object before renaming.")
        new_name = new_name.strip()
        if new_name == active:
            return active
        new_name = self._validate_new_name(new_name, "Object")
        def operation():
            self.cmd.set_name(active, new_name)
            self.state.selected = [
                new_name if name == active else name for name in self.state.selected
            ]
            self.state.active = new_name
            self.report("Renamed {} to {}.".format(active, new_name))
            return new_name

        return self._run_undoable("Rename object", operation)

    def delete_selected(self) -> List[str]:
        existing = set(self.molecular_objects())
        deleted = [name for name in self.state.selected if name in existing]
        if not deleted:
            raise KYMolError("Select at least one existing KyMol object before deleting.")

        def operation():
            for name in deleted:
                self.cmd.delete(name)
            self.state = ActiveObjectState()
            self.report(
                "Deleted {} object(s) from the current PyMOL session.".format(
                    len(deleted)
                )
            )
            return deleted

        return self._run_undoable("Delete objects", operation)

    def active_selection(self, whole_chain: bool = False, chain: str = "") -> str:
        active = self.state.active
        if active not in self.molecular_objects():
            raise KYMolError("Choose an existing active object first.")
        model = "model {}".format(self._selection_value(active))
        if chain:
            if chain not in self.cmd.get_chains(active):
                raise KYMolError("Chain {!r} does not exist in active object '{}'.".format(chain, active))
            selection = "({} and chain {})".format(model, self._selection_value(chain))
        elif not whole_chain and self.cmd.count_atoms("({} and ?sele)".format(model)):
            selection = "({} and ?sele)".format(model)
        else:
            selection = "({})".format(model)
        if not self.cmd.count_atoms(selection):
            raise KYMolError("The requested active-object selection contains no atoms.")
        return selection

    def export_active(self, filename: str, file_format: str, whole_chain: bool = False, chain: str = "") -> str:
        file_format = file_format.lower()
        if file_format not in ("pdb", "cif"):
            raise KYMolError("Export format must be pdb or cif.")
        selection = self.active_selection(whole_chain=whole_chain, chain=chain)
        if self.sources.is_source_path(filename, self.state.active):
            raise KYMolError("This is an original source file. Choose a new export filename to preserve it.")
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
