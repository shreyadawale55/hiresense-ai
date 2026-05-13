#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  HireSense AI — Model Training Script
#  Trains PyTorch resume scorer using the downloaded dataset
#  Usage: ./scripts/train_model.sh [--source kaggle|huggingface] [--epochs 30] [--gpu]
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; PURPLE='\033[0;35m'; NC='\033[0m'
log()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Defaults ─────────────────────────────────────────────────────────────
SOURCE="huggingface"; EPOCHS=30; BATCH_SIZE=64; DEVICE=""

for arg in "$@"; do
  case $arg in
    --source=*)   SOURCE="${arg#*=}" ;;
    --epochs=*)   EPOCHS="${arg#*=}" ;;
    --batch=*)    BATCH_SIZE="${arg#*=}" ;;
    --gpu)        DEVICE="cuda" ;;
    --cpu)        DEVICE="cpu" ;;
  esac
done

echo -e "${PURPLE}══ HireSense AI Model Trainer ══${NC}"
log "Source:     $SOURCE"
log "Epochs:     $EPOCHS"
log "Batch size: $BATCH_SIZE"

# ── Check dataset ─────────────────────────────────────────────────────────
DATA_DIR="${DATA_DIR:-$(pwd)/data}"
if [ ! "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
  warn "No dataset found. Downloading first..."
  bash "$(dirname "$0")/download_dataset.sh" "$SOURCE"
fi

# ── Train inside Docker container ──────────────────────────────────────────
log "Starting training via Docker..."

GPU_ARGS=""
if [ "${DEVICE}" = "cuda" ] || ([ -z "$DEVICE" ] && command -v nvidia-smi &>/dev/null); then
  GPU_ARGS="--gpus all"
  log "CUDA GPU detected — training on GPU"
else
  log "Training on CPU (use --gpu flag for GPU acceleration)"
fi

docker run --rm $GPU_ARGS \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/data/models:/app/models" \
  -e DATA_DIR=/app/data \
  -e MODEL_DIR=/app/models \
  hiresense-ai-ai_model \
  python -m trainer.train \
    --source "$SOURCE" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    ${DEVICE:+--device "$DEVICE"}

ok "Training complete!"
log "Model saved to: $(pwd)/data/models/resume_scorer.pt"

# ── Copy model to shared volume ────────────────────────────────────────────
if docker compose ps | grep -q "hiresense_backend"; then
  log "Restarting workers to load new model..."
  docker compose restart worker ai_model
  ok "Workers restarted with new model"
fi

echo ""
echo -e "${GREEN}✓ Model training complete!${NC}"
echo -e "  Model:          data/models/resume_scorer.pt"
echo -e "  Evaluation:     data/models/evaluation_report.json"
echo -e "  Training curves: data/models/training_curves.png"
echo ""
