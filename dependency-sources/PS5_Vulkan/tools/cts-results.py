#!/usr/bin/env python3
# PS5 Vulkan - summarise a batched CTS run (tools/run-cts.py).
# Copyright (C) 2026 Mihawk-99
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarise a batched CTS run: counts by status and the failures grouped.

Reads build/cts-runs/<run>/results.tsv. Failures (every status other than
Pass, NotSupported and the warnings) are grouped by their first --depth path
components, largest group first, each with its most common message and an
example case; --list prints every failing case instead.
"""

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOOD = ("Pass", "NotSupported", "QualityWarning", "CompatibilityWarning", "Waiver")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="the run's name under build/cts-runs")
    parser.add_argument("--depth", type=int, default=5, help="path components a group shares")
    parser.add_argument("--list", action="store_true", help="print every failing case")
    args = parser.parse_args()

    path = ROOT / "build" / "cts-runs" / args.run / "results.tsv"
    rows = [(line.split("\t") + ["", ""])[:3] for line in path.read_text().splitlines() if line]
    counts = collections.Counter(status for _, status, _ in rows)
    print(f"{args.run}: {len(rows)} cases  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    failures = [row for row in rows if row[1] not in GOOD]
    if args.list:
        for name, status, detail in failures:
            print(f"{status:<14} {name}  {detail}")
        return 1 if failures else 0
    groups = collections.defaultdict(list)
    for row in failures:
        groups[".".join(row[0].split(".")[:args.depth])].append(row)
    for group, members in sorted(groups.items(), key=lambda item: -len(item[1])):
        statuses = collections.Counter(status for _, status, _ in members)
        detail, _ = collections.Counter(detail for _, _, detail in members).most_common(1)[0]
        print(f"{len(members):>6}  {group}  ({', '.join(f'{k} {v}' for k, v in statuses.items())})")
        print(f"        {detail[:150]}")
        print(f"        e.g. {members[0][0]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
