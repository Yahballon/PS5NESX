#!/usr/bin/env python3
# PS5 Vulkan - launch a deployed title, capture its klog and fetch its results.
# Copyright (C) 2026 Mihawk-99
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a deployed title once and keep what it said.

The runner has its own battery loop (tools/ps5_console.py battery); this is
for titles that simply run a program and end, such as the RADV title
(PPSA99014): it checks the console is idle, arms the klog capture (keeping the
service's replayed backlog out of the result), launches the title through the
control payload, captures klog until a line matches --until or --timeout
passes, closes the title if it is still running, and fetches the files named
by --fetch from the title's folder. Exit status: 0 when --until matched, 3
when it did not.
"""

import argparse
import datetime
import re
import socket
import sys
import time
from ftplib import FTP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ps5_console  # noqa: E402

# The records the console writes when a title's process dies.
CRASH = re.compile(r"A user thread receives a fatal signal|mDBG: Sending signal|GPU_FAULT|gpu fault", re.I)


def symbolise(log_path, elf):
    """Print a crash record's rip and backtrace as functions and lines.

    The title's executable loads at 0x400000 (the record's "dynamic libraries"
    list gives /app0/eboot.bin's xotext base) and the ELF is linked at 0."""
    import subprocess
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    if "fatal signal" not in text:
        return
    record = text[text.index("fatal signal"):]
    base_match = re.search(r"/app0/eboot\.bin\s*\n#\s*xotext:\s*([0-9a-f]+):", record)
    base = int(base_match.group(1), 16) if base_match else 0x400000
    addresses = []
    rip = re.search(r"# rip: ([0-9a-f]+)", record)
    if rip:
        addresses.append(("rip", int(rip.group(1), 16)))
    backtrace = record[record.find("# backtrace:"):record.find("# dynamic libraries:")]
    for value in re.findall(r"^# ([0-9a-f]{16})$", backtrace, re.M):
        addresses.append(("from", int(value, 16)))
    reason = re.search(r"# reason: (.*)", record)
    fault = re.search(r"# fault address: ([0-9a-f]+)", record)
    print(f"crash: {reason.group(1) if reason else '?'} at {fault.group(1) if fault else '?'}")
    for kind, address in addresses:
        if not base <= address < base + 0x10000000:
            print(f"  {kind} {address:#x}")
            continue
        out = subprocess.run(["llvm-addr2line", "-f", "-C", "-i", "-e", elf, hex(address - base)],
                             capture_output=True, text=True).stdout.split("\n")
        frames = [f"{out[i]} ({out[i + 1].split('/src/')[-1]})" for i in range(0, len(out) - 1, 2)]
        print(f"  {kind} {address:#x}: " + " <- ".join(frames))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("title")
    parser.add_argument("--until", required=True, help="regex a klog line matches when the run is over")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", help="klog file (default Klog_Logs/<title>-<time>.log)")
    parser.add_argument("--fetch", action="append", default=[], help="file in the title folder to download")
    parser.add_argument("--echo", default="", help="regex of klog lines to print while capturing")
    parser.add_argument("--elf", help="the linked ELF (before signing), to symbolise a crash's backtrace")
    parser.add_argument("--exit-grace", type=float, default=30.0,
                        help="seconds a title that finished gets to exit on its own before it is closed")
    args = parser.parse_args()
    ended, _output, _fetched = run_title(args.title, args.until, args.timeout, args.output, args.fetch,
                                         args.echo, args.elf, exit_grace=args.exit_grace)
    return 0 if ended == "finished" else 3


def run_title(title, until_pattern, timeout, output=None, fetch=(), echo_pattern="", elf=None, on_line=None,
              stall=None, progressing=None, activity=None, exit_grace=30.0):
    """Run a deployed title once; returns (how it ended, the klog file, the
    fetched files). on_line, if given, sees every klog line as it arrives.
    With stall, a run whose klog has had no line of its own (one matching the
    regex activity, or any line without it) for that many seconds has
    stalled, unless progressing() (asked then) says it is still moving; a
    stalled title is closed. The system writes klog lines of its own every few
    seconds, so activity is what makes the stall detectable."""
    args = argparse.Namespace(title=title, until=until_pattern, timeout=timeout, output=output,
                              fetch=list(fetch), echo=echo_pattern, elf=elf, exit_grace=exit_grace)
    if not re.fullmatch(r"PPSA\d{5}", args.title):
        raise SystemExit("TITLE must look like PPSA12345")

    settings = ps5_console.load_settings()
    status = ps5_console.ps5vkctl_command(settings, "procs", timeout=20)
    if " count=0 " not in status + " ":
        raise SystemExit(f"the console is running an application ({status}); not launching")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path(__file__).resolve().parent.parent
    output = Path(args.output) if args.output else root / "Klog_Logs" / f"{args.title}-{stamp}.log"
    output.parent.mkdir(parents=True, exist_ok=True)
    until = re.compile(args.until)
    echo = re.compile(args.echo) if args.echo else None
    matched = False
    ended = None
    with socket.create_connection((settings["host"], settings["klog_port"]), timeout=10) as klog, \
            output.open("w", encoding="utf-8", newline="\n") as log:
        # The service replays its buffer on connect: drain it first.
        klog.settimeout(0.3)
        drain_until = time.monotonic() + 3.0
        while time.monotonic() < drain_until:
            try:
                if not klog.recv(65536):
                    raise SystemExit("klog closed")
            except socket.timeout:
                break
        reply = ps5_console.ps5vkctl_command(settings, f"launch {args.title}", timeout=120)
        print(f"launch: {reply}", flush=True)
        log.write(f"# launch {args.title}: {reply}\n")
        # The run is over at the first of: the --until line, a crash record,
        # or the console no longer running the title (asked once a second).
        # The timeout is only the watchdog for a hang.
        klog.settimeout(0.25)
        pending = b""
        started = time.monotonic()
        deadline = started + args.timeout
        next_poll = started + 2.0
        last_line = started
        ended = None
        while time.monotonic() < deadline and ended is None:
            try:
                chunk = klog.recv(65536)
            except socket.timeout:
                chunk = b""
            pending += chunk
            *lines, pending = pending.split(b"\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace").rstrip("\r")
                if activity is None or re.search(activity, line):
                    last_line = time.monotonic()
                log.write(line + "\n")
                if echo and echo.search(line):
                    print(line, flush=True)
                if on_line:
                    on_line(line)
                if until.search(line):
                    matched = True
                    ended = ended or "finished"
                elif CRASH.search(line):
                    ended = ended or "crashed"
            log.flush()
            if ended is None and time.monotonic() >= next_poll:
                next_poll = time.monotonic() + 1.0
                if " count=0 " in ps5_console.ps5vkctl_command(settings, "procs", timeout=10) + " ":
                    ended = "exited"
            if ended is None and stall and time.monotonic() - last_line > stall:
                if progressing and progressing():
                    last_line = time.monotonic()
                else:
                    ended = "stalled"
        print(f"run {ended or 'timed out'} after {time.monotonic() - started:.1f} s", flush=True)
        # What follows the end: a crash record's registers and backtrace.
        klog.settimeout(0.25)
        tail_until = time.monotonic() + (2.0 if ended == "crashed" else 0.5)
        while time.monotonic() < tail_until:
            try:
                chunk = klog.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            log.write(chunk.decode("utf-8", "replace"))
    print(f"klog: {output}")
    # A title that returns from main takes the console's known exit SIGSYS
    # after its last line; only a crash that ended the run is worth reading.
    if args.elf and ended != "finished":
        symbolise(output, args.elf)

    # A finished title is given time to exit on its own (its teardown can take seconds; killing
    # it mid-teardown, or while it renders at 8K, preceded console power-offs). The kill is
    # the watchdog for one that never exits.
    status = ps5_console.ps5vkctl_command(settings, "procs", timeout=20)
    exit_deadline = time.monotonic() + (args.exit_grace if ended == "finished" else 0.0)
    while " count=0 " not in status + " " and time.monotonic() < exit_deadline:
        time.sleep(0.5)
        status = ps5_console.ps5vkctl_command(settings, "procs", timeout=20)
    if " count=0 " not in status + " ":
        print(f"closing: {ps5_console.ps5vkctl_command(settings, f'kill {args.title}', timeout=60)}")
    elif ended == "finished":
        print("closing: the title exited on its own")

    fetched = []
    for name in args.fetch:
        destination = output.with_name(output.stem + "-" + name.replace("/", "_"))
        with FTP() as ftp:
            ftp.connect(settings["host"], settings["ftp_port"], timeout=30)
            ftp.login(settings["ftp_user"], settings["ftp_password"] or "codex")
            with destination.open("wb") as sink:
                ftp.retrbinary(f"RETR /data/homebrew/{args.title}/{name}", sink.write)
        fetched.append(destination)
        print(f"fetched: {destination}")
    return ended or "timed out", output, fetched


if __name__ == "__main__":
    sys.exit(main())
