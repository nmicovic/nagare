#!/usr/bin/env bash
set -euo pipefail

go build -ldflags="-s -w" -o nagare .
echo "Built: ./nagare ($(du -h nagare | cut -f1))"
