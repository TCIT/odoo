# Running this Odoo on Heroku

This directory contains everything needed to run the Odoo 19.0 source in
this repository as a Heroku app, plus a `docker-compose.yml` at the root
that runs the exact same image locally.

```
heroku.yml                  Heroku container-stack manifest
app.json                    Deploy-button / review-app definition
deploy/Dockerfile           The image (Python 3.11, Debian 12, wkhtmltopdf)
deploy/heroku/render_config.py   DATABASE_URL + PORT  ->  odoo.conf
deploy/heroku/bootstrap.py       first-run detection, system parameters
deploy/heroku/release.sh         release phase: install or update modules
deploy/heroku/entrypoint.sh      web process
custom-addons/              your own modules (added to addons_path if present)
```

**Read [Heroku is a tight fit for Odoo](#heroku-is-a-tight-fit-for-odoo)
before committing to this for production.** The setup works and is honest
about what it does, but the platform imposes real limits on Odoo.

## Deploy

You need the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
and a verified account (the Postgres add-on requires a payment method).

```bash
heroku create my-odoo --stack=container
heroku addons:create heroku-postgresql:essential-0 --app my-odoo

# Master password for the database manager. Do not skip this: the app
# refuses to boot without it rather than fall back to Odoo's "admin".
heroku config:set --app my-odoo ODOO_ADMIN_PASSWD="$(openssl rand -base64 32)"

# Modules installed on the first release. Chilean localisation, for example:
heroku config:set --app my-odoo ODOO_INIT_MODULES="base,l10n_cl,sale_management"

# Odoo needs more than the 512 MB of an eco/basic dyno.
heroku ps:type web=standard-2x --app my-odoo

git push heroku claude/wonderful-einstein-a1u1dm:main
```

The first push builds the image, runs the release phase (which installs
Odoo into the empty database, a few minutes), and then starts the web dyno.
`heroku open --app my-odoo` lands on the login page; the initial credentials
are `admin` / `admin`, which you should change immediately.

If you prefer the one-click path, `app.json` supports the Heroku deploy
button and review apps; it provisions the same add-on and dyno size.

## Configuration

Everything is driven by environment variables and turned into an
`odoo.conf` at boot by `render_config.py`. Nothing is baked into the image.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | *(set by the add-on)* | Parsed into `db_host`, `db_port`, `db_user`, `db_password`, `db_name` |
| `PORT` | *(set by Heroku)* | `http_port`; `http_interface` is always `0.0.0.0` |
| `ODOO_ADMIN_PASSWD` | **required** | Master password. Boot fails if unset |
| `ODOO_INIT_MODULES` | `base` | Installed on the first release only |
| `ODOO_UPDATE_MODULES` | *(empty)* | Updated on every later release. Empty means "skip" |
| `ODOO_WORKERS` | `0` | Must stay `0`, see below |
| `ODOO_MAX_CRON_THREADS` | `1` | Scheduled-action threads |
| `ODOO_DB_MAXCONN` | `5` | Keep below the add-on's connection limit (20 on essential tiers) |
| `ODOO_DB_SSLMODE` | `require` | Heroku Postgres refuses plaintext |
| `ODOO_LIST_DB` | `False` | Exposes the database manager when `True` |
| `ODOO_WITHOUT_DEMO` | `True` | Set `False` to install demo data |
| `ODOO_BASE_URL` | derived | `web.base.url`; falls back to `HEROKU_APP_NAME` |
| `ODOO_ATTACHMENT_LOCATION` | `db` | Where attachments live, see below |
| `ODOO_EXTRA_ADDONS_PATH` | `custom-addons` | Comma-separated, relative to `/app`; an entry is only added once it holds a module |
| `ODOO_DATA_DIR` | `/tmp/odoo-data` | Sessions and filestore |
| `ODOO_LOG_LEVEL` | `info` | Odoo log level |
| `ODOO_LIMIT_TIME_REAL` | `120` | Per-request wall-clock limit |
| `ODOO_CONFIG_EXTRA` | *(empty)* | Raw `key = value` lines appended to `odoo.conf` |

## The release phase

`release.sh` runs once per deploy, before the new dyno takes traffic, and a
non-zero exit rolls the release back.

* **Empty database** (no `ir_module_module` table): installs
  `ODOO_INIT_MODULES`. Heroku hands you a database that exists but is
  empty, which is not the same as an Odoo installation.
* **Existing database**: updates `ODOO_UPDATE_MODULES`, or does nothing when
  that variable is empty. Running `-u all` on every deploy is slow and
  rewrites data, so it is deliberately an opt-in.

Afterwards it writes two system parameters straight to Postgres:
`ir_attachment.location = db` and a frozen `web.base.url`.

That parameter cannot be set any earlier -- `ir_config_parameter` does not
exist until `base` is installed -- so the first installation always writes a
few hundred attachments to the filestore first. The release phase therefore
finishes by calling `ir.attachment.force_storage()` to move them into
Postgres, and only when something is actually left on disk. Skipping this
would cost you every module icon and image on the first dyno restart.

### Installing more apps later

```bash
heroku run --size=standard-2x --app my-odoo bash
# inside the one-off dyno:
python3 deploy/heroku/render_config.py
./odoo-bin --config /tmp/odoo.conf --init l10n_cl --stop-after-init
```

Installing apps from Odoo's own Apps screen usually exceeds Heroku's 30
second router timeout and dies with an `H12`, even though the installation
keeps running server-side. Use the command above instead.

### Upgrading the Odoo series later

Bring in the new upstream branch, then let the release phase migrate:

```bash
git remote add upstream https://github.com/odoo/odoo    # once
git fetch upstream 20.0
# review, merge into your branch, then:
heroku config:set --app my-odoo ODOO_UPDATE_MODULES=all
git push heroku <branch>:main
heroku config:set --app my-odoo ODOO_UPDATE_MODULES=""   # back to opt-in
```

Odoo's own `-u all` only migrates data between *minor* revisions of the same
series. Jumping between major series (18.0 -> 19.0, 19.0 -> 20.0) needs
[Odoo's upgrade service](https://upgrade.odoo.com) for the database; the
code side is the merge above.

## Local development

```bash
docker compose up --build
```

Same image, same entrypoint, same `DATABASE_URL` contract, with demo data
on and TLS off. Odoo is on <http://localhost:8069>, and `./custom-addons` is
mounted into the container so your own modules are picked up (the
directory is left out of `addons_path` until it actually holds a module, so
an empty one is not an error). Restart the `odoo` service after adding a
module directory, then install it with:

```bash
docker compose exec odoo ./odoo-bin --config /tmp/odoo.conf \
    --init your_module --stop-after-init
```

## Heroku is a tight fit for Odoo

Odoo is a stateful, multi-process, filesystem-backed application; a dyno is
none of those things. The configuration here works around each mismatch, but
the workarounds have consequences worth knowing before you rely on them.

**Attachments go into Postgres.** A dyno's disk is wiped on every restart,
so `ir_attachment.location` is set to `db`. Everything Odoo would normally
put in the filestore — invoice PDFs, product images, compiled asset bundles
— becomes rows in Postgres. It is correct and it survives restarts, but the
database grows much faster than usual and `essential-0` only holds 1 GB.
Watch `heroku pg:info` and size up early.

**Sessions do not survive a restart.** Odoo keeps its session store on
disk and has no shared-store option in core. Heroku cycles dynos at least
daily, and every deploy replaces them, so users are logged out each time.

**One dyno only, and it is single-process.** In multiprocess mode Odoo
serves websockets from a *second* port (`gevent_port`), and a dyno exposes
exactly one. So `workers = 0`: one Python process serving requests with
threads. That also rules out scaling `web` past one dyno, because the
router has no sticky sessions and the session store is local. Expect this
to be comfortable for a handful of concurrent users, not for a busy
company.

**Memory.** `standard-2x` (1 GB) is the realistic floor once a few apps are
installed. Smaller dynos will hit `R14` swapping and crawl.

**Long requests.** The router cuts a response off after 30 seconds. Report
generation, imports and module installs can all exceed that; run them from
a one-off dyno.

If those trade-offs do not work for you, the same `deploy/Dockerfile` runs
unchanged on anything that gives you a persistent volume and more than one
port — a small VM with the `docker-compose.yml` here, or Fly.io with a
volume. [Odoo.sh](https://www.odoo.com/odoo-sh) is the managed option, and
it handles the database upgrades between series for you.

## Troubleshooting

**`odoo: ODOO_ADMIN_PASSWD is not set`** — the app refuses to boot without a
master password. Set it as shown above.

**Release phase fails on `FATAL: too many connections`** — lower
`ODOO_DB_MAXCONN`, or check for one-off dynos still holding connections
(`heroku pg:killall`).

**`H12 Request timeout` on first load** — the first request after a deploy
compiles the asset bundles, which can take longer than 30 seconds. Reload;
the bundles are cached in the database from then on.

**`H10 App crashed` right after deploy** — `heroku logs --tail`. The most
common causes are a missing `ODOO_ADMIN_PASSWD` and an `ODOO_INIT_MODULES`
entry that does not exist in `addons_path`.

**PDF reports come out blank** — check `wkhtmltopdf --version` inside
`heroku run bash`; the image pins 0.12.6.1-3, the build Odoo expects.
