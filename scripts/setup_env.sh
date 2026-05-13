#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  HireSense AI — Environment Setup & Validation Script
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[CHECK]${NC} $*"; }
ok()   { echo -e "${GREEN}[PASS]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC}  $*"; FAILED=$((FAILED+1)); }
FAILED=0

echo -e "\n${BLUE}═══ HireSense AI — System Requirements Check ═══${NC}\n"

# ── Docker ──────────────────────────────────────────────────────────────
log "Docker installation..."
if command -v docker &>/dev/null; then
  DOCKER_VER=$(docker --version | grep -oP '\d+\.\d+')
  ok "Docker $DOCKER_VER"
else
  fail "Docker not installed. Install from https://docs.docker.com/get-docker/"
fi

log "Docker Compose v2..."
if docker compose version &>/dev/null 2>&1; then
  ok "Docker Compose v2 available"
else
  fail "Docker Compose v2 not found. Update Docker Desktop or install plugin."
fi

log "Docker daemon running..."
if docker info &>/dev/null 2>&1; then
  ok "Docker daemon is running"
else
  fail "Docker daemon not running. Start Docker first."
fi

# ── NVIDIA GPU (Optional) ────────────────────────────────────────────────
log "NVIDIA GPU (optional)..."
if command -v nvidia-smi &>/dev/null; then
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
  GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
  ok "GPU: $GPU_NAME ($GPU_MEM)"
  log "  NVIDIA Docker runtime..."
  docker run --rm --gpus all nvidia/cuda:11.0.3-base-ubuntu20.04 nvidia-smi &>/dev/null \
    && ok "  NVIDIA Container Toolkit configured" \
    || warn "  NVIDIA Container Toolkit not configured (GPU won't be used in containers)"
else
  warn "No NVIDIA GPU detected — AI model will run on CPU (slower)"
fi

# ── Disk Space ───────────────────────────────────────────────────────────
log "Disk space (need ≥ 20GB free)..."
FREE_GB=$(df -BG . | awk 'NR==2 {print $4}' | tr -d 'G')
if [ "$FREE_GB" -ge 20 ]; then
  ok "${FREE_GB}GB free disk space"
else
  warn "Only ${FREE_GB}GB free — recommend ≥ 20GB for models + datasets"
fi

# ── RAM ──────────────────────────────────────────────────────────────────
log "RAM (need ≥ 8GB)..."
if command -v free &>/dev/null; then
  RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
  if [ "$RAM_GB" -ge 8 ]; then
    ok "${RAM_GB}GB RAM"
  else
    warn "Only ${RAM_GB}GB RAM — Mistral-7B needs 8GB+ (use phi3:mini as fallback)"
  fi
fi

# ── Ports ────────────────────────────────────────────────────────────────
log "Required ports availability..."
for PORT in 80 3000 5432 5555 6379 8000 8001 9090 11434; do
  if ! ss -tlnp 2>/dev/null | grep -q ":$PORT " && ! netstat -tlnp 2>/dev/null | grep -q ":$PORT "; then
    ok "  Port $PORT: available"
  else
    warn "  Port $PORT: already in use — may conflict"
  fi
done

# ── Python (for local scripts) ───────────────────────────────────────────
log "Python 3.10+..."
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version | grep -oP '\d+\.\d+')
  ok "Python $PY_VER"
else
  warn "Python 3 not found — needed for dataset download scripts"
fi

# ── Environment file ─────────────────────────────────────────────────────
log "Environment configuration (.env)..."
if [ -f ".env" ]; then
  ok ".env file exists"
  # Check for insecure defaults
  if grep -q "change_me\|your-super-secret" .env 2>/dev/null; then
    warn "  .env contains default secrets — change before production!"
  fi
else
  warn ".env not found — run: cp .env.example .env"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}✓ All checks passed! Run: ./scripts/deploy.sh${NC}"
else
  echo -e "${RED}✗ $FAILED check(s) failed. Fix issues above before deploying.${NC}"
  exit 1
fi
echo ""
