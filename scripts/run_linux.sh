#!/usr/bin/env bash
# ==============================================================================
# Earth Pulse — Production Application Launcher
# NASA Space Apps Challenge 2026: Dancing with the SARs
# ==============================================================================
# Starts the high-performance unified FastAPI + WebGIS application service.
# ==============================================================================

set -uo pipefail

# ANSI Styling
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Default Runtime Parameters
HOST="127.0.0.1"
PORT="8000"
DEMO_MODE="true"

# Parse CLI options
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --unrestricted)
      DEMO_MODE="false"
      shift
      ;;
    --demo)
      DEMO_MODE="true"
      shift
      ;;
    -h|--help)
      echo "Usage: bash scripts/run_linux.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --host <ip>        Bind address (default: 127.0.0.1)"
      echo "  --port <port>      Listen port (default: 8000)"
      echo "  --demo             Safe demo mode with compute protection (default)"
      echo "  --unrestricted     Enable dynamic NASA ASF downloads and SNAP processing"
      echo "  -h, --help         Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Load environment configuration if present
if [ -f "${REPO_ROOT}/.env" ]; then
  # shellcheck source=/dev/null
  set -a
  . "${REPO_ROOT}/.env"
  set +a
  HOST="${HOST:-127.0.0.1}"
  PORT="${PORT:-8000}"
fi

export DEMO_MODE_RESTRICTED_EXECUTION="${DEMO_MODE}"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

# Check for Python Virtual Environment
PYTHON_BIN="python3"
if [ -d "${REPO_ROOT}/.venv" ] && [ -x "${REPO_ROOT}/.venv/bin/python3" ]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python3"
elif ! command -v python3 >/dev/null 2>&1; then
  echo -e "${RED}Error: Python 3 not found. Run bash scripts/install_linux.sh first.${NC}"
  exit 1
fi

# Verify Frontend Distribution
DIST_INDEX="${REPO_ROOT}/frontend/dist/index.html"
if [ ! -f "${DIST_INDEX}" ]; then
  echo -e "${YELLOW}Notice: Built frontend not found at frontend/dist/index.html${NC}"
  echo -e "Building frontend distribution..."
  if command -v npm >/dev/null 2>&1; then
    (cd "${REPO_ROOT}/frontend" && npm run build)
  else
    echo -e "${RED}Error: npm not found to build frontend. Please run scripts/install_linux.sh${NC}"
    exit 1
  fi
fi

# Banner
echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "${BOLD}${CYAN}🛰️  EARTH PULSE — SATELLITE RADAR HYDROLOGY & EXPLAINABLE AI${NC}"
echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "  • Web Application:  ${BOLD}${GREEN}http://${HOST}:${PORT}${NC}"
echo -e "  • Interactive Docs: ${BOLD}${CYAN}http://${HOST}:${PORT}/docs${NC}"
echo -e "  • Health Check:     ${BOLD}${CYAN}http://${HOST}:${PORT}/health${NC}"

if [ "${DEMO_MODE}" = "true" ]; then
  echo -e "  • Operating Mode:   ${GREEN}Public Demo Mode (Compute Protection Active)${NC}"
  echo -e "                      Serving authentic precomputed 2024 & 2025 Jamuna campaigns."
else
  echo -e "  • Operating Mode:   ${YELLOW}UNRESTRICTED Dynamic SAR Execution Mode${NC}"
  echo -e "                      Dynamic NASA ASF downloads & ESA SNAP processing ENABLED."
fi
echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "Press ${BOLD}Ctrl+C${NC} to stop the server cleanly.\n"

# Process management & graceful shutdown
SERVER_PID=""
cleanup() {
  echo -e "\n${YELLOW}Shutting down Earth Pulse server (PID: ${SERVER_PID:-none})...${NC}"
  if [ -n "${SERVER_PID}" ] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill -TERM "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  echo -e "${GREEN}Server stopped cleanly.${NC}"
  exit 0
}

trap cleanup SIGINT SIGTERM SIGHUP

# Launch uvicorn
"${PYTHON_BIN}" -m uvicorn src.backend.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --log-level info &

SERVER_PID=$!
wait "${SERVER_PID}"

