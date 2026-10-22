"""Run trusted hidden test wrappers and write equal-item reward inside a verifier container.

Wrapper contract: exit 0=pass, 1=candidate failed, all other exits=grader invalid.
Wrappers must catch candidate crashes/timeouts and return 1; a wrapper timeout is invalid.
This runner does not sandbox code. Use it only inside the verified Harbor verifier environment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(manifest_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reward = out_dir / "reward.txt"
    reward.write_text("0\n", encoding="ascii")
    report = {"execution_status": "invalid", "verification_id": uuid.uuid4().hex,
              "case_results": [], "reason": "verification not completed"}
    report_path = out_dir / "case-results.json"
    write(report_path, report)
    try:
        if (out_dir / "reward.json").exists():
            raise ValueError("reward.json also exists; only one reward format is allowed")
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
        tests = manifest["tests"]
        if manifest.get("schema_version") != "1.0" or not tests:
            raise ValueError("nonempty schema 1.0 tests required")
        ids = [t["id"] for t in tests]
        if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
            raise ValueError("unique nonempty IDs required")
        # Validate every check before launching the first, so malformed later entries cannot hide earlier failures.
        for t in tests:
            if not isinstance(t.get("pass_criteria"), str) or not t["pass_criteria"].strip():
                raise ValueError("pass_criteria required")
            if "weight" in t and (type(t["weight"]) not in (int, float) or t["weight"] != 1):
                raise ValueError("unequal weights prohibited")
            argv = t.get("command")
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
                raise ValueError("trusted wrapper command must be a nonempty argv array")
            if type(t.get("timeout_sec")) not in (int, float) or not 0 < t["timeout_sec"] <= 86400:
                raise ValueError("finite positive wrapper timeout required")
        report["manifest_hash"] = digest(manifest)
        invalid = False
        for i, test in enumerate(tests, 1):
            stdout = out_dir / f"case-{i:04d}.stdout.log"
            stderr = out_dir / f"case-{i:04d}.stderr.log"
            with stdout.open("wb") as out, stderr.open("wb") as err:
                try:
                    proc = subprocess.run(test["command"], stdout=out, stderr=err,
                                          timeout=test["timeout_sec"], check=False)
                    status = {0: "pass", 1: "fail"}.get(proc.returncode, "grader_error")
                    code = proc.returncode
                except subprocess.TimeoutExpired:
                    status, code = "grader_timeout", None
                except OSError:
                    status, code = "grader_error", None
            invalid |= status not in {"pass", "fail"}
            report["case_results"].append({"id": test["id"], "status": status, "returncode": code,
                                           "stdout": stdout.name, "stderr": stderr.name})
            write(report_path, report)
        passed = sum(c["status"] == "pass" for c in report["case_results"])
        report.update(passed_count=passed, total_count=len(tests))
        if invalid:
            report["reason"] = "grader error or wrapper timeout; placeholder zero is not a model score"
        else:
            report.update(execution_status="completed", raw_reward=passed / len(tests))
            report.pop("reason", None)
            # Write the complete result first; interruption cannot leave a positive stale score.
            write(report_path, report)
            reward.write_text(format(passed / len(tests), ".17g") + "\n", encoding="ascii")
        write(report_path, report)
        return 2 if invalid else 0
    except (Exception, KeyboardInterrupt) as e:
        reward.write_text("0\n", encoding="ascii")
        report.update(execution_status="invalid", reason=str(e) or type(e).__name__)
        write(report_path, report)
        return 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--output-dir", default="/logs/verifier")
    args = p.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError(f"signal {signum}")
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    return run(args.manifest, args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
