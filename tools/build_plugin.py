"""Build a deterministic, create-only PyMOL plugin ZIP from an explicit allowlist.

Usage: python tools/build_plugin.py [--output path/to/KyMol-version.zip]
No Git tree, tests, sessions, private structures, or installed files are packaged.
"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import zipfile


def build(output=None):
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "KYMol" / "__init__.py").read_text(encoding="utf-8"))
    version = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "__version__"
                           for target in node.targets))
    destination = Path(output) if output else root / "dist" / ("KyMol-" + version + ".zip")
    files = [root / "KYMol" / name for name in
             ("__init__.py", "core.py", "ui.py", "provenance.py")]
    files += [root / name for name in ("LICENSE", "README.md", "INSTALLATION.zh-CN.md", "VERIFICATION.md")]
    manifest = []
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            data = path.read_bytes()
            member = "KYMol/" + path.name
            info = zipfile.ZipInfo(member, date_time=(2026, 9, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            manifest.append({"path": member, "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest()})
    payload = stream.getvalue()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise FileExistsError("Refusing to overwrite a different candidate package: " + str(destination))
    else:
        with destination.open("xb") as handle:
            handle.write(payload)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == [entry["path"] for entry in manifest]
    receipt = {"version": version, "package": destination.name, "bytes": len(payload),
               "sha256": hashlib.sha256(payload).hexdigest(), "files": manifest}
    receipt_path = destination.with_suffix(".manifest.json")
    serialized = json.dumps(receipt, indent=2) + "\n"
    if receipt_path.exists() and receipt_path.read_text(encoding="utf-8") != serialized:
        raise FileExistsError("Refusing to overwrite a different package receipt: " + str(receipt_path))
    receipt_path.write_text(serialized, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
