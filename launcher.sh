#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
app_dir=@APP_DIR@
@STORAGE_SETUP@
export SteamAppId=@APP_ID@
export STEAM_COMPAT_INSTALL_PATH="$app_dir/lepton-app"
export STEAM_COMPAT_DATA_PATH="$app_dir/lepton-data"
export STEAM_COMPAT_SHADER_PATH="$app_dir/lepton-shaders"
export STEAM_COMPAT_LIBRARY_PATHS="$app_dir"
export LEPTON_ENV_FRAMEBRIDGE_CONFIG="$app_dir/settings.conf"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
export IS_PARENT=true
child=''
cleanup() {
    trap - EXIT INT TERM
    # Lepton can leave log/event helpers behind after its main process exits.
    # A private session lets us stop only this launch's descendants.
    if [[ -n "$child" ]]; then kill -TERM -- "-$child" 2>/dev/null || true; fi
    podman kill "lepton-steamlaunch-$SteamAppId" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
setsid @LEPTON@ start >"$app_dir/launch.log" 2>&1 &
child=$!
wait "$child"
