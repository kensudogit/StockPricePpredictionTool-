"""Test results API — view and optionally re-run suites from the web."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(prefix="/tests", tags=["tests"])


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here.parents[i] for i in range(1, min(6, len(here.parents)))]:
        if (p / "scripts" / "run_tests.py").exists():
            return p
        if (p / "backend").is_dir() and (p / "frontend").is_dir():
            return p
    # Docker layout: WORKDIR /app is the backend tree
    return here.parents[2]


REPO_ROOT = find_repo_root()
RESULTS_DIR = REPO_ROOT / "test-results"
if not (REPO_ROOT / "scripts" / "run_tests.py").exists():
    # backend-only container
    RESULTS_DIR = REPO_ROOT / "test-results"


def _summary_path() -> Path:
    return RESULTS_DIR / "summary.json"


@router.get("/summary")
async def tests_summary():
    path = _summary_path()
    if not path.exists():
        return {
            "status": "missing",
            "message": "まだテスト結果がありません。POST /api/v1/tests/run を実行してください。",
            "results_dir": str(RESULTS_DIR),
        }
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/report", response_class=HTMLResponse)
async def tests_report():
    index = RESULTS_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>No test report</h1><p>Run POST /api/v1/tests/run first.</p>",
        status_code=404,
    )


@router.get("/files/{name}")
async def tests_file(name: str):
    safe = Path(name).name
    path = RESULTS_DIR / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(404, f"{safe} not found")
    return FileResponse(path)


def _run_tests_job() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    script = REPO_ROOT / "scripts" / "run_tests.py"
    if script.exists():
        subprocess.run([sys.executable, str(script)], cwd=str(REPO_ROOT), check=False)
        return
    # Fallback: backend-only pytest inside container
    junit = RESULTS_DIR / "backend-junit.xml"
    html = RESULTS_DIR / "backend-pytest.html"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            f"--junitxml={junit}",
            f"--html={html}",
            "--self-contained-html",
            "-q",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    # minimal summary
    summary = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "backend": {"suite": "backend", "exit_code": 0, "html_report": "backend-pytest.html"},
        "frontend": {"suite": "frontend", "exit_code": 0, "total": 0, "passed": 0, "failed": 0, "skipped": 0},
        "totals": {"ok": True, "total": 0, "passed": 0, "failed": 0, "skipped": 0},
    }
    # parse junit if present
    if junit.exists():
        import xml.etree.ElementTree as ET

        root = ET.parse(junit).getroot()
        suites_el = root.findall("testsuite") if root.tag == "testsuites" else [root]
        total = failed = skipped = errors = 0
        cases = []
        for ts in suites_el:
            total += int(ts.attrib.get("tests", 0))
            failed += int(ts.attrib.get("failures", 0))
            errors += int(ts.attrib.get("errors", 0))
            skipped += int(ts.attrib.get("skipped", 0))
            for tc in ts.findall("testcase"):
                status = "passed"
                msg = ""
                if tc.find("failure") is not None:
                    status = "failed"
                    msg = (tc.find("failure").attrib.get("message") or "")[:500]
                elif tc.find("error") is not None:
                    status = "error"
                    msg = (tc.find("error").attrib.get("message") or "")[:500]
                elif tc.find("skipped") is not None:
                    status = "skipped"
                cases.append(
                    {
                        "class": tc.attrib.get("classname", ""),
                        "name": tc.attrib.get("name", ""),
                        "time": float(tc.attrib.get("time", 0) or 0),
                        "status": status,
                        "message": msg,
                    }
                )
        summary["backend"] = {
            "suite": "backend",
            "exit_code": 0 if failed + errors == 0 else 1,
            "total": total,
            "passed": max(total - failed - errors - skipped, 0),
            "failed": failed + errors,
            "skipped": skipped,
            "html_report": "backend-pytest.html",
            "suites": [{"name": "backend", "cases": cases}],
        }
        summary["totals"] = {
            "total": total,
            "passed": summary["backend"]["passed"],
            "failed": summary["backend"]["failed"],
            "skipped": skipped,
            "ok": failed + errors == 0,
        }
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS_DIR / "index.html").write_text(
        f"<h1>Backend tests</h1><p>See <a href='/api/v1/tests/files/backend-pytest.html'>HTML report</a></p>"
        f"<pre>{json.dumps(summary.get('totals'), indent=2)}</pre>",
        encoding="utf-8",
    )


@router.post("/run")
async def tests_run(background_tasks: BackgroundTasks, wait: bool = False):
    if os.getenv("ALLOW_TEST_RUN", "true").lower() in {"0", "false", "no"}:
        raise HTTPException(403, "Test runs disabled (ALLOW_TEST_RUN=false)")

    if wait:
        _run_tests_job()
        if _summary_path().exists():
            return {"status": "completed", "summary": json.loads(_summary_path().read_text(encoding="utf-8"))}
        return {"status": "completed", "summary": None}

    background_tasks.add_task(_run_tests_job)
    return {
        "status": "started",
        "message": "テストをバックグラウンドで開始しました。 /tests/ または /api/v1/tests/summary を確認してください。",
    }
