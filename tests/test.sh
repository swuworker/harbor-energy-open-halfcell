#!/bin/bash
set -euo pipefail
unset PYTHONPATH PYTHONHOME BASH_ENV ENV
export PYTHONNOUSERSITE=1
/opt/venv/bin/python -I /tests/prepare_verifier.py
/opt/venv/bin/python -I /tests/ratio_verifier.py --manifest /tests/test-manifest.json --output-dir /logs/verifier
