#!/usr/bin/env python3
"""Database bootstrap helpers used by the Heroku release phase.

Two things have to happen around ``odoo-bin -i`` / ``-u`` that Odoo itself
does not do for us on a platform with an ephemeral filesystem:

``is-initialized``
    Tell the release script whether the Heroku Postgres database already
    holds an Odoo schema. Heroku creates an empty database for us, so
    "database exists" is not the same as "Odoo is installed".

``sync-parameters``
    Force attachments into the database and pin ``web.base.url``. A dyno
    loses its filesystem on every restart, so anything written to the
    filestore would silently disappear.

Both talk to Postgres directly instead of booting a registry: the release
dyno is small and short-lived, and this keeps it that way.
"""

import os
import sys

import psycopg2

from render_config import ConfigError, parse_database_url

INITIALIZED_QUERY = """
    SELECT 1
      FROM information_schema.tables
     WHERE table_schema = 'public'
       AND table_name = 'ir_module_module'
"""

UPSERT_PARAMETER = """
    INSERT INTO ir_config_parameter (key, value, create_date, write_date)
         VALUES (%s, %s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
    ON CONFLICT (key)
  DO UPDATE SET value = EXCLUDED.value,
                write_date = now() AT TIME ZONE 'UTC'
"""


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ConfigError("DATABASE_URL is not set")
    params = parse_database_url(url)
    return psycopg2.connect(
        host=params["db_host"],
        port=params["db_port"],
        user=params["db_user"],
        password=params["db_password"],
        dbname=params["db_name"],
        sslmode=os.environ.get("ODOO_DB_SSLMODE", "require"),
        connect_timeout=30,
    )


def base_url():
    """The public URL of the app, as far as the environment knows it."""
    explicit = os.environ.get("ODOO_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    domain = os.environ.get("HEROKU_APP_DEFAULT_DOMAIN_NAME")
    if domain:
        return "https://%s" % domain
    app = os.environ.get("HEROKU_APP_NAME")
    if app:
        return "https://%s.herokuapp.com" % app
    return None


def wanted_parameters():
    params = {
        # The filestore lives on the dyno's ephemeral disk and is wiped on
        # every restart, so attachments have to go to Postgres instead.
        "ir_attachment.location": os.environ.get("ODOO_ATTACHMENT_LOCATION", "db"),
    }
    url = base_url()
    if url:
        # Without this, Odoo records the URL of whichever request happens to
        # come first, which behind the router is not always the public one.
        params["web.base.url"] = url
        params["web.base.url.freeze"] = "True"
    return params


def cmd_is_initialized():
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(INITIALIZED_QUERY)
        return 0 if cursor.fetchone() else 1


def cmd_sync_parameters():
    params = wanted_parameters()
    with connect() as conn, conn.cursor() as cursor:
        for key, value in sorted(params.items()):
            cursor.execute(UPSERT_PARAMETER, (key, value))
            sys.stderr.write("odoo: set %s = %s\n" % (key, value))
        conn.commit()
    return 0


COMMANDS = {
    "is-initialized": cmd_is_initialized,
    "sync-parameters": cmd_sync_parameters,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        sys.stderr.write("usage: bootstrap.py {%s}\n" % "|".join(sorted(COMMANDS)))
        return 2
    try:
        return COMMANDS[argv[1]]()
    except ConfigError as exc:
        sys.stderr.write("odoo: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
