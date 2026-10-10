#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prepare a complete timed engineering queue; never run or certify tests."""
import argparse
from collections import Counter
import hashlib
import importlib
import json
import math
import re
import fnmatch
from pathlib import Path

PREPARE = importlib.import_module("prepare-cts-shard")
ROOT = Path(__file__).resolve().parents[1]
MUSTPASS = ROOT / "third_party/VK-GL-CTS/external/openglcts/data/gl_cts/data/mustpass/gl/khronos_mustpass/main/gl33-main.txt"


def family(name):
    parent, leaf = name.rsplit('.', 1) if '.' in name else ('', name)
    # DSA buffer timings do not predict texture allocation/transfer workloads.
    return parent + '.' + leaf.split('_')[0] if parent.endswith('.direct_state_access') else parent


def resume_history(cases, ledger, candidate=None, retest=()):
    """Engineering resume only; retain skip/warning dispositions and build identity."""
    completed, isolated = {}, set()
    for config, rows in ledger.get('cases', {}).items():
        for name, row in rows.items():
            if name not in cases:
                continue
            receipt = ledger.get('receipts', {}).get(row.get('receipt'), {})
            peak = receipt.get('heap_peak_bytes')
            # ponytail: receipt-wide quarantine, not additive case memory; refine with per-case telemetry if needed.
            if receipt.get('heap_failures') or (peak is not None and peak >= 64 * 1024**2):
                isolated.add(name)
            if (row.get('status') not in {'Pass', 'NotSupported', 'QualityWarning',
                                         'CompatibilityWarning', 'CapabilityWarning'} or
                any(fnmatch.fnmatchcase(name, pattern) for pattern in retest) or
                not re.fullmatch(r'[0-9a-f]{64}', receipt.get('eboot_sha256', '')) or
                (candidate and receipt.get('eboot_sha256') != candidate) or
                receipt.get('configuration') != int(config) or
                not receipt.get('ordered_prefix') or not receipt.get('entered') or
                receipt.get('teardown') != 'runtime-layers-released' or
                receipt.get('post_health') is not True or
                not (receipt.get('lock_released') is True or receipt.get('dedicated_console') is True)):
                continue
            completed.setdefault(config, {})[name] = dict(row, eboot_sha256=receipt['eboot_sha256'])
    return completed, isolated


def plan(cases, history, smoke, budget=120, startup=15, margin=1.5, unknown=30,
         configurations=range(4), family_estimates=False, completed=None, isolated=()):
    configurations = tuple(configurations)
    if (not configurations or len(set(configurations)) != len(configurations) or
            any(type(c) is not int or c not in range(4) for c in configurations)):
        raise ValueError("invalid configurations")
    if (not cases or len(cases) != len(set(cases)) or not set(smoke) <= set(cases) or
            any(not math.isfinite(v) for v in (budget, startup, margin, unknown)) or
            not (budget > startup >= 0 and margin >= 1 and unknown > 0)):
        raise ValueError("invalid inventory or time budget")
    capacity = (budget - startup) / margin
    shards = []
    for config in configurations:
        pending = [name for name in cases if name not in (completed or {}).get(str(config), {})]
        rows = history.get(str(config), {})
        timings, fallback, previous_failures = {}, set(), set()
        for name in cases:
            row = rows.get(name, {})
            value = row.get("seconds")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                      not math.isfinite(value) or value < 0):
                raise ValueError("invalid timing: " + name)
            if row.get("status") in {"Pass", "NotSupported"} and value is not None:
                timings[name] = value
            else:
                # No credit for history; failed/incomplete durations cannot estimate a passing run.
                fallback.add(name)
                if row and row.get("status") not in {"Pass", "NotSupported"}:
                    previous_failures.add(name)
        samples = {}
        for name, seconds in timings.items():
            if rows[name].get("status") == "Pass":
                samples.setdefault(family(name), []).append(seconds)
        # Scheduling hints only: unmeasured cases still require execution.
        estimates = {name: max(0.001, 4 * max(samples[family(name)]))
                     for name in fallback if family_estimates and name not in previous_failures
                     and len(samples.get(family(name), [])) >= 3}
        costs = {name: timings.get(name, estimates.get(name, unknown)) for name in cases}
        groups = {}
        for name in pending:
            seconds = costs[name]
            lane = ("long" if seconds > capacity else "previous-failure" if name in previous_failures else
                    "memory-heavy" if name in isolated else "smoke" if name in smoke else
                    "discovery" if name in fallback and name not in estimates else "bulk")
            # Fast groups share a launch; unknown families and risky cases stay separate.
            groups.setdefault((lane, '' if lane == 'bulk' else family(name)), []).append(name)
        for (lane, group_family), remaining in groups.items():
            position = 0
            while position < len(remaining):
                if lane in {"long", "previous-failure", "memory-heavy"}:
                    selected = remaining[position:position + 1]
                    seconds = costs[selected[0]]
                else:
                    # One ordered pass; rebuilding family timings per shard is quadratic.
                    selected, seconds = [], 0.0
                    end = position
                    while end < len(remaining):
                        name = remaining[end]
                        cost = costs[name]
                        if selected and seconds + cost > capacity:
                            break
                        selected.append(name)
                        seconds += cost
                        end += 1
                observation = max(5, math.ceil(startup + margin * seconds))
                shard_families = list(dict.fromkeys(family(name) for name in selected))
                shards.append(dict(configuration=config, lane=lane,
                    family=shard_families[0] if len(shard_families) == 1 else 'mixed',
                    families=shard_families, cases=selected,
                    estimated_test_seconds=round(seconds, 6), observation_seconds=observation,
                    needs_duration_approval=observation > budget,
                    exceeds_runner_limit=observation > 3600,
                    unknown_timings=sum(name in fallback for name in selected),
                    family_estimates=sum(name in estimates for name in selected)))
                position += len(selected)
    priorities = {"previous-failure": 0, "smoke": 1, "memory-heavy": 2, "bulk": 3, "discovery": 4, "long": 5}
    shards.sort(key=lambda row: (priorities[row["lane"]], row["configuration"],
                                -len(row["cases"]) if row["lane"] == "bulk" else 0))
    for config in configurations:
        covered = Counter(name for row in shards if row["configuration"] == config for name in row["cases"])
        if covered != Counter(name for name in cases if name not in (completed or {}).get(str(config), {})):
            raise ValueError("lost or duplicated case in schedule")
    for index, row in enumerate(shards):
        row["id"] = f'{index:04d}-config{row["configuration"]}-{row["lane"]}'
    return shards


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timings", type=Path, action="append", default=[],
                        help="inventory JSONs, oldest first; scheduling hints, never acceptance")
    parser.add_argument("--output", type=Path, required=True, help="new directory; never overwritten")
    parser.add_argument("--mustpass", type=Path, default=MUSTPASS)
    parser.add_argument("--smoke-suite", default="smoke")
    parser.add_argument("--manifest-only", action="store_true",
                        help="keep selections/hashes in plan.json; materialize only the next shard")
    parser.add_argument("--budget-seconds", type=float, default=120)
    parser.add_argument("--startup-seconds", type=float, default=15)
    parser.add_argument("--margin", type=float, default=1.5)
    parser.add_argument("--configuration", type=int, choices=range(4), action="append",
                        help="schedule only these configurations; default all four")
    parser.add_argument("--family-estimates", action="store_true",
                        help="estimate unknown siblings from at least three passing cases")
    parser.add_argument('--resume', choices=('candidate', 'discovery'),
                        help='exclude clean completed receipts; discovery may defer older-build results, never inherit acceptance')
    parser.add_argument('--candidate-sha256', help='required for candidate-only resume')
    parser.add_argument('--retest', action='append', default=[], help='force affected-case glob back into the queue')
    parser.add_argument('--isolate', action='append', default=[], help='run matching memory-heavy cases alone')
    args = parser.parse_args()
    try:
        cases = args.mustpass.read_text().splitlines()
        suites = json.loads((ROOT / "tests/ps5/cts-regressions.json").read_text())
        smoke = PREPARE.select_cases(cases, suites[args.smoke_suite])
        if args.resume == 'candidate' and not re.fullmatch(r'[0-9a-f]{64}', args.candidate_sha256 or ''):
            raise ValueError('candidate resume requires a lowercase executable SHA-256')
        if args.candidate_sha256 and args.resume != 'candidate':
            raise ValueError('candidate SHA-256 requires --resume candidate')
        history, sources, receipts = {}, [], {}
        for path in args.timings:
            raw = path.read_bytes()
            ledger = json.loads(raw)
            if ledger.get("scope") != "development-history-not-release-certification":
                raise ValueError("expected a CTS inventory ledger: " + str(path))
            for config, rows in ledger["cases"].items():
                # Namespace receipt IDs so ledgers from different directories cannot collide.
                history.setdefault(config, {}).update({name: dict(row, receipt=f'{len(sources)}:{row.get("receipt")}')
                                                       for name, row in rows.items()})
            receipts.update({f'{len(sources)}:{key}': row for key, row in ledger.get('receipts', {}).items()})
            sources.append(dict(file=path.name, sha256=hashlib.sha256(raw).hexdigest()))
        configurations = args.configuration if args.configuration is not None else range(4)
        completed, isolated = resume_history(set(cases), dict(cases=history, receipts=receipts),
                                             args.candidate_sha256, args.retest)
        if not args.resume:
            completed = {}
        isolated.update(name for name in cases if any(fnmatch.fnmatchcase(name, p) for p in args.isolate))
        shards = plan(cases, history, smoke, args.budget_seconds, args.startup_seconds, args.margin,
                      configurations=configurations, family_estimates=args.family_estimates,
                      completed=completed, isolated=isolated)
        revision = json.loads((ROOT / "dependencies.json").read_text())["repositories"]["VK-GL-CTS"]["revision"]
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        for row in shards:
            folder = output / "shards" / row["id"]
            if not args.manifest_only:
                folder.mkdir(parents=True)
            data = {"cts-shard.txt": ("\n".join(row["cases"]) + "\n").encode(),
                    "cts-args.txt": PREPARE.encode_arguments(row["configuration"])}
            row["input_sha256"] = {}
            for name, content in data.items():
                if not args.manifest_only:
                    (folder / name).write_bytes(content)
                row["input_sha256"][name] = hashlib.sha256(content).hexdigest()
        result = dict(format="ps5-opengl-cts-plan-v1",
            scope="pinned-inventory engineering rehearsal; NOT an official submission schedule",
            ready_for_console=False, candidate_frozen=False, completed_executions=0,
            blockers=["select approved CTS release and audit patches",
                      "enumerate required EGL/window configurations and official runner summary",
                      "freeze current SDK and native app with matching names",
                      "obtain explicit duration exceptions for long cases"],
            mustpass_file=args.mustpass.name, manifest_only=args.manifest_only,
            mustpass_sha256=hashlib.sha256(args.mustpass.read_bytes()).hexdigest(),
            unique_cases=len(cases), planned_executions=sum(len(row["cases"]) for row in shards),
            resume_mode=args.resume, candidate_sha256=args.candidate_sha256,
            deferred_results={str(c): completed.get(str(c), {}) for c in configurations},
            deferred_executions=sum(len(completed.get(str(c), {})) for c in configurations),
            memory_isolation_cases=sorted(isolated),
            cts_revision=revision,
            budget_seconds=args.budget_seconds, startup_seconds=args.startup_seconds, margin=args.margin,
            historical_estimated_test_hours=sum(row["estimated_test_seconds"] for row in shards)/3600,
            unknown_timing_executions=sum(row["unknown_timings"] for row in shards),
            family_estimated_executions=sum(row["family_estimates"] for row in shards),
            selected_configurations=list(configurations),
            observation_budget_hours=sum(row["observation_seconds"] for row in shards)/3600,
            note="Excludes deploy/readback/teardown/lock waits. Old timings are not a current-runtime benchmark.",
            timing_sources=sources, configurations=PREPARE.CONFIGURATIONS, shards=shards)
        raw = (json.dumps(result, indent=2) + "\n").encode()
        (output / "plan.json").write_bytes(raw)
        (output / "plan.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  plan.json\n")
        lines = ["# CTS engineering queue", "", result["scope"], "",
                 "**Not ready for console execution:** resolve the preflight in the local PLAN.md first.",
                 "", f'- Inventory: {len(cases):,} cases; {result["planned_executions"]:,} configuration/case pairs.',
                 f'- Frozen selections: {len(shards)} shards; remaining cases plus explicit deferred results cover the inventory.',
                 f'- Deferred completed executions: {result["deferred_executions"]}; Pass/skip/warning and original build identities preserved.',
                 f'- Unmeasured executions: {result["unknown_timing_executions"]:,}; placeholder budgets are not a runtime forecast.',
                 f'- Scheduling test-time budget: {result["historical_estimated_test_hours"]:.2f} hours (includes unknown placeholders).',
                 f'- Observation budgets including margin: {result["observation_budget_hours"]:.2f} hours, plus external overhead.',
                 "- Completed on this candidate: **0**. Historical results supply timings only.", "",
                 "| Lane | Shards | Executions | Historical seconds |", "|---|---:|---:|---:|"]
        for lane in ("smoke", "previous-failure", "memory-heavy", "bulk", "discovery", "long"):
            rows = [row for row in shards if row["lane"] == lane]
            lines.append(f'| {lane} | {len(rows)} | {sum(len(row["cases"]) for row in rows)} | '
                         f'{sum(row["estimated_test_seconds"] for row in rows):.1f} |')
        lines += ["", "## Duration exceptions", "",
                  "These cases remain mandatory. No automatic timeout extension or exclusion.", "",
                  "| Config | Case | Historical seconds | Proposed observation seconds | Runner change needed |",
                  "|---:|---|---:|---:|---|"]
        for row in shards:
            if row["needs_duration_approval"]:
                lines.append(f'| {row["configuration"]} | {row["cases"][0]} | '
                             f'{row["estimated_test_seconds"]:.1f} | {row["observation_seconds"]} | '
                             f'{row["exceeds_runner_limit"]} |')
        (output / "SUMMARY.md").write_text("\n".join(lines) + "\n")
        print("\n".join(lines[:21]))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
