# display http version used in header (optional)
more_set_headers "X-protocol : $server_protocol always";

# Advertise HTTP/3 QUIC support (required)
more_set_headers 'Alt-Svc h3=":$server_port"; ma=86400';

# enable [QUIC address validation](https://datatracker.ietf.org/doc/html/rfc9000#name-address-validation)
quic_retry on;

# Listen on port 443 with HTTP/3 QUIC
listen 443 quic reuseport;
listen [::]:443 quic reuseport;

# listen on port 443 with HTTP/2
listen 443 ssl;
listen [::]:443 ssl;
ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
ssl_certificate_key     /etc/letsencrypt/live/${DOMAIN}/key.pem;
ssl_trusted_certificate /etc/letsencrypt/live/${DOMAIN}/ca.pem;
ssl_stapling_verify on;
