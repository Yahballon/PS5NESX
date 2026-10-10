"""Check or package PS5NES source for publication (AI-assisted).

python tools/prepare_source.py --write     Refresh the source manifest.
python tools/prepare_source.py            Verify it without changing files.
python tools/prepare_source.py --archive   Verify and create a source ZIP.

Hashes cover checkout bytes. Refresh after line-ending conversion if needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SOURCE-MANIFEST.json"
VERSION = "v1.0.0.9"
BLOCKED = {".elf", ".self", ".prx", ".pkg", ".nes", ".unf", ".unif",
           ".iso", ".chd", ".bios", ".rom", ".sav", ".state", ".pyc", ".pyo"}


def source_files():
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
    ).decode("utf-8")
    files = []
    for name in sorted(set(filter(None, output.split("\0")))):
        path = ROOT / name
        if not path.is_file():
            continue  # Deleted files awaiting a commit.
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise SystemExit(f"Review linked file before publication: {name}")
        parts = Path(name).parts
        if any(part in {".git", ".deps", ".cache", "__pycache__"} for part in parts):
            raise SystemExit(f"Private/generated file in source inventory: {name}")
        if path.suffix.lower() in BLOCKED or path.name == ".env" or (
            path.name.startswith(".env.") and path.name not in {".env.example", ".env.sample"}
        ):
            raise SystemExit(f"Private/generated/game file in source inventory: {name}")
        files.append(name)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    names = source_files()
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in names if name != MANIFEST.name}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.write:
        previous = data["files"]
        data["project"] = "PS5NES"
        data["version"] = VERSION + " by YAHBALLON"
        data["files"] = {name: hashes[name] for name in previous if name in hashes}
        data["files"].update({name: value for name, value in hashes.items() if name not in previous})
        MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif data["files"] != hashes or data.get("version") != VERSION + " by YAHBALLON":
        raise SystemExit("Source manifest is stale. Review changes and run with --write.")
    print(f"Verified {len(hashes)} source files (AI-assisted).")
    if args.archive:
        output = ROOT / "release" / f"PS5NES-source-{VERSION}-by-YAHBALLON.zip"
        output.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(ROOT / name, "PS5NES/" + name)
        with zipfile.ZipFile(output) as archive:
            bad = archive.testzip()
            if bad:
                raise SystemExit(f"Archive verification failed: {bad}")
        checksum = hashlib.sha256(output.read_bytes()).hexdigest()
        output.with_suffix(".zip.sha256").write_text(
            f"{checksum}  {output.name}\n", encoding="utf-8")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
