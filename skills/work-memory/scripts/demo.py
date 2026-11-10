#!/usr/bin/env python3
"""Replay three decision changes in an isolated sample project."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent


def run_cli(root, script, *args, payload=None, expected_exit=0):
    process = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args, "--root", str(root)],
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
    )
    if process.returncode != expected_exit:
        raise RuntimeError(f"{script} exit {process.returncode}: {process.stderr}")
    return json.loads(process.stdout if expected_exit == 0 else process.stderr)


def run(root):
    root.mkdir()
    root = root.resolve()
    run_cli(root, "memory.py", "init")
    choices = [
        ("Friday", "The initial launch target is Friday."),
        ("Monday", "Move launch to Monday because review needs the weekend."),
        ("Wednesday", "Move launch to Wednesday because the partner needs two days."),
        ("Thursday", "Move launch to Thursday because the final smoke test moved to Wednesday."),
    ]

    def capture(day, source, expected_revision):
        payload = {
            "key": "launch-day",
            "kind": "decision",
            "authority": "user",
            "actor": "sample-recorder",
            "summary": f"Launch on {day}.",
            "source": {"text": source, "locator": f"fictional-user-turn-{expected_revision + 1}"},
            "applicability": "Sample launch only",
        }
        if expected_revision:
            payload.update(expected_revision=expected_revision, supersedes_reason=source)
        return payload

    for expected_revision, (day, source) in enumerate(choices):
        saved = run_cli(root, "memory.py", "capture", "--input", "-",
                        payload=capture(day, source, expected_revision))
        record_id = saved["record"]["id"]
        assert saved["record"]["revision"] == expected_revision + 1

    conflict = run_cli(root, "memory.py", "capture", "--input", "-",
                       payload=capture("Tuesday", "A late writer still has revision 2.", 2),
                       expected_exit=2)
    assert "expected_revision must be 4" in conflict["error"]
    brief = run_cli(root, "context.py", "brief", "--query", "launch", "--mode", "execute")
    assert [(item["id"], item["revision"], item["summary"]) for item in brief["current"]] == [
        (record_id, 4, "Launch on Thursday.")
    ]
    evidence = []
    for revision, (_, source) in enumerate(choices, start=1):
        shown = run_cli(root, "context.py", "show", "--id", record_id, "--revision", str(revision))
        record = shown["record"]
        assert record["source_excerpt"] == source
        assert record["eligible_for_execution_context"] == (revision == 4)
        evidence.append({
            "revision": revision,
            "summary": record["summary"],
            "source": record["source"]["locator"],
            "exact_evidence": source,
            "eligible_for_execution_context": record["eligible_for_execution_context"],
        })

    return {"sample_data": True, "verification": "separate local CLI processes",
            "project": str(root), "record_id": record_id, "history": evidence,
            "stale_writer_rejected": conflict["error"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New sample project directory")
    args = parser.parse_args()
    try:
        receipt = run(args.output.expanduser())
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        parser.exit(1, f"Demo failed: {exc}\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
