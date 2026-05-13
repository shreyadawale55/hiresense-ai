#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  HireSense AI — Main Deployment Script
#  Usage: ./scripts/deploy.sh [dev|prod] [--build] [--pull-llm]
#  SDG 8: Decent Work and Economic Growth
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; PURPLE='\033[0;35m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
head() { echo -e "\n${PURPLE}══ $* ══${NC}"; }

# ── Banner ──────────────────────────────────────────────────────────────
echo -e "${CYAN}"
cat << 'EOF'
  ██╗  ██╗██╗██████╗ ███████╗███████╗███████╗███╗   ██╗███████╗███████╗
  ██║  ██║██║██╔══██╗██╔════╝██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝
  ███████║██║██████╔╝█████╗  ███████╗█████╗  ██╔██╗ ██║███████╗█████╗
  ██╔══██║██║██╔══██╗██╔══╝  ╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══╝
  ██║  ██║██║██║  ██║███████╗███████║███████╗██║ ╚████║███████║███████╗
  ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝
                    AI Resume Screening · SDG 8 Aligned
EOF
echo -e "${NC}"

# ── Args ────────────────────────────────────────────────────────────────
ENV="${1:-dev}"
BUILD_FLAG=""
PULL_LLM=false

for arg in "$@"; do
  case $arg in
    --build)    BUILD_FLAG="--build" ;;
    --pull-llm) PULL_LLM=true ;;
  esac
done

# ── Validate environment ────────────────────────────────────────────────
head "Environment Check"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
log "Project root: $PROJECT_ROOT"

command -v docker   &>/dev/null || err "Docker not found. Install Docker first."
command -v docker   &>/dev/null && docker compose version &>/dev/null || err "Docker Compose v2 not found."
ok "Docker & Docker Compose available"

# ── Environment file ────────────────────────────────────────────────────
head "Environment Configuration"

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    warn ".env created from .env.example — update SECRET_KEY and passwords before production!"
  else
    err ".env.example not found"
  fi
else
  ok ".env exists"
fi

# Validate critical vars
source .env 2>/dev/null || true
[ -z "${POSTGRES_PASSWORD:-}" ] && warn "POSTGRES_PASSWORD not set — using default (insecure!)"
[ -z "${SECRET_KEY:-}" ]        && warn "SECRET_KEY not set — using default (insecure!)"

# ── Create directories ──────────────────────────────────────────────────
head "Directory Setup"
mkdir -p data/uploads data/models monitoring nginx/ssl
ok "Directories created"

# ── Monitoring config ───────────────────────────────────────────────────
if [ ! -f "monitoring/prometheus.yml" ]; then
  cat > monitoring/prometheus.yml << 'PROM'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'hiresense-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
  - job_name: 'hiresense-ai-model'
    static_configs:
      - targets: ['ai_model:8001']
PROM
  ok "Prometheus config created"
fi

# ── Database init SQL ───────────────────────────────────────────────────
if [ ! -f "backend/init.sql" ]; then
  cat > backend/init.sql << 'SQL'
-- HireSense AI — Database initialization
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- GIN index support
COMMENT ON DATABASE hiresense_db IS 'HireSense AI Resume Screening Database — SDG 8 Aligned';
SQL
  ok "Database init SQL created"
fi

# ── Build & Start services ──────────────────────────────────────────────
head "Starting Services ($ENV mode)"

COMPOSE_PROFILES=""
if [ "$ENV" = "prod" ]; then
  COMPOSE_PROFILES="--profile monitoring"
fi

log "Building and starting Docker services..."
docker compose up -d $BUILD_FLAG $COMPOSE_PROFILES \
  postgres redis backend worker beat flower ai_model frontend nginx

ok "Core services started"

# ── Wait for backend health ─────────────────────────────────────────────
head "Health Checks"
log "Waiting for backend to be ready..."
MAX_WAIT=120
ELAPSED=0
until curl -sf http://localhost:8000/health &>/dev/null || [ $ELAPSED -ge $MAX_WAIT ]; do
  sleep 3; ELAPSED=$((ELAPSED+3))
  echo -n "."
done
echo ""

if curl -sf http://localhost:8000/health &>/dev/null; then
  ok "Backend is healthy ✓"
else
  warn "Backend not ready after ${MAX_WAIT}s — check logs: docker compose logs backend"
fi

# ── Pull Mistral LLM ────────────────────────────────────────────────────
if [ "$PULL_LLM" = true ]; then
  head "Pulling Mistral-7B LLM"
  log "Starting Ollama service..."
  docker compose up -d ollama
  sleep 5
  LLM_MODEL="${LLM_MODEL:-mistral:7b}"
  log "Pulling model: $LLM_MODEL (this may take several minutes)..."
  docker compose exec ollama ollama pull "$LLM_MODEL" && ok "LLM model ready: $LLM_MODEL" \
    || warn "LLM pull failed — system will use rule-based fallback"
fi

# ── Summary ─────────────────────────────────────────────────────────────
head "Deployment Complete 🚀"
echo ""
echo -e "  ${GREEN}Frontend:${NC}   http://localhost:3000"
echo -e "  ${GREEN}API:${NC}        http://localhost:8000"
echo -e "  ${GREEN}API Docs:${NC}   http://localhost:8000/api/docs"
echo -e "  ${GREEN}Flower:${NC}     http://localhost:5555"
echo -e "  ${GREEN}Grafana:${NC}    http://localhost:3001"
echo -e "  ${GREEN}Prometheus:${NC} http://localhost:9090"
echo ""
echo -e "  ${CYAN}Useful commands:${NC}"
echo -e "    docker compose logs -f backend    # Backend logs"
echo -e "    docker compose logs -f worker     # Celery worker logs"
echo -e "    ./scripts/train_model.sh          # Train AI model"
echo -e "    ./scripts/download_dataset.sh     # Download dataset"
echo ""
echo -e "  ${PURPLE}SDG 8:${NC} Fair hiring — skills-first, bias-free AI screening"
echo ""
