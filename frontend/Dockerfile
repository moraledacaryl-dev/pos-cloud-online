FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

ARG NEXT_PUBLIC_API_BASE=/api
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

COPY . .
RUN npm run build \
    && npm prune --omit=dev

FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf

ENV NODE_ENV=production \
    PORT=3100

WORKDIR /app

COPY --from=build /app ./

EXPOSE 3100

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3100"]
