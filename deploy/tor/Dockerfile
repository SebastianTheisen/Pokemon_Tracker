# Optionaler Tor-Proxy (nur Test, Profil „tor“): SOCKS-Port ausschließlich auf localhost des VPS.
FROM alpine:3.20
RUN apk add --no-cache tor \
    && adduser -D -u 1000 toruser
COPY torrc /etc/tor/torrc
USER toruser
CMD ["tor", "-f", "/etc/tor/torrc"]
