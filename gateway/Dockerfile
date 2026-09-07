FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /arena-gateway ./cmd/arena-gateway

FROM alpine:3.22
RUN adduser -D -u 10002 arena
COPY --from=build /arena-gateway /usr/local/bin/arena-gateway
USER arena
EXPOSE 8081
ENTRYPOINT ["arena-gateway"]
