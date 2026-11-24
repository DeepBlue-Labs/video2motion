#!/usr/bin/env bash
# Generate CSV from the newly reconstructed GVHMR result.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export GMR_ROOT=${GMR_ROOT:-$REPO/vendor/gmr}
export SMPLX_BODY_MODELS=${SMPLX_BODY_MODELS:-$GMR_ROOT/assets/body_models}
GMR_PY=${GMR_PY:-$GMR_ROOT/.venv/bin/python}
[ -x "$GMR_PY" ] || { echo "GMR Python not found: $GMR_PY; see README.md" >&2; exit 1; }
V2M_WORK=${V2M_WORK:-$REPO/work/video2motion}
exec "$GMR_PY" "$REPO/scripts/gvhmr_to_supermimic.py" \
  --gvhmr_pred "$V2M_WORK/gvhmr/gouquan/hmr4d_results.pt" --name gouquan \
  --floor_mode drift --out_dir "$V2M_WORK/csv_drift" \
  --robot_xml "${G1_XML:-$REPO/assets/mjlab_unitree_g1/xmls/g1.xml}" \
  --init_from_human --restart_tol 0.1 "$@"
