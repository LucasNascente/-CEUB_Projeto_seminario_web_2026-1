#!/bin/sh
set -eu

port="${PORT:-10000}"
case "$port" in
  ''|*[!0-9]*) echo "PORT inválida" >&2; exit 1 ;;
esac

sed -e "s/listen 80;/listen ${port};/" \
    -e '/resolver 127.0.0.11/d' \
    -e 's|http://gateway:8000|http://127.0.0.1:8000|' \
    -e 's/proxy_read_timeout 25s;/proxy_read_timeout 160s;/' \
    /app/frontend.conf > /etc/nginx/conf.d/helpdesk.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 155 app:app &
gateway_pid=$!
nginx -g 'daemon off;' &
nginx_pid=$!

stop() {
  kill -TERM "$gateway_pid" "$nginx_pid" 2>/dev/null || true
  wait "$gateway_pid" "$nginx_pid" 2>/dev/null || true
}
trap 'stop; exit 0' INT TERM
while kill -0 "$gateway_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
  sleep 1
done
stop
exit 1
