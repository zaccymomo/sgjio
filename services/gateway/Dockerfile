# The API gateway: routes /api/* to the services and asks Identity who is signed in.
# Built only from this directory: docker build services/gateway
FROM nginx:1.27-alpine

# Defaults for running the image alone; docker-compose.yml sets them too.
ENV IDENTITY_UPSTREAM=identity:8000 \
    CONTENT_UPSTREAM=content:8000 \
    LEARNING_UPSTREAM=learning:8000 \
    MEDIA_MAX_MB=15

RUN rm -f /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/ /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/05-require-gateway-key.sh
COPY snippets/ /etc/nginx/snippets/
# The official image renders /etc/nginx/templates/*.template into /etc/nginx/conf.d/ with
# envsubst at start-up, replacing only variables that are set in the environment.
COPY templates/ /etc/nginx/templates/

EXPOSE 8080
