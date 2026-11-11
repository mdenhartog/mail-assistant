#!/usr/bin/env bash
# Creates the private CA, the edge certificate and the database certificate for the prod-like stack (ADR-0037, guardrail-tls-certificates).
# Output goes to deploy/prod-like/certs/ (git-ignored): ca.crt (trust this one), server.crt, server.key (edge),
# db.crt, db.key (PostgreSQL, host name `db`, served through db-tls.sh).
# Usage: deploy/prod-like/certs.sh [output-dir]
# The CA key never leaves this script: it is deleted after the leaf is signed. Everything expires after 30 days.
set -euo pipefail

host="mail-assistant.localhost"
out="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/certs}"
days=30

mkdir -p "$out"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

openssl ecparam -name prime256v1 -genkey -noout -out "$work/ca.key"
openssl req -x509 -new -key "$work/ca.key" -sha256 -days "$days" -subj "/CN=mail-assistant prod-like CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out "$out/ca.crt"

openssl ecparam -name prime256v1 -genkey -noout -out "$out/server.key"
openssl req -new -key "$out/server.key" -subj "/CN=$host" -out "$work/server.csr"
printf 'subjectAltName=DNS:%s\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n' \
  "$host" > "$work/server.ext"
openssl x509 -req -in "$work/server.csr" -CA "$out/ca.crt" -CAkey "$work/ca.key" -CAcreateserial \
  -days "$days" -sha256 -extfile "$work/server.ext" -out "$out/server.crt"

# The database leaf: the same CA, the one name the api connects to (verify-full), server auth only.
openssl ecparam -name prime256v1 -genkey -noout -out "$out/db.key"
openssl req -new -key "$out/db.key" -subj "/CN=db" -out "$work/db.csr"
printf 'subjectAltName=DNS:db\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n' \
  > "$work/db.ext"
openssl x509 -req -in "$work/db.csr" -CA "$out/ca.crt" -CAkey "$work/ca.key" -CAcreateserial \
  -days "$days" -sha256 -extfile "$work/db.ext" -out "$out/db.crt"

# The edge runs as a non-root user without capabilities, so it needs read access; the files are throwaway and local.
chmod 0644 "$out/ca.crt" "$out/server.crt" "$out/server.key" "$out/db.crt" "$out/db.key"
echo "wrote $out/ca.crt, $out/server.crt, $out/server.key for $host and $out/db.crt, $out/db.key for db"
