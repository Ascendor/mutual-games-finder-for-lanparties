FROM mirror.gcr.io/library/node:20-alpine

LABEL org.opencontainers.image.source="https://codeberg.org/Ascendor/ref_ju_geeks-play-together"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY steam-helper/package.json steam-helper/package-lock.json ./
RUN npm ci --omit=dev
COPY steam-helper/server.js ./
COPY LICENSE THIRD_PARTY_NOTICES.md /licenses/
COPY LICENSES /licenses/

EXPOSE 3000
CMD ["npm", "start"]
