"""Fresh unprivileged candidate process; never import candidate code in the grader."""
import json
import math
import os
from pathlib import Path
import pwd
import resource
import shutil
import signal
import subprocess
import tempfile
import time


class CandidateFailure(Exception):
    """A determinate candidate failure, including missing output and timeout."""


def _stop_uid(uid):
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = next(line for line in (entry / 'status').read_text().splitlines()
                          if line.startswith('Uid:')).split()
            if int(fields[1]) == uid:
                os.kill(int(entry.name), signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError, PermissionError, StopIteration):
            pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate output object key')
        result[key] = value
    return result


def _finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError('Nonfinite output number')
    return value


def run_payload(payload, timeout_seconds, *, raw=False):
    if os.geteuid() != 0:
        raise RuntimeError('Trusted process boundary requires root')
    executable = Path('/opt/venv/bin/python')
    if not executable.is_file():
        raise RuntimeError('Trusted Python environment is missing')
    account = pwd.getpwnam('candidate')
    if account.pw_uid == 0:
        raise RuntimeError('Candidate account must be unprivileged')
    _stop_uid(account.pw_uid)
    snapshot = Path('/run/halfcell-candidate-snapshot')
    status = json.loads((snapshot / 'status.json').read_text())
    if status['candidate_error']:
        raise CandidateFailure(status['candidate_error'])
    data = payload.encode('utf-8') if raw else json.dumps(payload, allow_nan=False).encode('utf-8')
    with tempfile.TemporaryDirectory(prefix='hc-', dir='/tmp') as temporary:
        work = Path(temporary)
        work.chmod(0o755)
        shutil.copytree(snapshot / 'src', work / 'src')
        for path in [work / 'src', *(work / 'src').rglob('*')]:
            os.chown(path, account.pw_uid, account.pw_gid)
            path.chmod(0o755 if path.is_dir() else 0o644)
        (work / 'home').mkdir(mode=0o700)
        os.chown(work / 'home', account.pw_uid, account.pw_gid)
        code = ("import runpy,sys;sys.path.insert(0,sys.argv[1]);"
                "runpy.run_path(sys.argv[1]+'/halfcell.py',run_name='__main__')")
        command = [str(executable), '-I', '-c', code, str(work / 'src')]
        env = {'PATH': '/opt/venv/bin:/usr/bin:/bin', 'HOME': str(work / 'home'),
               'LANG': 'C.UTF-8', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
               'MKL_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        def demote():
            os.setgroups([])
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            cpu = max(1, math.ceil(timeout_seconds) + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_FSIZE, (16*1024*1024, 16*1024*1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        with tempfile.TemporaryFile(dir='/logs/verifier') as out, tempfile.TemporaryFile(dir='/logs/verifier') as err:
            started = time.monotonic()
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                cwd=work / 'src', env=env, close_fds=True, start_new_session=True, preexec_fn=demote)
            try:
                try:
                    process.communicate(data, timeout=timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    raise CandidateFailure('Candidate process timed out') from exc
                elapsed = time.monotonic() - started
                print(json.dumps({'event': 'candidate_timing', 'seconds': elapsed}), flush=True)
                out.seek(0)
                stdout = out.read(8*1024*1024 + 1)
                err.seek(0, os.SEEK_END)
                length = err.tell()
                err.seek(max(0, length - 3000))
                stderr = err.read().decode('utf-8', errors='replace')
                if process.returncode != 0:
                    print(json.dumps({'event': 'candidate_error', 'returncode': process.returncode,
                                      'stderr_tail': stderr}), flush=True)
                    raise CandidateFailure('Candidate process exited unsuccessfully')
                if len(stdout) > 8*1024*1024:
                    raise CandidateFailure('Candidate response is larger than 8 MiB')
                try:
                    result = json.loads(stdout.decode('utf-8'), object_pairs_hook=_object,
                        parse_float=_finite_float,
                        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
                except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
                    raise CandidateFailure('Candidate did not return one valid JSON object') from exc
                if not isinstance(result, dict):
                    raise CandidateFailure('Candidate response is not an object')
                print(json.dumps({'event': 'candidate_output', 'output': result}, allow_nan=False), flush=True)
                return result
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _stop_uid(account.pw_uid)
                if process.poll() is None:
                    process.wait(timeout=2)
