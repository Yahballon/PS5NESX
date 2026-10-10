#!/usr/bin/env python3
# PS5 OpenGL - OpenGL implementation for PlayStation 5.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib.util
import json
import tempfile
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).with_name("audit-gl46-notsupported.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def main():
    cases = {
        "KHR-GL46.sparse_texture_tests.a": "Required extension is not supported",
        "KHR-GL46.texture_cube_map_array.a": "The test can be run only in ES context",
        "KHR-GL46.sample_variables.a": "Test sample count greater than samples that the format supports",
        "KHR-GL46.shader_storage_buffer_object.a":
            "Required 1 VS storage blocks but only 0 available.",
    }
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        plan = root / "plan.json"
        results = root / "results"
        results.mkdir()
        plan.write_text(json.dumps({"deferred_results": {"0": {
            name: {"status": "NotSupported"} for name in cases}}}))
        body = []
        for name, why in cases.items():
            body += [f"#beginTestCaseResult {name}",
                     f'<TestCaseResult><Text>{why}</Text><Result StatusCode="NotSupported">Not supported</Result></TestCaseResult>',
                     "#endTestCaseResult"]
        (results / "fixture.qpa").write_text("\n".join(body))
        report = audit.audit(plan, results)
        assert report["missing_diagnostics"] == []
        assert report["classifications"] == {
            "core-capability-shortfall": 1,
            "format-sample-limit": 1,
            "optional-extension": 1,
            "profile-inapplicable": 1,
        }
    print("gl46 NotSupported audit test: PASS")


if __name__ == "__main__":
    main()
