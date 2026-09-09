#!/usr/bin/env bash
# Rebuild dist/blender_harness_addon.zip from the blender_addon/ sources.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/blender_harness_addon.zip
zip -rq dist/blender_harness_addon.zip blender_addon -x "*__pycache__*" "*.pyc"
echo "Created dist/blender_harness_addon.zip"
