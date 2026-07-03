FROM mirror.gcr.io/library/node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN mkdir -p public/legal
COPY LICENSE THIRD_PARTY_NOTICES.md public/legal/
COPY LICENSES public/legal/licenses/
RUN npm run build

FROM mirror.gcr.io/library/nginx:1.27-alpine
LABEL org.opencontainers.image.source="https://codeberg.org/Ascendor/ref_ju_geeks-play-together"
LABEL org.opencontainers.image.licenses="MIT"
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY LICENSE THIRD_PARTY_NOTICES.md /licenses/
COPY LICENSES /licenses/
EXPOSE 80
