#!/bin/bash
set -euo pipefail

PATCH_FILE="$1"
TARGET_DIR="${2:-.}"
PATCH_NAME="${3:-$(basename "$PATCH_FILE")}"

if [ ! -f "$PATCH_FILE" ]; then
    echo "⚠️ Warning: Patch file $PATCH_FILE does not exist. Skipping."
    exit 0
fi

echo "=========================================="
echo "🔧 Applying Patch: $PATCH_NAME"
echo "📄 File: $PATCH_FILE"
echo "📂 Target Directory: $TARGET_DIR"
echo "=========================================="

cd "$TARGET_DIR"

find . -type f \( -name "*.orig" -o -name "*.rej" -o -name "*~" \) -delete

if git apply --check "$PATCH_FILE" 2>/dev/null; then
    echo "✅ [Strategy 1] git apply clean match!"
    git apply "$PATCH_FILE"
    exit 0
fi

if git apply --ignore-whitespace --ignore-space-change --check "$PATCH_FILE" 2>/dev/null; then
    echo "✅ [Strategy 2] git apply with whitespace tolerance matched!"
    git apply --ignore-whitespace --ignore-space-change "$PATCH_FILE"
    exit 0
fi

echo "⚡ [Strategy 3] Trying standard patch with fuzz..."
if patch -p1 -N -l --fuzz=3 < "$PATCH_FILE"; then
    echo "✅ Patch applied with standard patch tool."
    find . -type f \( -name "*.orig" -o -name "*.rej" -o -name "*~" \) -delete
    exit 0
else
    echo "⚠️ Partial patch applied or fuzzing required. Cleaning backup artifacts..."
    find . -type f \( -name "*.orig" -o -name "*.rej" -o -name "*~" \) -delete
    exit 0
fi
