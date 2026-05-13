#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  HireSense AI — Dataset Download Script
#  Downloads resume dataset from HuggingFace (or Kaggle)
#  Uses a local virtual environment — safe on Debian/Ubuntu 23+ (PEP 668)
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SOURCE="${1:-huggingface}"
DATA_DIR="${DATA_DIR:-$(pwd)/data}"
VENV_DIR="$(pwd)/.venv-dataset"

mkdir -p "$DATA_DIR"
log "Dataset will be saved to: $DATA_DIR"

# ── Create / reuse virtual environment ───────────────────────────────────
# This avoids the PEP 668 "externally-managed-environment" error
# that Debian/Ubuntu 23+ enforces when using system pip.
setup_venv() {
  command -v python3 &>/dev/null || err "python3 not found. Install with: sudo apt install python3 python3-venv"

  if [ ! -d "$VENV_DIR" ]; then
    log "Creating isolated virtual environment at .venv-dataset ..."
    python3 -m venv "$VENV_DIR" || err "Failed to create venv. Try: sudo apt install python3-venv"
    ok "Virtual environment created"
  else
    log "Reusing existing virtual environment"
  fi

  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  pip install --quiet --upgrade pip
}

if [ "$SOURCE" = "kaggle" ]; then
  # ── Kaggle Dataset (500MB+) ───────────────────────────────────────────
  log "Setting up Kaggle download..."
  setup_venv
  pip install --quiet kaggle

  if [ ! -f "$HOME/.kaggle/kaggle.json" ]; then
    if [ -n "${KAGGLE_USERNAME:-}" ] && [ -n "${KAGGLE_KEY:-}" ]; then
      mkdir -p "$HOME/.kaggle"
      echo "{\"username\":\"${KAGGLE_USERNAME}\",\"key\":\"${KAGGLE_KEY}\"}" > "$HOME/.kaggle/kaggle.json"
      chmod 600 "$HOME/.kaggle/kaggle.json"
      ok "Kaggle credentials written from env vars"
    else
      deactivate
      err "No Kaggle credentials. Place kaggle.json at ~/.kaggle/ or set KAGGLE_USERNAME + KAGGLE_KEY"
    fi
  fi

  log "Downloading Kaggle Resume Dataset (~500MB)..."
  kaggle datasets download -d gauravduttakiit/resume-dataset -p "$DATA_DIR" --unzip
  deactivate
  ok "Kaggle dataset downloaded"

elif [ "$SOURCE" = "huggingface" ]; then
  # ── HuggingFace Dataset (no credentials needed) ───────────────────────
  log "Setting up HuggingFace download..."
  setup_venv
  log "Installing: datasets huggingface-hub pandas pyarrow ..."
  pip install --quiet datasets huggingface-hub pandas pyarrow

  python3 - <<PYEOF
import os, sys
DATA_DIR = "${DATA_DIR}"

print("Loading ahmedheakl/resume-atlas from HuggingFace Hub ...")
try:
    from datasets import load_dataset
    ds = load_dataset("ahmedheakl/resume-atlas", trust_remote_code=True)
    df = ds["train"].to_pandas()
    out = os.path.join(DATA_DIR, "resume_atlas.csv")
    df.to_csv(out, index=False)
    size_mb = os.path.getsize(out) / (1024 * 1024)
    print(f"  Samples : {len(df):,}")
    print(f"  Size    : {size_mb:.1f} MB")
    print(f"  Saved   : {out}")
    # Show category distribution
    cat_col = next((c for c in ["Category","category","label"] if c in df.columns), None)
    if cat_col:
        print(f"  Classes : {df[cat_col].nunique()} unique categories")
        print("  Top 5   :", df[cat_col].value_counts().head(5).to_dict())
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

  deactivate

else
  err "Unknown source: '$SOURCE'. Use: huggingface  OR  kaggle"
fi

echo ""
log "Total dataset size: $(du -sh "$DATA_DIR" | cut -f1)"
ok "Dataset ready ✓"
echo ""
echo -e "  Next: ${GREEN}./scripts/train_model.sh${NC}"
echo ""
