# Loki single binary + a static busybox for the compose healthcheck (the upstream image is distroless: no shell,
# no wget). Build context: smartsched/deploy/observability/loki. Base images by digest from docker-compose.yml.
ARG LOKI_IMAGE=grafana/loki:3.7.8
ARG BUSYBOX_IMAGE=busybox:1.37.0-musl

FROM ${BUSYBOX_IMAGE} AS busybox

FROM ${LOKI_IMAGE}
COPY --from=busybox /bin/busybox /usr/local/bin/busybox
COPY loki.yaml /etc/loki/loki.yaml
USER 10001
EXPOSE 3100
ENTRYPOINT ["/usr/bin/loki"]
CMD ["-config.file=/etc/loki/loki.yaml"]
