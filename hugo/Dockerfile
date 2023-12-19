FROM --platform=$BUILDPLATFORM alpine:3.19 as build
RUN apk add --no-cache hugo
COPY . /src
WORKDIR /src
RUN --mount=type=cache,target=/tmp/hugo_cache hugo
EXPOSE 80

