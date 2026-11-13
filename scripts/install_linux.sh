#!/usr/bin/env bash
# ==============================================================================
# Earth Pulse — Automated Linux Installer
# NASA Space Apps Challenge 2026: Dancing with the SARs
# ==============================================================================
# Performs complete, isolated setup of backend, frontend, database, and demo data.
# Safe & reproducible: does NOT require root privileges.
# ==============================================================================

set -euo pipefail

# Color palette
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "${BOLD}${CYAN}🚀  EARTH PULSE — AUTOMATED LINUX INSTALLATION${NC}"
echo -e "${BOLD}${CYAN}========================================================================${NC}"

# Step 1: Check System Prerequisites
echo -e "\n${BOLD}[Step 1/6] Auditing System Prerequisites...${NC}"
if ! bash "${SCRIPT_DIR}/check_prerequisites.sh"; then
  echo -e "\n${BOLD}${RED}Installation aborted: missing required system prerequisites.${NC}"
  exit 1
fi

# Step 2: Set up Python Virtual Environment (.venv)
echo -e "\n${BOLD}[Step 2/6] Configuring Python Virtual Environment...${NC}"
VENV_DIR="${REPO_ROOT}/.venv"
if [ ! -d "${VENV_DIR}" ]; then
  echo -e "  • Creating virtual environment in ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
else
  echo -e "  • Existing virtual environment detected in ${VENV_DIR}."
fi

VENV_PYTHON="${VENV_DIR}/bin/python3"
VENV_PIP="${VENV_DIR}/bin/pip"

echo -e "  • Upgrading pip, setuptools, wheel..."
"${VENV_PIP}" install --upgrade pip setuptools wheel >/dev/null 2>&1

echo -e "  • Installing Python dependencies from requirements.txt..."
"${VENV_PIP}" install -r "${REPO_ROOT}/requirements.txt"

# Step 3: Install Frontend Dependencies & Build Static Bundle
echo -e "\n${BOLD}[Step 3/6] Setting Up React/TypeScript Frontend...${NC}"
FRONTEND_DIR="${REPO_ROOT}/frontend"
if [ ! -d "${FRONTEND_DIR}" ]; then
  echo -e "${RED}Error: frontend directory missing at ${FRONTEND_DIR}${NC}"
  exit 1
fi

echo -e "  • Installing npm dependencies..."
(cd "${FRONTEND_DIR}" && npm install --silent)

echo -e "  • Building production WebGIS bundle (tsc && vite build)..."
(cd "${FRONTEND_DIR}" && npm run build)

if [ -f "${FRONTEND_DIR}/dist/index.html" ]; then
  DIST_SIZE=$(du -sh "${FRONTEND_DIR}/dist" | cut -f1)
  echo -e "  • ${GREEN}Frontend build verified${NC} (dist/ size: ${DIST_SIZE})"
else
  echo -e "${RED}Error: Frontend build failed to produce dist/index.html${NC}"
  exit 1
fi

# Step 4: Initialize Metadata Database & Data Directories
echo -e "\n${BOLD}[Step 4/6] Initializing Database & Workspace Directories...${NC}"
mkdir -p "${REPO_ROOT}/data/metadata"
mkdir -p "${REPO_ROOT}/data/runs"
mkdir -p "${REPO_ROOT}/data/raw"

"${VENV_PYTHON}" -c "
import sys
sys.path.insert(0, '${REPO_ROOT}')
from src.backend.database.database import init_db
init_db()
print('  • SQLite database initialized and seeded.')
"

# Step 5: Check & Verify Scientific Demonstration Data
echo -e "\n${BOLD}[Step 5/6] Scientific Demonstration Data Detection & Verification...${NC}"
RUN_2024="${REPO_ROOT}/data/runs/run_20261110_221732_1f2e94"
RUN_2025="${REPO_ROOT}/data/runs/run_20261111_164348_f3c2b8"

if [ ! -d "${RUN_2024}" ] || [ ! -d "${RUN_2025}" ]; then
  echo -e "  • Demonstration runs not found in data/runs/."
  ZIP_CANDIDATES=(
    "${REPO_ROOT}/EARTH_PULSE_PORTABLE_DEMO_DATA.zip"
    "${REPO_ROOT}/../EARTH_PULSE_PORTABLE_DEMO_DATA.zip"
    "${REPO_ROOT}/../EarthPulse-Upload-Ready/EARTH_PULSE_PORTABLE_DEMO_DATA.zip"
  )
  FOUND_ZIP=""
  for cand in "${ZIP_CANDIDATES[@]}"; do
    if [ -f "$cand" ]; then
      FOUND_ZIP="$cand"
      break
    fi
  done

  if [ -n "$FOUND_ZIP" ]; then
    echo -e "  • Found demo data archive: ${FOUND_ZIP}"
    echo -e "  • Unpacking demo data into ${REPO_ROOT}..."
    unzip -q -o "$FOUND_ZIP" -d "${REPO_ROOT}"
  else
    echo -e "  ${YELLOW}Notice: Demo data archive EARTH_PULSE_PORTABLE_DEMO_DATA.zip not found.${NC}"
    echo -e "  Please download it from the GitHub Release page and extract into the project root:"
    echo -e "    ${BOLD}unzip EARTH_PULSE_PORTABLE_DEMO_DATA.zip -d .${NC}"
  fi
fi

# Run integrity verification
if [ -d "${RUN_2024}" ] && [ -d "${RUN_2025}" ]; then
  bash "${SCRIPT_DIR}/verify_integrity.sh"
else
  echo -e "  ${YELLOW}Skipping data integrity audit until demo data is unpacked.${NC}"
fi

# Step 6: Safe Environment Configuration
echo -e "\n${BOLD}[Step 6/6] Configuring Application Environment...${NC}"
ENV_FILE="${REPO_ROOT}/.env"
if [ ! -f "${ENV_FILE}" ]; then
  echo -e "  • Creating default safe .env configuration..."
  cat <<'EOF' > "${ENV_FILE}"
# Earth Pulse — Environment Configuration
# Public Demo Mode: compute protection enabled by default
DEMO_MODE_RESTRICTED_EXECUTION=true
PROJECT_NAME="Earth Pulse SAR API"
PORT=8000
HOST=127.0.0.1
EOF
  echo -e "  • ${GREEN}.env created with DEMO_MODE_RESTRICTED_EXECUTION=true${NC}"
else
  echo -e "  • Preserving existing .env configuration."
fi

# ------------------------------------------------------------------------------
# Installation Success Summary
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}${CYAN}========================================================================${NC}"
echo -e "${BOLD}${GREEN}🎉  EARTH PULSE INSTALLATION COMPLETED SUCCESSFULLY!${NC}"
echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "To start the application, execute:"
echo -e "  ${BOLD}${GREEN}bash scripts/run_linux.sh${NC}"
echo -e "\nThen open your browser at:"
echo -e "  ${BOLD}${CYAN}http://127.0.0.1:8000${NC}"
echo -e "${BOLD}${CYAN}========================================================================${NC}\n"

