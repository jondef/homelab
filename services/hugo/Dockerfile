ARG ENVIRONMENT=production

# For deevelopment in Pycharm:
# Bind ports: 1313:1313
# Environment variables: ENVIRONMENT=development


FROM alpine:3.19 as build
RUN apk add --no-cache hugo
COPY . /src
WORKDIR /src

# Conditional build steps
RUN if [ "$ENVIRONMENT" = "production" ]; then \
        echo "Running in production mode"; \
        hugo; \
    else \
        echo "Running in development mode"; \
    fi

# In development mode, run Hugo server. In production, no CMD is needed
CMD if [ "$ENVIRONMENT" = "development" ]; then \
        hugo server --bind 0.0.0.0 --disableFastRender; \
    fi

EXPOSE 1313