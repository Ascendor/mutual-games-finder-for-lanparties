FROM mirror.gcr.io/library/node:24.21.0-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN mkdir -p public/legal
COPY LICENSE THIRD_PARTY_NOTICES.md public/legal/
COPY LICENSES public/legal/licenses/
RUN npm ls --depth=0 && npm run build

FROM mirror.gcr.io/library/nginx:1.30.5-alpine
LABEL org.opencontainers.image.source="https://github.com/Ascendor/mutual-games-finder-for-lanparties"
LABEL org.opencontainers.image.licenses="MIT"
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY LICENSE THIRD_PARTY_NOTICES.md /licenses/
COPY LICENSES /licenses/
EXPOSE 80
