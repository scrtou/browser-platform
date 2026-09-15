FROM alpine:3.23@sha256:fd791d74b68913cbb027c6546007b3f0d3bc45125f797758156952bc2d6daf40 AS trust

RUN test -s /etc/ssl/certs/ca-certificates.crt

FROM scratch
LABEL io.browser-platform.secret-lease="1"

COPY build/profile-relay /profile-relay
COPY --from=trust /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
LABEL io.browser-platform.proxy-upstreams="1"

USER 1000:1000
ENTRYPOINT ["/profile-relay"]
CMD ["-config", "/run/config/relay.json"]
