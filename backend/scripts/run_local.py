#!/usr/bin/env python3
"""Start the FindableAI API and the durable scan worker together (local dev / demo).

Usage (from backend/, with the venv active and PostgreSQL up):

    python scripts/run_local.py            # API on :8000 + worker
    python scripts/run_local.py --no-worker
    python scripts/run_local.py --port 8001

Both children inherit this process's environment (.env is loaded by the app).
Ctrl-C stops both. If either child exits, the other is terminated and the
launcher exits non-zero so a dead worker is never silent.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-worker", action="store_true", help="API only")
    parser.add_argument("--reload", action="store_true", help="uvicorn --reload (API only)")
    args = parser.parse_args()

    py = sys.executable
    api_cmd = [py, "-m", "uvicorn", "app.main:app", "--host", args.host, "--port", str(args.port)]
    if args.reload:
        api_cmd.append("--reload")
    worker_cmd = [py, "-m", "app.worker"]

    procs: dict[str, subprocess.Popen[bytes]] = {}
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

    def start(name: str, cmd: list[str]) -> None:
        print(f"[run_local] starting {name}: {' '.join(cmd)}", flush=True)
        procs[name] = subprocess.Popen(cmd, cwd=str(BACKEND_ROOT), creationflags=creation)

    def stop_all() -> None:
        for name, proc in procs.items():
            if proc.poll() is None:
                print(f"[run_local] stopping {name} (pid={proc.pid})", flush=True)
                try:
                    if sys.platform == "win32":
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        proc.terminate()
                except Exception:
                    pass
        deadline = time.monotonic() + 10
        for proc in procs.values():
            remaining = max(0.0, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()

    start("api", api_cmd)
    if not args.no_worker:
        start("worker", worker_cmd)

    exit_code = 0
    try:
        while True:
            for name, proc in procs.items():
                rc = proc.poll()
                if rc is not None:
                    print(f"[run_local] {name} exited with code {rc}; shutting down", flush=True)
                    exit_code = rc or 1
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
