# LunaGo website + ComplaintLens console (Next.js static export). Production is GitHub Pages; this
# image serves the same static files with nginx for running everything locally (docker compose).
FROM node:24-slim AS build
RUN corepack enable
WORKDIR /repo/apps/web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
# The Help Center pages are generated from company/help_center at build time.
COPY company/help_center /repo/company/help_center
# Inlined into the browser bundle at build time.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /repo/apps/web/out /usr/share/nginx/html
EXPOSE 80
