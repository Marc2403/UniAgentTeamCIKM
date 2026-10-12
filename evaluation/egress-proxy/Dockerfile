# Allowlist proxy: the only egress of the internal network uniagent-internal, admitting openrouter.ai:443 only.
# docker build -t egress-proxy evaluation/egress-proxy
# docker network create --internal uniagent-internal
# docker run -d --name egress-proxy egress-proxy && docker network connect uniagent-internal egress-proxy
# then: HTTPS_PROXY=http://egress-proxy:8888 evaluation/run-mvp.sh <name> <image> <out> uniagent-internal -- ...
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
RUN printf 'Port 8888\nListen 0.0.0.0\nTimeout 600\nAllow 0.0.0.0/0\nFilter "/etc/tinyproxy/allow"\nFilterDefaultDeny Yes\nFilterURLs Off\nConnectPort 443\nLogLevel Connect\n' > /etc/tinyproxy/tinyproxy.conf \
 && printf '^openrouter\.ai$\n' > /etc/tinyproxy/allow
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
