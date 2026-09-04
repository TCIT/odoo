#!/usr/bin/env bash
#
# Web process. Renders the configuration from the environment, then hands
# over to the Odoo server, which must stay in the foreground as PID 1's
# child so that the dyno manager can signal it.
set -euo pipefail

HEROKU_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ODOO_APP_ROOT:-/app}"

python3 "${HEROKU_DIR}/render_config.py"

exec ./odoo-bin --config "${ODOO_CONFIG_FILE:-/tmp/odoo.conf}" "$@"
