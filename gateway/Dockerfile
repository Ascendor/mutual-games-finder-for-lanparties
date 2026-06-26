FROM mirror.gcr.io/library/nginx:1.27

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.d/40-lan-party-auth-and-tls.sh
RUN chmod +x /docker-entrypoint.d/40-lan-party-auth-and-tls.sh

EXPOSE 80 443
