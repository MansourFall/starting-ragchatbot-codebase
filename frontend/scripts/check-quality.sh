#!/usr/bin/env bash
# check-quality.sh — Run all frontend code quality checks
# Usage: ./scripts/check-quality.sh [--fix]
#
# Options:
#   --fix    Auto-fix formatting and linting issues where possible

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$FRONTEND_DIR"

FIX_MODE=false
for arg in "$@"; do
  if [ "$arg" = "--fix" ]; then
    FIX_MODE=true
  fi
done

echo "================================================"
echo " Frontend Code Quality Checks"
echo "================================================"
echo ""

# Ensure node_modules exist
if [ ! -d "node_modules" ]; then
  echo "[setup] Installing dependencies..."
  npm install
  echo ""
fi

# ── Prettier ─────────────────────────────────────────
echo "[1/2] Prettier — formatting check"
if [ "$FIX_MODE" = true ]; then
  npx prettier --write "**/*.{js,css,html}"
  echo "       Formatting applied."
else
  if npx prettier --check "**/*.{js,css,html}"; then
    echo "       All files are properly formatted."
  else
    echo ""
    echo "  Run './scripts/check-quality.sh --fix' to auto-format."
    exit 1
  fi
fi
echo ""

# ── ESLint ────────────────────────────────────────────
echo "[2/2] ESLint — JavaScript linting"
if [ "$FIX_MODE" = true ]; then
  npx eslint --fix "**/*.js" || true
  echo "       Auto-fixable issues resolved."
else
  npx eslint "**/*.js" || {
    echo ""
    echo "  Run './scripts/check-quality.sh --fix' to auto-fix ESLint errors."
    exit 1
  }
fi
echo ""

echo "================================================"
echo " All quality checks passed!"
echo "================================================"
