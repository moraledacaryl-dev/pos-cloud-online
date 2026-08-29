FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

ARG NEXT_PUBLIC_API_BASE=/api
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

COPY . .
RUN npm run build \
    && npm prune --omit=dev

FROM node:24-alpine

ENV NODE_ENV=production \
    PORT=3100

WORKDIR /app

COPY --from=build /app ./

EXPOSE 3100

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3100"]
