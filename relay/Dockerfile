FROM scratch

COPY build/profile-relay /profile-relay

USER 1000:1000
ENTRYPOINT ["/profile-relay"]
CMD ["-config", "/run/config/relay.json"]
