#!/usr/bin/env python3
# PS5 Vulkan - run Vulkan CTS cases on the console (PPSA99015).
# Copyright (C) 2026 Mihawk-99
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a selection of the Vulkan CTS on the console and summarise it.

The CTS title (tools/build-cts-title.sh) reads its arguments from
/app0/cts/args.txt. This writes that file for a case pattern (--case) or a
case list (uploaded as /app0/cts/caselist.txt), runs the title through
tools/run-title.py and reads the QPA log it fetches back.

The flags are the standard ones plus these for the console: the log is not
flushed after every write (a write() to the console's storage costs about
3.3 ms, which made a 322-message case take 11.5 s instead of 17 ms); the CTS's
own crash handler is off, because the title's platform reports a crash itself
(the case logged as Crash, the log flushed, the fault and a stack scan in
klog); and the CTS's watchdog is on, so a case that hangs is logged as
Timeout.

With --mustpass (groups of the pinned mustpass list) or --caselist, the cases
run in batches, and a batch that ends early (a crash, a hang, the title
exiting) is resumed after the case that ended it. Every result goes to
build/cts-runs/<run>/results.tsv as it is read, so --run with the same name
resumes an interrupted run.

Each invocation first uploads dist/PPSA99015 as last built (eboot.bin and
cts/build.txt always, other files when their size differs), so a run never
uses an older title than the one built; a batched run notes the build it ran
(cts/build.txt) in its batches.log. --no-deploy runs what the console has.

A file named pause in a batched run's directory holds the run before its next
launch, with the console idle, until the file is removed; the run then
uploads the title again (it may have been rebuilt meanwhile) and goes on.

Exit status: 0 when every case passed or is not supported, 1 when a case
failed, 3 when a single run (--case) did not end on its own.
"""

import argparse
import collections
import datetime
import io
import re
import subprocess
import sys
import time
from ftplib import FTP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ps5_console  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_title", Path(__file__).resolve().parent / "run-title.py")
run_title_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_title_module)

ROOT = Path(__file__).resolve().parent.parent
TITLE = "PPSA99015"
CTS_FORK = ROOT.parent / "PS5_VK-GL-CTS"
MUSTPASS = CTS_FORK / "external/vulkancts/mustpass/main/vk-default"
CASE_LINE = re.compile(r"\[cts\] Test case '([^']+)'\.\.")
CRASH_LINE = re.compile(r"\[cts\] Crash in '([^']*)'")
GOOD = ("Pass", "NotSupported", "QualityWarning", "CompatibilityWarning", "Waiver")


def ftp_session(settings):
    ftp = FTP()
    ftp.connect(settings["host"], settings["ftp_port"], timeout=30)
    ftp.login(settings["ftp_user"], settings["ftp_password"] or "codex")
    return ftp


def upload(settings, files):
    with ftp_session(settings) as ftp:
        for name, text in files.items():
            ftp.storbinary(f"STOR /data/homebrew/{TITLE}/cts/{name}", io.BytesIO(text.encode()))


def parse_qpa(text):
    """The cases a QPA log holds, in order: (name, status, detail); a case
    whose result was never written has the status None."""
    cases = []
    for block in re.split(r"\n#beginTestCaseResult ", "\n" + text)[1:]:
        name, _, body = block.partition("\n")
        terminated = re.search(r"#terminateTestCaseResult (\w+)", body)
        status = re.search(r'StatusCode="(\w+)">([^<]*)<', body)
        if terminated:
            cases.append((name.strip(), terminated.group(1), "terminated"))
        elif "#endTestCaseResult" in body and status:
            cases.append((name.strip(), status.group(1), status.group(2).strip()))
        else:
            cases.append((name.strip(), None, ""))
    return cases


KLOG_RESULT = re.compile(r"\[cts\]   (\w+) \((.*)\)$")
ASYNC_GPU_FAULT = re.compile(r"GPU_FAULT_\w*ASYNC")


def parse_klog(path):
    """The results klog printed, in order: (name, status, detail). A killed
    title loses what it had not flushed of its QPA log, but klog kept each
    result line as the case ended (it can drop lines under load)."""
    cases = []
    current = None
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return cases, False
    async_fault = False
    for line in lines:
        async_fault |= bool(ASYNC_GPU_FAULT.search(line))
        match = CASE_LINE.search(line)
        if match:
            current = match.group(1)
            continue
        match = KLOG_RESULT.match(line)
        if match and current:
            cases.append((current, match.group(1), match.group(2).strip()))
            current = None
    return cases, async_fault


def run_once(settings, args, selection, caselist=None):
    """One launch of the title. Returns how the run ended, its cases from the
    QPA log, the last case klog saw start, and the klog file."""
    flags = [
        "--deqp-log-filename=/app0/cts/TestResults.qpa",
        "--deqp-archive-dir=/app0/cts",
        f"--deqp-log-images={args.log_images}",
        "--deqp-log-shader-sources=disable",
        "--deqp-shadercache=disable",
        f"--deqp-log-flush={args.log_flush}",
        # The title reports a crash itself (the CTS's handler hung on the
        # console): the case is logged as Crash and the fault goes to klog.
        "--deqp-crashhandler=disable",
        "--deqp-watchdog=enable",
    ]
    files = {}
    if caselist is not None:
        files["caselist.txt"] = "\n".join(caselist) + "\n"
        flags.append("--deqp-caselist-file=/app0/cts/caselist.txt")
    else:
        flags.append(f"--deqp-case={selection}")
    flags += args.extra
    flags += [f"env {setting}" for setting in args.env]
    if args.stderr_file:
        flags.append("env CTS_STDERR_FILE=/app0/cts/stderr.txt")
    files["args.txt"] = "\n".join(flags) + "\n"
    upload(settings, files)

    state = {"case": None, "crashed": None}

    def on_line(line):
        match = CASE_LINE.search(line)
        if match:
            state["case"] = match.group(1)
            if args.verbose:
                print(f"  {match.group(1)}", flush=True)
        match = CRASH_LINE.search(line)
        if match and match.group(1):
            state["crashed"] = match.group(1)

    # klog can lag or drop lines under load; the log the CTS writes on the
    # console is the other sign of progress.
    qpa_size = {"bytes": -1}

    def progressing():
        with ftp_session(settings) as ftp:
            ftp.voidcmd("TYPE I")
            size = ftp.size(f"/data/homebrew/{TITLE}/cts/TestResults.qpa") or 0
        grew = size > qpa_size["bytes"]
        qpa_size["bytes"] = size
        return grew

    output = None
    if args.klog_dir:
        output = str(Path(args.klog_dir) / f"{TITLE}-{datetime.datetime.now():%Y%m%d-%H%M%S}.log")
    fetch = ["cts/TestResults.qpa"] + (["cts/stderr.txt"] if args.stderr_file else [])
    ended, klog, fetched = run_title_module.run_title(
        TITLE, r"\[cts\] run ends", args.timeout, output=output, fetch=fetch,
        elf=args.elf, on_line=on_line, stall=args.stall, progressing=progressing, activity=r"\[cts")
    qpa = fetched[0] if fetched else None
    if args.stderr_file and len(fetched) > 1:
        print(f"stderr: {fetched[1]}", flush=True)
    text = qpa.read_text(errors="replace") if qpa and qpa.exists() else ""
    # The title's own crash line names the case; klog's last case line is the
    # fallback (it can drop lines under load).
    return ended, parse_qpa(text), state["crashed"] or state["case"], klog


def summarise(counts):
    return "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def single_run(settings, args):
    ended, cases, running, _ = run_once(settings, args, args.case)
    counts = collections.Counter()
    unfinished = None
    for name, status, detail in cases:
        if status is None:
            unfinished = name
            continue
        counts[status] += 1
        if status not in GOOD or args.verbose:
            print(f"  {status:<14} {name}  {detail}")
    print(f"cases: {sum(counts.values())}  {summarise(counts)}")
    if ended != "finished":
        culprit = unfinished or running
        print(f"the run {ended}" + (f" in {culprit}" if culprit else ""))
        return 3
    return 0 if all(k in GOOD for k in counts) else 1


def mustpass_cases(groups):
    cases = []
    for group in groups:
        path = MUSTPASS / group
        files = sorted(path.rglob("*.txt")) if path.is_dir() else [MUSTPASS / f"{group}.txt"]
        for file in files:
            if not file.exists():
                raise SystemExit(f"no mustpass list {file}")
            cases += [line.strip() for line in file.read_text().splitlines() if line.strip()]
    return cases


def deploy_title(args, batches=None):
    """Upload the CTS title as last built, and note which build in batches."""
    if args.no_deploy:
        return
    subprocess.run([sys.executable, str(ROOT / "tools" / "deploy-title-folder.py"), str(ROOT / "dist" / TITLE),
                    "--always", "cts/build.txt"], check=True)
    build = ROOT / "dist" / TITLE / "cts" / "build.txt"
    if batches and build.exists():
        batches.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} deployed {build.read_text().strip()}\n")
        batches.flush()


def wait_while_paused(args, run_dir, batches):
    pause = run_dir / "pause"
    if not pause.exists():
        return
    batches.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} paused\n")
    batches.flush()
    print(f"paused until {pause} is removed", flush=True)
    while pause.exists():
        time.sleep(1)
    batches.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} resumed\n")
    batches.flush()
    deploy_title(args, batches)


def batch_run(settings, args, cases):
    run_dir = ROOT / "build" / "cts-runs" / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.tsv"
    done = {}
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            name, status = (line.split("\t") + [""])[:2]
            done[name] = status
    args.klog_dir = str(run_dir / "klog")
    Path(args.klog_dir).mkdir(exist_ok=True)
    with (run_dir / "batches.log").open("a") as batches:
        deploy_title(args, batches)

    wanted = set(cases)
    pending = [c for c in cases if c not in done]
    print(f"run {args.run}: {len(cases)} cases, {len(cases) - len(pending)} already done", flush=True)
    counts = collections.Counter(status for name, status in done.items() if name in wanted)
    batch_number = 0
    with results_path.open("a") as results, (run_dir / "batches.log").open("a") as batches:
        def record(name, status, detail):
            done[name] = status
            counts[status] += 1
            results.write(f"{name}\t{status}\t{detail.replace(chr(9), ' ').replace(chr(10), ' ')}\n")
            if status not in GOOD:
                print(f"  {status:<14} {name}  {detail}", flush=True)

        while pending:
            wait_while_paused(args, run_dir, batches)
            batch_number += 1
            batch = pending[:args.batch]
            started = time.monotonic()
            ended, qpa_cases, running, klog = run_once(settings, args, None, caselist=batch)
            in_batch = set(batch)
            unfinished = None
            terminated = False
            for name, status, detail in qpa_cases:
                if name not in in_batch or name in done:
                    continue
                if status is None:
                    unfinished = name
                else:
                    record(name, status, detail)
                    terminated |= detail == "terminated"
            # What the QPA log lost when the title was killed, klog kept.
            klog_cases, async_fault = parse_klog(klog) if klog else ([], False)
            if ended != "finished":
                for name, status, detail in klog_cases:
                    if name in in_batch and name not in done:
                        record(name, status, detail)
            # A case the title logged as Crash or Timeout is what ended the run.
            if ended != "finished" and not terminated:
                # The case that ended the run: the one the title's crash line or
                # klog last named, else the one the log left open (with the log
                # not flushed per write, that is only where the file was cut),
                # else the first with no result, so every launch settles at
                # least one case.
                culprit = next((c for c in (running, unfinished) if c in in_batch and c not in done), None)
                if culprit is None:
                    culprit = next((c for c in batch if c not in done), None)
                if culprit is not None:
                    status = "Timeout" if ended in ("stalled", "timed out") else "Crash"
                    # An asynchronous GPU fault reaches the title after the draw
                    # that caused it: an earlier case may be the one to blame.
                    note = "; asynchronous GPU fault" if async_fault else ""
                    record(culprit, status, f"the run {ended} (runner{note})")
            elif not any(c in done for c in batch):
                # A finished run that settled nothing would repeat forever.
                record(batch[0], "Missing", "not in the log of a finished run (runner)")
            # A run the CTS ended early (it stops after a fatal result, such
            # as running out of device memory) leaves the rest of its batch to
            # the next launch.
            results.flush()
            seconds = time.monotonic() - started
            pending = [c for c in pending if c not in done]
            line = (f"batch {batch_number}: {len(batch)} cases, run {ended} after {seconds:.0f} s; "
                    f"{len(cases) - len(pending)}/{len(cases)} done: {summarise(counts)}")
            print(line, flush=True)
            batches.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {line} klog={klog}\n")
            batches.flush()
    print(f"run {args.run} complete: {summarise(counts)}")
    return 1 if any(k not in GOOD for k in counts) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", help="a case pattern, as --deqp-case takes it (one launch)")
    selection.add_argument("--caselist", help="a file of case names, one a line (batched)")
    selection.add_argument("--mustpass", nargs="+", metavar="GROUP",
                           help="groups of the pinned mustpass list (vk-default/<GROUP>.txt, or a "
                                "directory of them), batched")
    parser.add_argument("--run", help="the batched run's name (default: the date and time); an "
                                      "existing name resumes it")
    parser.add_argument("--batch", type=int, default=20000, help="cases a launch (batched runs)")
    parser.add_argument("--timeout", type=float, default=14400.0, help="watchdog for one launch, seconds")
    parser.add_argument("--stall", type=float, default=330.0,
                        help="seconds with no CTS klog line and the log not growing that end a launch; "
                             "above the CTS's own 300 s limit for a case, which it enforces itself")
    parser.add_argument("--log-flush", choices=("enable", "disable"), default="disable",
                        help="flush the log after every write (--deqp-log-flush)")
    parser.add_argument("--log-images", choices=("enable", "disable"), default="disable",
                        help="log result images (--deqp-log-images)")
    parser.add_argument("--elf", default="build/cts/llvm-pie.elf", help="the linked ELF, to symbolise a crash")
    parser.add_argument("--extra", action="append", default=[], help="another deqp argument")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE",
                        help="an environment variable for the driver (RADV_DEBUG=...)")
    parser.add_argument("--stderr-file", action="store_true",
                        help="send the driver's stderr and stdout to a file on the console and fetch it (klog drops "
                             "lines under large dumps such as RADV_DEBUG=shaders)")
    parser.add_argument("--verbose", action="store_true", help="print every case")
    parser.add_argument("--no-deploy", action="store_true",
                        help="run the title the console has instead of uploading dist/PPSA99015 first")
    args = parser.parse_args()
    args.klog_dir = None

    settings = ps5_console.load_settings()
    if args.case:
        deploy_title(args)
        return single_run(settings, args)
    if args.mustpass:
        cases = mustpass_cases(args.mustpass)
    else:
        cases = [line.strip() for line in Path(args.caselist).read_text().splitlines() if line.strip()]
    args.run = args.run or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return batch_run(settings, args, cases)


if __name__ == "__main__":
    sys.exit(main())
