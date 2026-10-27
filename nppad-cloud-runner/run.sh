#!/usr/bin/env bash
# NPPAD cloud runner entry point (used by .github/workflows/nppad-cloud-runner.yml;
# also runnable locally / on any machine with the requirements installed).
#
# 1. Downloads the dataset from the PUBLIC S3 URL (no credentials needed for
#    the read) and extracts it.
# 2. Trains all 8 models at the official protocol (train_all.py).
# 3. If AWS credentials are available (the workflow provides them from the
#    repo secrets), uploads results.json + status.json + pred_E_S1test.csv
#    (+ per-model sheets) to s3://nppad-hw2-data-2026/outputs/ and refreshes
#    status.json LAST so pollers only see "done" once everything is up.
#    Without credentials the outputs stay in ./outputs locally.
set -euo pipefail
cd "$(dirname "$0")"

DATA_URL="${NPPAD_DATA_URL:-https://nppad-hw2-data-2026.s3.amazonaws.com/NPPAD_Data_for_HW2.zip}"
OUT_BUCKET="${NPPAD_OUT_BUCKET:-nppad-hw2-data-2026}"
OUT_PREFIX="${NPPAD_OUT_PREFIX:-outputs}"
WORK="${RUNNER_WORK:-$PWD/.runner-work}"
mkdir -p "$WORK" outputs

write_status() {  # $1 = state, $2 = stage — minimal early status before python runs
  printf '{"state": "%s", "stage": "%s", "updated_utc": "%s"}\n' \
    "$1" "$2" "$(date -u +%FT%TZ)" > outputs/status.json
}

upload() {  # best-effort; only when credentials exist
  if aws sts get-caller-identity >/dev/null 2>&1; then
    aws s3 cp outputs/results.json      "s3://$OUT_BUCKET/$OUT_PREFIX/results.json"      || true
    aws s3 cp outputs/pred_E_S1test.csv "s3://$OUT_BUCKET/$OUT_PREFIX/pred_E_S1test.csv" || true
    for f in outputs/pred_*_W60_test.csv; do
      [ -f "$f" ] && aws s3 cp "$f" "s3://$OUT_BUCKET/$OUT_PREFIX/$(basename "$f")" || true
    done
    # status.json goes up LAST (and once at the start, as "running")
    aws s3 cp outputs/status.json "s3://$OUT_BUCKET/$OUT_PREFIX/status.json" || true
  else
    echo "No AWS credentials — outputs stay local in ./outputs"
  fi
}

if [ ! -d "$WORK/NuclearPowerPlantAccidentData/Operation_csv_data" ]; then
  echo "Downloading dataset from $DATA_URL"
  curl -fL "$DATA_URL" -o "$WORK/data.zip"
  unzip -q -o "$WORK/data.zip" -d "$WORK"
fi
export NPPAD_DATA_ROOT="$WORK/NuclearPowerPlantAccidentData/Operation_csv_data"
echo "NPPAD_DATA_ROOT=$NPPAD_DATA_ROOT"

write_status running downloading-data
upload || true

PY="$(command -v python3 || command -v python)"
set +e
if [ -n "${NPPAD_MODELS:-}" ]; then
  "$PY" train_all.py --out outputs --models "$NPPAD_MODELS"
else
  "$PY" train_all.py --out outputs
fi
rc=$?
set -e
upload || true
exit $rc
