#!/usr/bin/env bash
# ==============================================================================
# Earth Pulse — Linux System Prerequisites Checker
# NASA Space Apps Challenge 2026: Dancing with the SARs
# ==============================================================================
# Validates system requirements, runtimes, and libraries before installation.
# Safe, read-only: does not modify system files or run privileged commands.
# ==============================================================================

set -uo pipefail

# ANSI Color Codes
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}========================================================================${NC}"
echo -e "${BOLD}${CYAN}🛰️  EARTH PULSE — LINUX SYSTEM PREREQUISITES AUDIT${NC}"
echo -e "${BOLD}${CYAN}========================================================================${NC}"

MISSING_REQUIRED=0
WARNINGS=0

# ------------------------------------------------------------------------------
# 1. Operating System & Architecture
# ------------------------------------------------------------------------------
ARCH=$(uname -m)
OS_NAME="Linux"
if [ -f /etc/os-release ]; then
  # shellcheck source=/dev/null
  . /etc/os-release
  OS_NAME="${PRETTY_NAME:-Linux}"
fi

echo -e "\n${BOLD}[1/6] Operating System & Hardware Architecture${NC}"
echo -e "  • Operating System: ${GREEN}${OS_NAME}${NC}"
if [ "$ARCH" = "x86_64" ]; then
  echo -e "  • Architecture:     ${GREEN}${ARCH} (Officially Supported)${NC}"
else
  echo -e "  • Architecture:     ${YELLOW}${ARCH} (Notice: x86_64 is primary scientific target)${NC}"
  ((WARNINGS++))
fi

# ------------------------------------------------------------------------------
# 2. Python Environment (>= 3.10 required)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[2/6] Python Runtime & Virtual Environment Support${NC}"
if command -v python3 >/dev/null 2>&1; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
  PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
  PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

  if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 10 ]; then
    echo -e "  • Python:           ${GREEN}Python ${PY_VER}${NC} (Meets requirement: >= 3.10)"
  else
    echo -e "  • Python:           ${RED}Python ${PY_VER}${NC} (Required: >= 3.10)"
    ((MISSING_REQUIRED++))
  fi

  # Check python3-venv module
  if python3 -c "import venv" >/dev/null 2>&1; then
    echo -e "  • venv module:      ${GREEN}Available${NC}"
  else
    echo -e "  • venv module:      ${RED}Missing (python3-venv required)${NC}"
    ((MISSING_REQUIRED++))
  fi
else
  echo -e "  • Python 3:         ${RED}NOT FOUND${NC}"
  ((MISSING_REQUIRED++))
fi

# ------------------------------------------------------------------------------
# 3. Node.js & npm (Node >= 18, npm >= 9)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[3/6] JavaScript Runtime & Frontend Package Manager${NC}"
if command -v node >/dev/null 2>&1; then
  NODE_VER=$(node -v | sed 's/v//')
  NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 18 ]; then
    echo -e "  • Node.js:          ${GREEN}v${NODE_VER}${NC} (Meets requirement: >= 18)"
  else
    echo -e "  • Node.js:          ${RED}v${NODE_VER}${NC} (Required: >= 18)"
    ((MISSING_REQUIRED++))
  fi
else
  echo -e "  • Node.js:          ${RED}NOT FOUND (Required for frontend build)${NC}"
  ((MISSING_REQUIRED++))
fi

if command -v npm >/dev/null 2>&1; then
  NPM_VER=$(npm -v)
  NPM_MAJOR=$(npm -v | cut -d. -f1)
  if [ "$NPM_MAJOR" -ge 9 ]; then
    echo -e "  • npm:              ${GREEN}v${NPM_VER}${NC} (Meets requirement: >= 9)"
  else
    echo -e "  • npm:              ${YELLOW}v${NPM_VER}${NC} (Recommended: >= 9)"
    ((WARNINGS++))
  fi
else
  echo -e "  • npm:              ${RED}NOT FOUND${NC}"
  ((MISSING_REQUIRED++))
fi

# ------------------------------------------------------------------------------
# 4. Geospatial Tools & System Utilities
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[4/6] Geospatial Utilities & Build Tools${NC}"
for tool in gdalinfo unzip curl git; do
  if command -v "$tool" >/dev/null 2>&1; then
    TOOL_PATH=$(command -v "$tool")
    echo -e "  • ${tool}:           ${GREEN}Available${NC} (${TOOL_PATH})"
  else
    if [ "$tool" = "gdalinfo" ]; then
      echo -e "  • ${tool}:           ${RED}NOT FOUND (Package: gdal-bin / libgdal-dev)${NC}"
      ((MISSING_REQUIRED++))
    else
      echo -e "  • ${tool}:           ${RED}NOT FOUND${NC}"
      ((MISSING_REQUIRED++))
    fi
  fi
done

# ------------------------------------------------------------------------------
# 5. Optional: ESA SNAP Radar Processing Graph Tool (GPT)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[5/6] Optional: ESA SNAP Graph Processing Tool (GPT)${NC}"
SNAP_CANDIDATES=(
  "${SNAP_GPT_PATH:-}"
  "$HOME/esa-snap/bin/gpt"
  "/opt/esa-snap/bin/gpt"
  "/usr/local/snap/bin/gpt"
)
FOUND_GPT=""

if command -v gpt >/dev/null 2>&1; then
  FOUND_GPT=$(command -v gpt)
else
  for cand in "${SNAP_CANDIDATES[@]}"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then
      FOUND_GPT="$cand"
      break
    fi
  done
fi

if [ -n "$FOUND_GPT" ]; then
  echo -e "  • SNAP GPT:         ${GREEN}Detected${NC} (${FOUND_GPT})"
  echo -e "  • Dynamic SAR:      ${GREEN}Full local Level-1 GRD pipeline enabled${NC}"
else
  echo -e "  • SNAP GPT:         ${CYAN}Not installed / not on PATH (Optional)${NC}"
  echo -e "  • Status:           ${GREEN}Demo mode fully functional without SNAP${NC}"
  echo -e "                      To enable new dynamic SAR processing, download SNAP from:"
  echo -e "                      https://step.esa.int/main/download/snap-download/"
  echo -e "                      Then set: export SNAP_GPT_PATH=/path/to/snap/bin/gpt"
fi

# ------------------------------------------------------------------------------
# 6. Optional: NASA Earthdata Authentication
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[6/6] Optional: NASA Earthdata ASF DAAC Credentials${NC}"
NETRC_FILE="$HOME/.netrc"
if [ -f "$NETRC_FILE" ]; then
  if grep -q "urs.earthdata.nasa.gov" "$NETRC_FILE" 2>/dev/null; then
    PERMS=$(stat -c "%a" "$NETRC_FILE" 2>/dev/null || stat -f "%Lp" "$NETRC_FILE" 2>/dev/null)
    if [ "$PERMS" = "600" ] || [ "$PERMS" = "400" ]; then
      echo -e "  • NASA Earthdata:   ${GREEN}Configured in ~/.netrc (Permissions: ${PERMS})${NC}"
    else
      echo -e "  • NASA Earthdata:   ${YELLOW}Configured, but ~/.netrc permissions are ${PERMS} (Must be 600)${NC}"
      echo -e "                      Fix: chmod 600 ~/.netrc"
      ((WARNINGS++))
    fi
  else
    echo -e "  • NASA Earthdata:   ${CYAN}~/.netrc found, but no urs.earthdata.nasa.gov entry (Optional)${NC}"
  fi
else
  echo -e "  • NASA Earthdata:   ${CYAN}No ~/.netrc found (Optional for demo mode)${NC}"
  echo -e "                      Viewing archived campaigns does not require credentials."
  echo -e "                      To enable raw downloads: create ~/.netrc with Earthdata credentials."
fi

# ------------------------------------------------------------------------------
# Summary & Exit Code
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}${CYAN}========================================================================${NC}"
if [ "$MISSING_REQUIRED" -eq 0 ]; then
  echo -e "${BOLD}${GREEN}✅ ALL REQUIRED PREREQUISITES ARE MET!${NC}"
  if [ "$WARNINGS" -gt 0 ]; then
    echo -e "${YELLOW}Notice: ${WARNINGS} non-critical recommendation(s) noted above.${NC}"
  fi
  echo -e "Ready to run installation: ${BOLD}bash scripts/install_linux.sh${NC}"
  echo -e "${BOLD}${CYAN}========================================================================${NC}\n"
  exit 0
else
  echo -e "${BOLD}${RED}❌ MISSING ${MISSING_REQUIRED} REQUIRED PREREQUISITE(S)${NC}"
  echo -e "Please install missing packages before running the Earth Pulse installer."
  echo -e "\nOn Ubuntu / Debian / Kali Linux, install them with:"
  echo -e "  ${BOLD}sudo apt update && sudo apt install -y \\${NC}"
  echo -e "    ${BOLD}python3 python3-venv python3-pip nodejs npm \\${NC}"
  echo -e "    ${BOLD}gdal-bin libgdal-dev unzip curl git${NC}"
  echo -e "${BOLD}${CYAN}========================================================================${NC}\n"
  exit 1
fi

