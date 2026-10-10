#!/usr/bin/env python3
# PS5 Vulkan - upload a built title folder over FTP.
# Copyright (C) 2026 Mihawk-99
# SPDX-License-Identifier: GPL-3.0-or-later
"""Upload dist/<TITLE_ID>/ to /data/homebrew/<TITLE_ID>/ on the console.

tools/deploy.sh builds and uploads the runner; this uploads any folder another
build produced (tools/build-radv-title.sh's dist/PPSA99014), with the same
discipline: each file goes up under a hidden .upload name and replaces its
destination only once complete, eboot.bin and sce_sys/param.json are published
last, and files already identical on the console (same size) are skipped
unless --all or named with --always. Connection settings are tools/ps5_console.py's (.env).

Fully close the title first: this refuses to run while the console reports a
running application.
"""

import argparse
import sys
from ftplib import FTP, error_perm, error_reply
from pathlib import Path
from posixpath import join

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ps5_console  # noqa: E402

LAST = ("eboot.bin", "sce_sys/param.json")


def remote_size(ftp, path):
    try:
        return ftp.size(path)
    except error_perm:
        return None


def ensure_directory(ftp, path, made):
    parts = [p for p in path.split("/") if p]
    current = ""
    for part in parts:
        current += "/" + part
        if current in made:
            continue
        try:
            ftp.mkd(current)
        except error_perm as error:
            if not str(error).startswith("550"):
                raise
        made.add(current)


def upload(ftp, local, remote, made):
    ensure_directory(ftp, remote.rsplit("/", 1)[0], made)
    temporary = join(remote.rsplit("/", 1)[0], "." + remote.rsplit("/", 1)[1] + ".upload")
    with open(local, "rb") as source:
        ftp.storbinary(f"STOR {temporary}", source, blocksize=1 << 20)
    # The console's ftpsrv completes a deletion with 226, which ftplib calls
    # an error; any 2xx is a success (as tools/deploy.sh accepts).
    try:
        ftp.sendcmd(f"DELE {remote}")
    except error_perm:
        pass
    except error_reply as reply:
        if not str(reply).startswith("2"):
            raise
    ftp.rename(temporary, remote)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", help="the built title folder, dist/<TITLE_ID>")
    parser.add_argument("--all", action="store_true", help="upload files already on the console too")
    parser.add_argument("--always", action="append", default=[], metavar="NAME",
                        help="a file (relative to the folder) to upload even when its size matches")
    args = parser.parse_args()

    folder = Path(args.folder)
    title = folder.name
    if not (folder / "eboot.bin").is_file() or not (folder / "sce_sys/param.json").is_file():
        raise SystemExit(f"{folder} is not a built title folder")
    settings = ps5_console.load_settings()
    status = ps5_console.ps5vkctl_command(settings, "procs", timeout=20)
    if " count=0 " not in status + " ":
        raise SystemExit(f"the console is running an application ({status.strip()}); not deploying")

    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    ordered = [f for f in files if f not in LAST] + [f for f in LAST if f in files]
    base = f"/data/homebrew/{title}"
    made = set()
    with FTP() as ftp:
        ftp.connect(settings["host"], settings["ftp_port"], timeout=30)
        ftp.login(settings["ftp_user"], settings["ftp_password"] or "codex")
        ftp.voidcmd("TYPE I")
        sent = skipped = 0
        for name in ordered:
            local = folder / name
            remote = join(base, name)
            if not args.all and name not in LAST and name not in args.always and remote_size(ftp, remote) == local.stat().st_size:
                skipped += 1
                continue
            upload(ftp, local, remote, made)
            sent += 1
            print(f"  {name}  {local.stat().st_size:,} bytes")
        for name in LAST:
            local = folder / name
            stored = remote_size(ftp, join(base, name))
            # The console re-signs a SELF as it stores it, and the stored file
            # is larger (PS5_RetroArch's tools/deploy-title.py reads such files
            # back); anything else arrives byte for byte.
            signed = local.read_bytes()[:4] in (bytes.fromhex("4f153d1d"), bytes.fromhex("5414f5ee"))
            if stored is None or (stored < local.stat().st_size if signed else stored != local.stat().st_size):
                raise SystemExit(f"{name} did not arrive whole ({stored} bytes stored)")
    print(f"==> {title}: {sent} files sent, {skipped} already there")


if __name__ == "__main__":
    main()
