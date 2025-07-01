server {
    server_name ${DOMAIN} www.${DOMAIN};

    access_log /var/log/nginx/${DOMAIN}.access.log rt_cache;
    error_log /var/log/nginx/${DOMAIN}.error.log;

    root ${HTDOCS};

    index index.php index.html index.htm;

    include common/php${PHPVER_STRIPPED}-${SLUG}.conf;

    include common/wpcommon-php${PHPVER_STRIPPED}-${SLUG}.conf;
    include common/locations-wo.conf;
    include ${WEBROOT}/conf/nginx/*.conf;
}
