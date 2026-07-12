#!/usr/bin/env python3
"""Run backend + frontend tests and write unified JSON/HTML reports for the web UI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" if (ROOT / "backend" / "app").is_dir() else ROOT
FRONTEND = ROOT / "frontend"
RESULTS = ROOT / "test-results"


def _npm() -> str:
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    return "npm"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), f"(cwd={cwd})")
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )


def run_backend() -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    junit = RESULTS / "backend-junit.xml"
    html = RESULTS / "backend-pytest.html"
    json_path = RESULTS / "backend-pytest.json"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        f"--junitxml={junit}",
        f"--html={html}",
        "--self-contained-html",
        "-q",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    proc = subprocess.run(cmd, cwd=str(BACKEND), capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")

    suites = []
    total = failed = skipped = errors = 0
    if junit.exists():
        root = ET.parse(junit).getroot()
        # pytest may emit testsuites or testsuite
        suites_el = root.findall("testsuite") if root.tag == "testsuites" else [root]
        for ts in suites_el:
            total += int(ts.attrib.get("tests", 0))
            failed += int(ts.attrib.get("failures", 0))
            errors += int(ts.attrib.get("errors", 0))
            skipped += int(ts.attrib.get("skipped", 0))
            cases = []
            for tc in ts.findall("testcase"):
                status = "passed"
                message = ""
                if tc.find("failure") is not None:
                    status = "failed"
                    message = (tc.find("failure").attrib.get("message") or "")[:500]
                elif tc.find("error") is not None:
                    status = "error"
                    message = (tc.find("error").attrib.get("message") or "")[:500]
                elif tc.find("skipped") is not None:
                    status = "skipped"
                cases.append(
                    {
                        "class": tc.attrib.get("classname", ""),
                        "name": tc.attrib.get("name", ""),
                        "time": float(tc.attrib.get("time", 0) or 0),
                        "status": status,
                        "message": message,
                    }
                )
            suites.append({"name": ts.attrib.get("name", "backend"), "cases": cases})

    summary = {
        "suite": "backend",
        "exit_code": proc.returncode,
        "total": total,
        "passed": max(total - failed - errors - skipped, 0),
        "failed": failed + errors,
        "skipped": skipped,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
        "html_report": "backend-pytest.html" if html.exists() else None,
        "suites": suites,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def run_frontend() -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not (FRONTEND / "package.json").exists():
        return {
            "suite": "frontend",
            "exit_code": 0,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "stdout": "frontend skipped (not found)",
            "stderr": "",
            "html_report": None,
            "suites": [],
        }
    # ensure vitest deps
    npm = _npm()
    _run([npm, "install", "--no-fund", "--no-audit"], FRONTEND)
    proc = _run([npm, "run", "test:ci"], FRONTEND)
    vitest_json = RESULTS / "frontend-vitest.json"
    summary = {
        "suite": "frontend",
        "exit_code": proc.returncode,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
        "html_report": "frontend-vitest.html" if (RESULTS / "frontend-vitest.html").exists() else None,
        "suites": [],
    }
    if vitest_json.exists():
        try:
            raw = json.loads(vitest_json.read_text(encoding="utf-8"))
            # vitest json reporter shape
            test_results = raw.get("testResults") or []
            cases = []
            for tr in test_results:
                for a in tr.get("assertionResults") or []:
                    status = a.get("status", "passed")
                    if status == "passed":
                        summary["passed"] += 1
                    elif status == "failed":
                        summary["failed"] += 1
                    else:
                        summary["skipped"] += 1
                    summary["total"] += 1
                    cases.append(
                        {
                            "class": tr.get("name", ""),
                            "name": a.get("title") or a.get("fullName", ""),
                            "time": (a.get("duration") or 0) / 1000.0,
                            "status": status,
                            "message": (a.get("failureMessages") or [""])[0][:500],
                        }
                    )
            summary["suites"] = [{"name": "frontend", "cases": cases}]
            # lightweight HTML for frontend
            rows = "".join(
                f"<tr><td>{c['class']}</td><td>{c['name']}</td><td>{c['status']}</td></tr>"
                for c in cases
            )
            (RESULTS / "frontend-vitest.html").write_text(
                f"<html><body><h1>Frontend Vitest</h1><table border='1'>{rows}</table></body></html>",
                encoding="utf-8",
            )
            summary["html_report"] = "frontend-vitest.html"
        except json.JSONDecodeError:
            pass
    (RESULTS / "frontend-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def write_unified(backend: dict, frontend: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    unified = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": backend,
        "frontend": frontend,
        "totals": {
            "total": backend.get("total", 0) + frontend.get("total", 0),
            "passed": backend.get("passed", 0) + frontend.get("passed", 0),
            "failed": backend.get("failed", 0) + frontend.get("failed", 0),
            "skipped": backend.get("skipped", 0) + frontend.get("skipped", 0),
            "ok": backend.get("exit_code", 1) == 0 and frontend.get("exit_code", 1) == 0,
        },
    }
    out = RESULTS / "summary.json"
    out.write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")

    # Simple HTML dashboard
    t = unified["totals"]
    rows = []
    for side in ("backend", "frontend"):
        block = unified[side]
        for suite in block.get("suites") or []:
            for c in suite.get("cases") or []:
                color = {"passed": "#3dd68c", "failed": "#e85d5d", "error": "#e85d5d", "skipped": "#e8b84a"}.get(
                    c["status"], "#8aa396"
                )
                rows.append(
                    f"<tr><td>{side}</td><td>{c['class']}</td><td>{c['name']}</td>"
                    f"<td style='color:{color}'>{c['status']}</td><td>{c['time']:.3f}s</td>"
                    f"<td><pre style='white-space:pre-wrap;max-width:420px'>{c.get('message','')}</pre></td></tr>"
                )
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"/><title>StockAI Test Results</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0c1210;color:#e8f0eb;margin:0;padding:2rem}}
.ok{{color:#3dd68c}}.bad{{color:#e85d5d}}
table{{border-collapse:collapse;width:100%;margin-top:1rem}}
th,td{{border:1px solid #2a3a32;padding:.5rem;font-size:.85rem;vertical-align:top}}
th{{background:#141c18;text-align:left}}
a{{color:#3dd68c}}
</style></head><body>
<h1>StockAI Test Results</h1>
<p>Generated: {unified['generated_at']}</p>
<p>Total {t['total']} · Passed <span class="ok">{t['passed']}</span> ·
Failed <span class="{'bad' if t['failed'] else 'ok'}">{t['failed']}</span> · Skipped {t['skipped']} ·
Overall: <strong class="{'ok' if t['ok'] else 'bad'}">{'PASS' if t['ok'] else 'FAIL'}</strong></p>
<p>
  <a href="backend-pytest.html">Backend HTML</a> ·
  <a href="frontend-vitest.html">Frontend HTML</a> ·
  <a href="summary.json">summary.json</a>
</p>
<table>
<thead><tr><th>Side</th><th>Class / File</th><th>Test</th><th>Status</th><th>Time</th><th>Message</th></tr></thead>
<tbody>
{''.join(rows) or '<tr><td colspan="6">No case details</td></tr>'}
</tbody></table>
</body></html>"""
    html_path = RESULTS / "index.html"
    html_path.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    backend = run_backend()
    frontend = run_frontend()
    write_unified(backend, frontend)
    print(json.dumps({"backend_exit": backend["exit_code"], "frontend_exit": frontend["exit_code"]}, indent=2))
    return 0 if backend["exit_code"] == 0 and frontend["exit_code"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
