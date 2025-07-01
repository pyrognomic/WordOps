upstream php${PHPVER_STRIPPED}-${SLUG} {
    least_conn;

    server unix:${PHP_POOL_SOCK};
    keepalive 5;
}
