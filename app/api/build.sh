#!/usr/bin/env bash
# Packages app/api/ into a flat directory Lambda can import from directly
# (lambda.Code.fromAsset() zips this whole dir — no venv, no site-packages
# nesting, matching MyAgent's CodeZip-over-Container precedent: no Docker).
set -euo pipefail
cd "$(dirname "$0")"

rm -rf build
mkdir -p build

uv export --no-dev -o requirements.lock.txt

# --python-platform must match the CDK stack's lambda.Architecture (ARM_64) —
# a mismatch here silently breaks the deploy: the wheel ABI mismatch only
# shows up at cold-start import time, not at `cdk deploy`.
uv pip install \
  --target build \
  --python-platform aarch64-manylinux2014 \
  --python 3.14 \
  -r requirements.lock.txt

cp main.py worker.py reconciler.py models.py clients.py linkgen.py serialize.py build/
cp -r routers build/

echo "Built app/api/build/ ($(du -sh build | cut -f1))"
