server {
    ## HTTP (port 80)
    listen 80 default_server;
    listen [::]:80 default_server;

    ## HTTPS (port 443) – must supply certs for SSL
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;

    ssl_certificate     ${SELFSIGNCERT_ROOT}/default.crt;
    ssl_certificate_key ${SELFSIGNCERT_ROOT}/default.key;

    # no server_name → catches anything not matched elsewhere
    return 444;
}