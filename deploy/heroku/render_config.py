#!/usr/bin/env python3
"""Render an Odoo configuration file from the process environment.

Heroku hands the application a single ``DATABASE_URL`` and an HTTP ``PORT``
to bind, while Odoo expects a configuration file. This script bridges the
two. It is executed by both the release phase and the web process so that
they always run against the exact same settings.

Every value can be overridden with an ``ODOO_*`` environment variable; the
defaults are chosen to be correct on a Heroku dyno.
"""

import os
import sys
from urllib.parse import unquote, urlsplit

DEFAULT_CONFIG_FILE = "/tmp/odoo.conf"
DEFAULT_DATA_DIR = "/tmp/odoo-data"
APP_ROOT = os.environ.get("ODOO_APP_ROOT", "/app")


class ConfigError(Exception):
    """Raised when the environment cannot produce a usable configuration."""


def parse_database_url(url):
    """Split a libpq style URL into the db_* options Odoo expects."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise ConfigError(
            "DATABASE_URL must use the postgres:// or postgresql:// scheme, "
            "got %r" % (parts.scheme or "<none>",)
        )
    database = parts.path.lstrip("/")
    if not database:
        raise ConfigError("DATABASE_URL does not contain a database name")
    return {
        "db_host": parts.hostname or "localhost",
        "db_port": parts.port or 5432,
        "db_user": unquote(parts.username or ""),
        "db_password": unquote(parts.password or ""),
        "db_name": database,
    }


def env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def addons_path():
    """Core addons, plus an optional directory for the project's own modules.

    ``custom-addons`` is only added when it exists: Odoo refuses to start on
    an addons_path entry that points nowhere.
    """
    paths = [os.path.join(APP_ROOT, "addons"), os.path.join(APP_ROOT, "odoo", "addons")]
    for extra in os.environ.get("ODOO_EXTRA_ADDONS_PATH", "custom-addons").split(","):
        extra = extra.strip()
        if not extra:
            continue
        if not os.path.isabs(extra):
            extra = os.path.join(APP_ROOT, extra)
        if os.path.isdir(extra):
            paths.insert(0, extra)
    return ",".join(paths)


def build_options():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigError(
            "DATABASE_URL is not set. On Heroku it is provisioned by the "
            "heroku-postgresql add-on; locally, point it at your own server."
        )
    options = parse_database_url(database_url)

    admin_passwd = os.environ.get("ODOO_ADMIN_PASSWD")
    if not admin_passwd:
        raise ConfigError(
            "ODOO_ADMIN_PASSWD is not set. It protects the database manager "
            "and must never be left on Odoo's 'admin' default. Set it with: "
            "heroku config:set ODOO_ADMIN_PASSWD=$(openssl rand -base64 32)"
        )
    options["admin_passwd"] = admin_passwd

    # Heroku Postgres only accepts TLS connections.
    options["db_sslmode"] = os.environ.get("ODOO_DB_SSLMODE", "require")
    # Essential-tier databases cap connections at 20, shared between the web
    # dyno, the release dyno and any one-off dyno, so stay well below it.
    options["db_maxconn"] = os.environ.get("ODOO_DB_MAXCONN", "5")

    # A single database, never exposed through the database manager.
    options["dbfilter"] = "^%s$" % options["db_name"]
    options["list_db"] = env_bool("ODOO_LIST_DB", False)

    options["addons_path"] = addons_path()
    options["data_dir"] = os.environ.get("ODOO_DATA_DIR", DEFAULT_DATA_DIR)

    # The router forwards everything to a single port, so bind all interfaces.
    options["http_interface"] = "0.0.0.0"
    options["http_port"] = os.environ.get("PORT", "8069")
    options["proxy_mode"] = env_bool("ODOO_PROXY_MODE", True)

    # workers must stay at 0: in prefork mode Odoo serves websockets from a
    # second (gevent) port, and a dyno only ever exposes one port.
    options["workers"] = os.environ.get("ODOO_WORKERS", "0")
    options["max_cron_threads"] = os.environ.get("ODOO_MAX_CRON_THREADS", "1")
    options["limit_time_real"] = os.environ.get("ODOO_LIMIT_TIME_REAL", "120")
    options["limit_time_cpu"] = os.environ.get("ODOO_LIMIT_TIME_CPU", "60")

    options["without_demo"] = env_bool("ODOO_WITHOUT_DEMO", True)
    options["log_level"] = os.environ.get("ODOO_LOG_LEVEL", "info")
    options["logfile"] = ""  # stdout, where the Heroku log drain reads from

    return options


def render(options, extra):
    lines = ["[options]"]
    for key in sorted(options):
        lines.append("%s = %s" % (key, options[key]))
    for line in extra.splitlines():
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines) + "\n"


def main():
    try:
        options = build_options()
    except ConfigError as exc:
        sys.stderr.write("odoo: %s\n" % exc)
        return 1

    path = os.environ.get("ODOO_CONFIG_FILE", DEFAULT_CONFIG_FILE)
    content = render(options, os.environ.get("ODOO_CONFIG_EXTRA", ""))
    with open(path, "w") as fobj:
        fobj.write(content)
    os.chmod(path, 0o600)

    os.makedirs(options["data_dir"], exist_ok=True)

    sys.stderr.write(
        "odoo: wrote %s (database %s on %s, http port %s, workers %s)\n"
        % (path, options["db_name"], options["db_host"],
           options["http_port"], options["workers"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
