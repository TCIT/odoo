# Odoo 19.0 image, built for a Heroku container-stack dyno.
#
# Python 3.11 on Debian 12 is one of the two reference platforms behind the
# version pins in requirements.txt (the other being Ubuntu 24.04), and it is
# the last Debian release with an official wkhtmltopdf package.

##############################################################################
# Builder: compile the Python dependencies into a self-contained virtualenv.
##############################################################################
FROM python:3.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# psycopg2 and python-ldap have no wheels for these pins and are built here;
# the toolchain is left behind in this stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libjpeg62-turbo-dev \
        libldap2-dev \
        libpq-dev \
        libsasl2-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install --requirement /tmp/requirements.txt

##############################################################################
# Runtime.
##############################################################################
FROM python:3.11-slim-bookworm

ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ARG WKHTMLTOPDF_SHA256=98ba0d157b50d36f23bd0dedf4c0aa28c7b0c50fcdcdc54aa5b6bbba81a3941d

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    ODOO_APP_ROOT=/app \
    ODOO_CONFIG_FILE=/tmp/odoo.conf \
    ODOO_DATA_DIR=/tmp/odoo-data

# wkhtmltopdf renders every PDF report; apt pulls in its X and font
# dependencies from the local .deb.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        fonts-liberation \
        libldap-2.5-0 \
        libmagic1 \
        libpq5 \
        libsasl2-2 \
        libxml2 \
        libxslt1.1 \
    && curl -sSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_amd64.deb" \
    && echo "${WKHTMLTOPDF_SHA256}  /tmp/wkhtmltox.deb" | sha256sum --check --strict \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -f /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* \
    && wkhtmltopdf --version

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . /app

# Heroku runs the container as a non-root user, so nothing may need to be
# written inside the image: the configuration file, the session store and the
# (unused) filestore all live under /tmp.
RUN useradd --create-home --uid 1000 odoo \
    && chown -R odoo:odoo /app
USER odoo

EXPOSE 8069

CMD ["/app/deploy/heroku/entrypoint.sh"]
