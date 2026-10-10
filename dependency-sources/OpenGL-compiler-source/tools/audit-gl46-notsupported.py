#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

"""Classify GL 4.6 CTS NotSupported results from their QPA diagnostics."""

from __future__ import annotations

import argparse
import collections
import html
import json
import re
from pathlib import Path


CASE = re.compile(
    r"^#beginTestCaseResult (?P<name>\S+)\r?\n(?P<body>.*?)"
    r"^#endTestCaseResult\s*$", re.MULTILINE | re.DOTALL)
STATUS = re.compile(r'<Result\s+StatusCode="([^"]+)"[^>]*>(.*?)</Result>', re.DOTALL)
TEXT = re.compile(r'<Text>(.*?)</Text>', re.DOTALL)

# These suites require extensions which are not part of OpenGL 4.6 Core.
OPTIONAL_FAMILIES = {
    "blend_equation_advanced",
    "ext_texture_shadow_lod",
    "fragment_shading_rate",
    "negative_texture_lookup_functions_with_bias_tests",
    "post_depth_coverage_tests",
    "shader_ballot_tests",
    "sparse_buffer_tests",
    "sparse_texture2_tests",
    "sparse_texture_clamp_tests",
    "sparse_texture_tests",
    "texture_filter_minmax_tests",
}


def plain(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def reason(body: str, result: str) -> str:
    lines = [plain(value) for value in TEXT.findall(body)]
    useful = [line for line in lines
              if line and not line.startswith(("gl", "//")) and
              "test will not run" not in line.lower()]
    return useful[-1] if useful else plain(result)


def classify(name: str, why: str) -> str:
    family = name.split(".", 2)[1]
    lower = why.lower()
    if "only in es context" in lower:
        return "profile-inapplicable"
    if family in OPTIONAL_FAMILIES:
        return "optional-extension"
    if ("sample count greater than" in lower or
            ("image samples" in lower and "only 0 available" in lower)):
        return "format-sample-limit"
    if "required extension is not supported" in lower:
        return "extension-gated-review"
    if (("requires gl_max_" in lower or "required " in lower) and
            (" got 0" in lower or "only 0 available" in lower)):
        return "core-capability-shortfall"
    if "target not supported" in lower:
        return "target-capability-shortfall"
    return "manual-review"


def audit(plan: Path, results: Path) -> dict:
    raw = json.loads(plan.read_text())
    rows = raw["deferred_results"]["0"]
    wanted = {name for name, row in rows.items()
              if row["status"] == "NotSupported"}
    found = {}
    for path in results.rglob("*.qpa"):
        text = path.read_text(errors="replace")
        for match in CASE.finditer(text):
            name = match["name"]
            if name not in wanted or name in found:
                continue
            status = STATUS.search(match["body"])
            if status and status[1] == "NotSupported":
                why = reason(match["body"], status[2])
                found[name] = {
                    "classification": classify(name, why),
                    "family": name.split(".", 2)[1],
                    "reason": why,
                    "receipt": path.relative_to(results).as_posix(),
                }
    missing = sorted(wanted - found.keys())
    classes = collections.Counter(row["classification"] for row in found.values())
    families = collections.Counter(row["family"] for row in found.values())
    return {
        "scope": "development triage; not a conformance determination",
        "not_supported": len(wanted),
        "classified": len(found),
        "missing_diagnostics": missing,
        "classifications": dict(sorted(classes.items())),
        "families": dict(sorted(families.items(), key=lambda row: (-row[1], row[0]))),
        "cases": dict(sorted(found.items())),
    }


def markdown(report: dict) -> str:
    lines = [
        "# OpenGL 4.6 `NotSupported` audit", "",
        report["scope"], "",
        f'- Results: **{report["not_supported"]:,}**',
        f'- Diagnostics classified: **{report["classified"]:,}**',
        f'- Missing diagnostics: **{len(report["missing_diagnostics"]):,}**',
        "", "## Classification", "", "| Class | Cases |", "|---|---:|",
    ]
    lines += [f"| {name} | {count:,} |"
              for name, count in report["classifications"].items()]
    lines += ["", "## Largest families", "", "| Family | Cases |", "|---|---:|"]
    lines += [f"| `{name}` | {count:,} |"
              for name, count in list(report["families"].items())[:30]]
    lines += ["", "## Review queue", "",
              "Capability shortfalls and ambiguous results require implementation review; "
              "optional-extension, profile and format-limit results do not by themselves "
              "show missing OpenGL 4.6 Core functionality.", "",
              "| Classification | Case | Reason |", "|---|---|---|"]
    review = {"core-capability-shortfall", "target-capability-shortfall",
              "extension-gated-review", "manual-review"}
    for name, row in report["cases"].items():
        if row["classification"] in review:
            why = row["reason"].replace("|", "\\|")
            lines.append(f'| {row["classification"]} | `{name}` | {why} |')
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.plan, args.results)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))
    print("NotSupported audit: " + " ".join(
        f"{name}={count}" for name, count in report["classifications"].items()))
    return 1 if report["missing_diagnostics"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
