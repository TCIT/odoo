#!/usr/bin/env bash
#
# Release phase. Runs once per deploy, before the new web dyno is started,
# and aborts the release if it exits non-zero.
#
# Heroku provisions an empty database, so the very first release installs
# Odoo into it. Later releases only update the modules named in
# ODOO_UPDATE_MODULES, which is empty by default: a blanket "-u all" on
# every deploy is slow and rewrites data, so it should be an explicit
# decision (typically after upgrading the Odoo series).
set -euo pipefail

HEROKU_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ODOO_APP_ROOT:-/app}"

CONFIG_FILE="${ODOO_CONFIG_FILE:-/tmp/odoo.conf}"

python3 "${HEROKU_DIR}/render_config.py"

if python3 "${HEROKU_DIR}/bootstrap.py" is-initialized; then
    echo "odoo: existing installation found"
    if [ -n "${ODOO_UPDATE_MODULES:-}" ]; then
        echo "odoo: updating modules: ${ODOO_UPDATE_MODULES}"
        ./odoo-bin --config "${CONFIG_FILE}" \
                   --update "${ODOO_UPDATE_MODULES}" \
                   --stop-after-init
    else
        echo "odoo: ODOO_UPDATE_MODULES is empty, no module update to run"
    fi
else
    echo "odoo: empty database, installing modules: ${ODOO_INIT_MODULES:-base}"
    ./odoo-bin --config "${CONFIG_FILE}" \
               --init "${ODOO_INIT_MODULES:-base}" \
               --stop-after-init
fi

python3 "${HEROKU_DIR}/bootstrap.py" sync-parameters

echo "odoo: release phase finished"
