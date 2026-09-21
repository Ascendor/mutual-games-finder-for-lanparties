FROM mirror.gcr.io/library/nginx:1.27

LABEL org.opencontainers.image.source="https://github.com/Ascendor/mutual-games-finder-for-lanparties"
LABEL org.opencontainers.image.licenses="MIT"

COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
RUN mkdir -p /etc/nginx/templates && mv /etc/nginx/conf.d/default.conf /etc/nginx/templates/default.conf.template
COPY gateway/docker-entrypoint.sh /docker-entrypoint.d/40-lan-party-auth-and-tls.sh
RUN chmod +x /docker-entrypoint.d/40-lan-party-auth-and-tls.sh
COPY LICENSE THIRD_PARTY_NOTICES.md /licenses/
COPY LICENSES /licenses/

EXPOSE 80 443
