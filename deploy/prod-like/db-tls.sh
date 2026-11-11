#!/bin/sh
# Entrypoint of the prod-like database (ADR-0037, guardrail-tls-certificates): turns TLS on with the certificate for the
# host name `db` that deploy/prod-like/certs.sh signed with the private CA, then hands over to the image's own entrypoint.
# PostgreSQL refuses a key file that is not owned by its user or is readable by others, and a bind-mounted file keeps the
# owner of the host, so the key is copied to a private directory first. Without certificates (dev, test) the database
# starts as before, without TLS.
set -eu

certs=/certs
tls=/tmp/db-tls

if [ -f "$certs/db.crt" ] && [ -f "$certs/db.key" ]; then
  mkdir -p "$tls"
  cp "$certs/db.crt" "$tls/server.crt"
  cp "$certs/db.key" "$tls/server.key"
  chown postgres "$tls" "$tls/server.crt" "$tls/server.key"
  chmod 0700 "$tls"
  chmod 0600 "$tls/server.key"
  set -- "$@" -c ssl=on -c "ssl_cert_file=$tls/server.crt" -c "ssl_key_file=$tls/server.key" \
    -c ssl_min_protocol_version=TLSv1.2 -c hba_file=/etc/postgresql-tls/pg_hba.conf
fi

exec docker-entrypoint.sh "$@"
