"""Root-only verifier preparation; executed by Harbor inside its Docker trial."""
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import stat
import subprocess
import sys


def stop_uid(uid):
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = next(x for x in (entry / 'status').read_text().splitlines()
                          if x.startswith('Uid:')).split()
            if int(fields[1]) == uid:
                os.kill(int(entry.name), signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError, PermissionError, StopIteration):
            pass


def protect_tree(root):
    if not root.exists():
        return
    if root.is_symlink():
        raise RuntimeError('Protected path is a symlink')
    os.chown(root, 0, 0)
    root.chmod(0o700)
    for path in root.rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Protected content contains a symlink')
        os.chown(path, 0, 0)
        path.chmod(0o700 if path.is_dir() else 0o600)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Verifier must run as root')
    account = pwd.getpwnam('candidate')
    if account.pw_uid == 0:
        raise RuntimeError('Candidate is privileged')
    stop_uid(account.pw_uid)
    for path in (Path('/tests'), Path('/solution')):
        protect_tree(path)
    Path('/tests/test.sh').chmod(0o755)

    output = Path('/logs/verifier')
    if output.is_symlink():
        raise RuntimeError('Verifier output path is a symlink')
    output.mkdir(parents=True, exist_ok=True)
    os.chown(output, 0, 0)
    output.chmod(0o700)
    for path in output.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    # Invalidate old scores even if preparation fails before the ratio runner.
    (output / 'reward.txt').write_text('0\n', encoding='ascii')
    (output / 'case-results.json').write_text(json.dumps({
        'execution_status': 'invalid', 'case_results': [],
        'reason': 'trusted verifier preparation not yet complete'}) + '\n')

    snapshot = Path('/run/halfcell-candidate-snapshot')
    if snapshot.exists() or snapshot.is_symlink():
        if snapshot.is_symlink() or not snapshot.is_dir():
            snapshot.unlink()
        else:
            shutil.rmtree(snapshot)
    snapshot.mkdir(mode=0o700)
    source = Path('/app/src')
    candidate_error = None
    try:
        if not source.is_dir() or source.is_symlink():
            raise ValueError('Candidate source directory missing or replaced')
        origin = source.resolve()
        for path in source.rglob('*'):
            resolved = path.resolve()
            if not resolved.is_relative_to(origin):
                raise ValueError('Candidate source link escapes /app/src')
            if not (resolved.is_dir() or resolved.is_file()):
                raise ValueError('Candidate source contains a special file')
        shutil.copytree(source, snapshot / 'src', symlinks=False)
        if not (snapshot / 'src/halfcell.py').is_file():
            raise ValueError('Candidate entrypoint is missing')
        protect_tree(snapshot / 'src')
    except (OSError, ValueError, RuntimeError) as exc:
        candidate_error = str(exc)
    (snapshot / 'status.json').write_text(json.dumps({'candidate_error': candidate_error}) + '\n')

    def demote():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    probe = subprocess.run([sys.executable, '-I', '-c',
        "import json,os;print(json.dumps({'uid':os.getuid(),"
        "'tests_readable':os.access('/tests',os.R_OK),"
        "'solution_readable':os.access('/solution',os.R_OK),"
        "'snapshot_readable':os.access('/run/halfcell-candidate-snapshot',os.R_OK),"
        "'reward_writable':os.access('/logs/verifier',os.W_OK)}))"],
        text=True, capture_output=True, check=True, preexec_fn=demote,
        cwd='/', env={'PATH': '/usr/bin:/bin'}, timeout=5)
    observed = json.loads(probe.stdout)
    if observed['uid'] == 0 or any(value for key, value in observed.items() if key != 'uid'):
        raise RuntimeError('Candidate can access protected verifier files')
    (output / 'verification-security.json').write_text(json.dumps({
        'phase': 'verification', 'probe': observed,
        'test_sh_mode': oct(stat.S_IMODE(Path('/tests/test.sh').stat().st_mode)),
        'test_sh_uid': Path('/tests/test.sh').stat().st_uid,
        'candidate_source_issue': candidate_error}, indent=2) + '\n')


if __name__ == '__main__':
    main()
