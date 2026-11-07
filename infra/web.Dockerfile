# LunaGo website + ComplaintLens console (Next.js). Production deploys use Vercel; this image is for
# running the whole system locally with docker compose (the defence fallback).
FROM node:24-slim AS build
RUN corepack enable
WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
# Inlined into the browser bundle at build time.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm build

FROM node:24-slim
RUN corepack enable
WORKDIR /web
COPY --from=build /web ./
ENV NODE_ENV=production
EXPOSE 3000
CMD ["pnpm", "start", "--port", "3000"]
