FROM alpine:3.19 as build
RUN apk add --no-cache hugo
COPY . /src
WORKDIR /src
RUN hugo

