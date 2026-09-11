"""Object-owned source provenance and safe export suggestions.

Paths are recorded only from an observed local file load or an explicit user
association.  They are never recovered from molecular object names.  Native
object properties keep metadata with renames, groups and saved PSE sessions,
and prevent a deleted name from lending its provenance to a new object.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Tuple


PROPERTY = "kymol_source_v1"
_STRUCTURE_FORMATS = {
    "pdb", "pqr", "cif", "mmcif", "bcif", "mol", "mol2", "sdf",
    "mae", "mmtf", "xyz", "gro", "pdbqt", "ent",
}
# Name of the target parameter and its positional index in memory loaders.
# These calls can append states to an existing file-loaded object without
# clearing its native properties, so they must invalidate completeness.
_MEMORY_LOADERS = {
    "read_pdbstr": ("oname", 1),
    "read_molstr": ("name", 1),
    "read_sdfstr": ("name", 1),
    "read_mmodstr": ("name", 1),
    "read_mol2str": ("name", 1),
    "load_model": ("object", 1),
    "load_raw": ("object", 2),
}


@dataclass(frozen=True)
class SourceRecord:
    paths: Tuple[str, ...] = ()
    complete: bool = False
    evidence: str = "unknown"


@dataclass(frozen=True)
class ExportSuggestion:
    path: str
    directory: str
    reason: str
    used_fallback: bool


def _canonical(path) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _unique_paths(paths: Iterable[str]) -> Tuple[str, ...]:
    result = []
    seen = set()
    for path in paths:
        normalized = _canonical(path)
        key = os.path.normcase(normalized)
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    return tuple(result)


def directory_writable(path: str) -> bool:
    """Check the actual directory ACL with an automatically removed temp file."""
    if not os.path.isdir(path):
        return False
    try:
        with tempfile.TemporaryFile(prefix=".kymol-write-check-", dir=path):
            pass
        return True
    except OSError:
        return False


class SourceTracker:
    def __init__(self, cmd):
        self.cmd = cmd
        self._installed = False
        self._observing = 0
        self._patches = []

    def record_for(self, name: str) -> SourceRecord:
        getter = getattr(self.cmd, "get_property", None)
        if getter is None:
            return SourceRecord()
        try:
            raw = getter(PROPERTY, name)
            if not raw:
                return SourceRecord()
            data = json.loads(raw)
            paths = data.get("paths", [])
            if data.get("version") != 1 or not isinstance(paths, list):
                return SourceRecord()
            if any(not isinstance(p, str) or not os.path.isabs(p) for p in paths):
                return SourceRecord()
            return SourceRecord(_unique_paths(paths), data.get("complete") is True,
                                str(data.get("evidence", "unknown")))
        except (ValueError, TypeError, OSError, AttributeError):
            return SourceRecord()

    def apply(self, name: str, record: SourceRecord) -> None:
        setter = getattr(self.cmd, "set_property", None)
        if setter is None:
            return
        value = json.dumps({"version": 1, "paths": list(record.paths),
                            "complete": record.complete, "evidence": record.evidence})
        setter(PROPERTY, value, name, proptype=6)

    set_record = apply

    def capture(self, names: Iterable[str]) -> SourceRecord:
        records = [self.record_for(name) for name in names]
        return SourceRecord(
            _unique_paths(path for record in records for path in record.paths),
            bool(records) and all(record.complete and record.paths for record in records),
            "derived",
        )

    def inherit(self, new_name: str, source_names: Iterable[str]) -> None:
        self.apply(new_name, self.capture(source_names))

    def associate_source(self, name: str, filename: str) -> SourceRecord:
        """Attach the file explicitly identified by the user, not a identity proof."""
        if name not in self.cmd.get_names_of_type("object:molecule"):
            raise ValueError("Choose an existing molecular object to associate a source.")
        path = _canonical(filename)
        if not os.path.isfile(path):
            raise ValueError("The associated source must be an existing local file.")
        if getattr(self.cmd, "set_property", None) is None:
            raise ValueError("This PyMOL build cannot store source metadata.")
        record = SourceRecord((path,), True, "user_associated")
        self.apply(name, record)
        return record

    record_source = associate_source

    def is_source_path(self, filename: str, name: str = "") -> bool:
        """Protect inputs of all current objects, even when exporting another one."""
        key = os.path.normcase(_canonical(filename))
        names = self.cmd.get_names_of_type("object:molecule")
        for object_name in names:
            for source in self.record_for(object_name).paths:
                if key == os.path.normcase(source):
                    return True
                try:
                    if os.path.exists(filename) and os.path.samefile(filename, source):
                        return True
                except OSError:
                    pass
        return False

    def export_default(self, name: str, file_format: str,
                       fallback_directory: str = "") -> ExportSuggestion:
        if file_format.lower() not in ("pdb", "cif"):
            raise ValueError("Export format must be pdb or cif.")
        record = self.record_for(name)
        directories = _unique_paths(os.path.dirname(path) for path in record.paths)
        directory = ""
        fallback = True
        if record.complete and len(directories) == 1 and directory_writable(directories[0]):
            directory = directories[0]
            fallback = False
            reason = ("Using the source folder explicitly associated by the user."
                      if record.evidence == "user_associated"
                      else "Using the active model's recorded source folder.")
        elif not record.paths:
            reason = "Original source is unknown; using a writable fallback folder."
        elif not record.complete:
            reason = "Some source data is unknown; using a writable fallback folder."
        elif len(directories) != 1:
            reason = "This model combines multiple source folders; using a writable fallback folder."
        else:
            reason = "The source folder is missing or not writable; using a writable fallback folder."
        if not directory:
            candidates = [fallback_directory, str(Path.home() / "Documents"),
                          str(Path.home()), os.getcwd(), tempfile.gettempdir()]
            for candidate in candidates:
                if candidate and directory_writable(candidate):
                    directory = _canonical(candidate)
                    break
        if not directory:
            raise ValueError("No writable export folder is available. Choose a writable folder.")
        # Always use a distinct export basename and skip existing files.
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .") or "model"
        stem = stem[:150] + "_export"
        extension = "." + file_format.lower()
        filename = os.path.join(directory, stem + extension)
        index = 2
        while os.path.exists(filename) or self.is_source_path(filename):
            filename = os.path.join(directory, "{}_{}{}".format(stem, index, extension))
            index += 1
        return ExportSuggestion(filename, directory, reason, fallback)

    suggested_export_path = export_default

    def _load_details(self, args, kwargs):
        filename = kwargs.get("filename", args[0] if args else "")
        requested = str(kwargs.get("object", args[1] if len(args) > 1 else "")).strip()
        format_arg = kwargs.get("format", args[3] if len(args) > 3 else "")
        try:
            from pymol.importing import filename_to_format, unquote
            filename = unquote(os.fspath(filename))
            basename, _ext, guessed_format, _zipped = filename_to_format(filename)
            actual_format = str(format_arg or guessed_format).lower()
            if actual_format not in _STRUCTURE_FORMATS:
                return None
            path = _canonical(self.cmd.exp_path(filename))
            if not os.path.isfile(path):
                return None
            # Forward naming uses PyMOL's own loader rules, never reverse path guessing.
            target = requested or basename
            target = self.cmd.get_legal_name(target)
            return path, target
        except (OSError, ValueError, TypeError, AttributeError, ImportError):
            return None

    def _observe_load(self, original, args, kwargs):
        if self._observing:
            return original(*args, **kwargs)
        details = self._load_details(args, kwargs)
        if details is None:
            return original(*args, **kwargs)
        path, target = details
        before = set(self.cmd.get_names_of_type("object:molecule"))
        prior = self.record_for(target) if target in before else SourceRecord()
        self._observing += 1
        try:
            result = original(*args, **kwargs)
        finally:
            self._observing -= 1
        # Metadata failure must not turn a successful scientific file load into an error.
        try:
            if isinstance(result, (int, float)) and result < 0:
                return result
            after = set(self.cmd.get_names_of_type("object:molecule"))
            created = after - before
            for name in created:
                self.apply(name, SourceRecord((path,), True, "file_load"))
            if target in after and target not in created:
                self.apply(target, SourceRecord(_unique_paths(prior.paths + (path,)),
                                                prior.complete, "file_load"))
        except Exception as exc:
            print("[KyMol] Source tracking unavailable for this load: {}".format(type(exc).__name__))
        return result

    def _observe_memory_load(self, original, args, kwargs, command_name):
        if self._observing:
            return original(*args, **kwargs)
        parameter, index = _MEMORY_LOADERS[command_name]
        requested = kwargs.get(parameter, args[index] if len(args) > index else "")
        target = self.cmd.get_legal_name(str(requested).strip()) if requested else ""
        existing = target in self.cmd.get_names_of_type("object:molecule")
        prior = self.record_for(target) if existing else SourceRecord()
        self._observing += 1
        try:
            result = original(*args, **kwargs)
        finally:
            self._observing -= 1
        try:
            if isinstance(result, (int, float)) and result < 0:
                return result
            if existing and target in self.cmd.get_names_of_type("object:molecule"):
                # Retain known input paths for overwrite protection but disclose
                # that the resulting object also contains untraced memory data.
                self.apply(target, SourceRecord(prior.paths, False, "memory_data"))
        except Exception as exc:
            print("[KyMol] Source tracking unavailable for this load: {}".format(type(exc).__name__))
        return result

    def _install_hook(self, command_name, observer):
        original = getattr(self.cmd, command_name, None)
        if original is None:
            return

        def dispatch(callback, args, kwargs):
            # pymol2 proxies can bind a globally wrapped function to a separate
            # engine via _self. Observe that actual engine, never the global one.
            target_cmd = kwargs.get("_self", self.cmd)
            if target_cmd is not self.cmd:
                tracker = get_tracker(target_cmd)
                if command_name == "load":
                    return tracker._observe_load(callback, args, kwargs)
                return tracker._observe_memory_load(callback, args, kwargs, command_name)
            return observer(callback, args, kwargs)

        @wraps(original)
        def tracked_api(*args, **kwargs):
            return dispatch(original, args, kwargs)

        setattr(self.cmd, command_name, tracked_api)
        self._patches.append(("api:" + command_name, original, tracked_api))
        keyword = getattr(self.cmd, "keyword", None)
        if keyword is not None and command_name in keyword:
            original_entry = keyword[command_name]
            parser_command = original_entry[0]

            @wraps(parser_command)
            def tracked_parser(*args, **kwargs):
                return dispatch(parser_command, args, kwargs)

            replacement = list(original_entry)
            replacement[0] = tracked_parser
            keyword[command_name] = replacement
            self._patches.append(("parser:" + command_name, original_entry, replacement))

    def install(self) -> None:
        """Observe this cmd's API and parser loaders without changing their behavior."""
        if self._installed:
            return
        if getattr(self.cmd, "load", None) is None:
            return
        self._install_hook("load", self._observe_load)
        for command_name in _MEMORY_LOADERS:
            def observe(original, args, kwargs, name=command_name):
                return self._observe_memory_load(original, args, kwargs, name)
            self._install_hook(command_name, observe)
        self._installed = True

    def uninstall(self) -> None:
        """Restore only entries still owned by this tracker (useful in isolated tests)."""
        for kind, original, replacement in reversed(self._patches):
            surface, name = kind.split(":", 1)
            if surface == "api" and getattr(self.cmd, name) is replacement:
                setattr(self.cmd, name, original)
            elif surface == "parser" and self.cmd.keyword.get(name) is replacement:
                self.cmd.keyword[name] = original
        self._patches.clear()
        self._installed = False


def get_tracker(cmd) -> SourceTracker:
    # cmd instances own their tracker; no global object-name cache can leak sessions.
    # pymol2.Cmd.__getattr__ forwards missing attributes to the global cmd module;
    # consulting it here would accidentally reuse another engine's tracker.
    tracker = vars(cmd).get("_kymol_source_tracker")
    if tracker is None:
        tracker = SourceTracker(cmd)
        setattr(cmd, "_kymol_source_tracker", tracker)
    return tracker
