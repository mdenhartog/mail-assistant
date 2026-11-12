#!/usr/bin/env bash
# Signs the certificate of the prod-like mail catcher (ADR-0037, guardrail-tls-certificates): host name `mail`, server
# auth only, from the private CA that certs.sh made. certs.sh calls it while the CA key still exists.
# Usage: deploy/prod-like/mail-tls.sh <ca.crt> <ca.key> <output-dir>   (writes mail.crt and mail.key there)
set -euo pipefail

ca_cert="${1:?ca certificate}"
ca_key="${2:?ca key}"
out="${3:?output directory}"
days=30

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

openssl ecparam -name prime256v1 -genkey -noout -out "$out/mail.key"
openssl req -new -key "$out/mail.key" -subj "/CN=mail" -out "$work/mail.csr"
printf 'subjectAltName=DNS:mail\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n' \
  > "$work/mail.ext"
openssl x509 -req -in "$work/mail.csr" -CA "$ca_cert" -CAkey "$ca_key" -CAcreateserial \
  -days "$days" -sha256 -extfile "$work/mail.ext" -out "$out/mail.crt"
