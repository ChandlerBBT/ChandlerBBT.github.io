from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / ".cache" / "bayes-rules-deepseek" / "parallel-logs"

DEFAULT_PAGES = [
    "/chapter-2",
    "/chapter-3",
    "/chapter-4",
    "/chapter-5",
    "/chapter-6",
    "/chapter-7",
    "/chapter-8",
    "/chapter-9",
    "/chapter-10",
    "/chapter-11",
    "/chapter-12",
    "/chapter-13",
    "/chapter-14",
    "/chapter-15",
    "/chapter-16",
    "/chapter-17",
    "/chapter-18",
    "/chapter-19",
    "/references",
]


@dataclass
class RunningJob:
    page: str
    attempt: int
    process: subprocess.Popen
    log_file: object
    log_path: Path
    started_at: float


def page_log_name(page: str, attempt: int) -> str:
    slug = page.strip("/").replace("/", "-") or "index"
    return f"{slug}.attempt-{attempt}.log"


def tail(path: Path, lines: int = 28) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def start_job(page: str, attempt: int, args: argparse.Namespace, env: dict[str, str]) -> RunningJob:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / page_log_name(page, attempt)
    log_file = log_path.open("w", encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "tools" / "import_bayes_rules.py"),
        "--translator",
        "deepseek",
        "--model",
        args.model,
        "--batch-size",
        str(args.batch_size),
        "--api-timeout",
        str(args.api_timeout),
        "--only",
        page,
    ]
    if args.no_book_context:
        command.append("--no-book-context")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"[start] {page} attempt={attempt} log={log_path}", flush=True)
    return RunningJob(page, attempt, process, log_file, log_path, time.time())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Bayes Rules chapter imports in parallel.")
    parser.add_argument("--workers", type=int, default=8, help="Maximum concurrent chapter jobs.")
    parser.add_argument("--batch-size", type=int, default=8, help="DeepSeek fragment batch size per chapter job.")
    parser.add_argument("--api-timeout", type=int, default=100, help="DeepSeek total response time limit per request.")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--retries", type=int, default=1, help="Retries per failed chapter job.")
    parser.add_argument("--pages", nargs="*", default=DEFAULT_PAGES, help="Import paths to render.")
    parser.add_argument("--no-book-context", action="store_true", help="Skip full-book guide injection.")
    args = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("ARGOS_CHUNK_TYPE", "SPACY")

    pending = list(args.pages)
    attempts = {page: 0 for page in pending}
    running: list[RunningJob] = []
    completed: list[str] = []
    failed: list[str] = []
    last_status = time.time()

    while pending or running:
        while pending and len(running) < args.workers:
            page = pending.pop(0)
            attempts[page] += 1
            running.append(start_job(page, attempts[page], args, env))

        still_running: list[RunningJob] = []
        for job in running:
            code = job.process.poll()
            if code is None:
                still_running.append(job)
                continue

            job.log_file.close()
            elapsed = time.time() - job.started_at
            if code == 0:
                completed.append(job.page)
                print(f"[done] {job.page} in {elapsed:.1f}s", flush=True)
            elif attempts[job.page] <= args.retries:
                print(f"[retry] {job.page} failed with code {code}; requeueing", flush=True)
                pending.append(job.page)
            else:
                failed.append(job.page)
                print(f"[fail] {job.page} code={code} log={job.log_path}", flush=True)
                print(tail(job.log_path), flush=True)
        running = still_running

        if time.time() - last_status >= 30:
            active = ", ".join(job.page for job in running) or "none"
            print(
                f"[status] done={len(completed)} failed={len(failed)} pending={len(pending)} active={active}",
                flush=True,
            )
            last_status = time.time()
        time.sleep(2)

    print(f"[summary] completed={len(completed)} failed={len(failed)}", flush=True)
    if failed:
        print("[summary] failed pages: " + ", ".join(failed), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
