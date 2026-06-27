#!/bin/sh
set -eu

: "${BASIC_AUTH_USER:=lanparty}"
: "${BASIC_AUTH_PASSWORD:=QC4lF93bYgwTHRT4xRynsAIz3San1lDW}"
: "${LAN_UPLOAD_LIMIT:=2g}"

mkdir -p /etc/nginx/auth /etc/nginx/certs

if command -v openssl >/dev/null 2>&1; then
  PASSWORD_HASH="$(openssl passwd -apr1 "$BASIC_AUTH_PASSWORD")"
else
  PASSWORD_HASH="{PLAIN}$BASIC_AUTH_PASSWORD"
fi
printf "%s:%s\n" "$BASIC_AUTH_USER" "$PASSWORD_HASH" > /etc/nginx/auth/.htpasswd
chmod 644 /etc/nginx/auth/.htpasswd

if [ ! -f /etc/nginx/certs/lan-party.crt ] || [ ! -f /etc/nginx/certs/lan-party.key ]; then
  openssl req \
    -x509 \
    -nodes \
    -newkey rsa:2048 \
    -days 3650 \
    -keyout /etc/nginx/certs/lan-party.key \
    -out /etc/nginx/certs/lan-party.crt \
    -subj "/CN=lan-party-game-finder"
fi
