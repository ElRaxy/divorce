#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

jar=0
destination=
for argument in "$@"; do
    case "$argument" in
        --jar) jar=1 ;;
        --help|-h)
            printf '%s\n' 'Usage: install-vnu.sh [--jar] [DESTINATION]' \
                'Install the official Nu HTML Checker after verifying its SHA-1.' \
                'Default destination: ~/.local/share/vnu'
            exit 0 ;;
        -*) fail "Unknown option: $argument" ;;
        *)
            [ -z "$destination" ] || fail 'Only one destination is allowed.'
            destination=$argument ;;
    esac
done
destination=${destination:-"$HOME/.local/share/vnu"}
case "$destination" in
    /*) ;;
    *) destination=$PWD/$destination ;;
esac

command -v curl >/dev/null 2>&1 || fail 'curl is required.'
if command -v shasum >/dev/null 2>&1; then
    hash_command=shasum
elif command -v sha1sum >/dev/null 2>&1; then
    hash_command=sha1sum
else
    fail 'shasum or sha1sum is required.'
fi
if [ "$jar" -eq 1 ]; then
    command -v java >/dev/null 2>&1 || fail 'Java is required for --jar.'
    asset=vnu.jar
    target=$destination/vnu.jar
else
    command -v unzip >/dev/null 2>&1 || fail 'unzip is required.'
    case "$(uname -s)" in
        Darwin) asset=vnu.osx.zip ;;
        Linux) asset=vnu.linux.zip ;;
        *) fail 'Unsupported operating system; use --jar.' ;;
    esac
    target=$destination/vnu-runtime-image
fi
[ ! -e "$target" ] && [ ! -L "$target" ] || fail 'The installation target already exists.'
mkdir -p "$destination" || fail 'Cannot create the destination.'
stage=$(mktemp -d "$destination/.vnu-install.XXXXXX") || fail 'Cannot create a staging directory.'
installed=
success=0
cleanup() {
    status=$?
    trap - 0
    rm -rf "$stage"
    if [ "$success" -eq 0 ] && [ -n "$installed" ]; then
        rm -rf "$installed"
    fi
    exit "$status"
}
trap cleanup 0
trap 'exit 1' HUP INT TERM

base=https://github.com/validator/validator/releases/latest/download
for name in "$asset" "$asset.sha1"; do
    if ! curl --fail --location --silent --show-error --connect-timeout 15 \
        --max-time 300 --output "$stage/$name" "$base/$name"; then
        fail "Download failed: $name"
    fi
done
expected=$(awk 'NR == 1 {print tolower($1)}' "$stage/$asset.sha1")
[ "${#expected}" -eq 40 ] || fail 'Invalid SHA-1 checksum file.'
case "$expected" in
    *[!0-9a-f]*) fail 'Invalid SHA-1 checksum file.' ;;
esac
if [ "$hash_command" = shasum ]; then
    actual=$(shasum -a 1 "$stage/$asset") || fail 'Cannot compute SHA-1.'
else
    actual=$(sha1sum "$stage/$asset") || fail 'Cannot compute SHA-1.'
fi
actual=${actual%% *}
[ "$actual" = "$expected" ] || fail 'SHA-1 checksum mismatch.'

if [ "$jar" -eq 1 ]; then
    mv "$stage/$asset" "$target" || fail 'Cannot install the JAR.'
    installed=$target
    java -jar "$target" --version >&2 || fail 'The installed validator failed its version check.'
    binary=$target
else
    mkdir "$stage/extracted" || fail 'Cannot create the extraction directory.'
    unzip -q "$stage/$asset" -d "$stage/extracted" || fail 'Cannot extract the validator.'
    [ -x "$stage/extracted/vnu-runtime-image/bin/vnu" ] || fail 'Validator binary not found in the archive.'
    mv "$stage/extracted/vnu-runtime-image" "$target" || fail 'Cannot install the validator.'
    installed=$target
    binary=$target/bin/vnu
    "$binary" --version >&2 || fail 'The installed validator failed its version check.'
fi
success=1
printf '%s\n' "$binary"
