#!/bin/sh
command -v python3 >/dev/null 2>&1 || { echo "divorce: python3 (3.9+) is required" >&2; exit 1; }
exec python3 "$(dirname "$0")/install.py" "$@"
