[Unit]
Description=PHP ${PHPVER} FPM pool for %i
After=network.target

[Service]
Type=notify
# Load the pool-specific config, not the global one
ExecStart=/usr/sbin/php-fpm${PHPVER} \
--nodaemonize \
--fpm-config /etc/php/${PHPVER}/fpm/php-fpm-%i.conf
ExecStartPost=-/usr/lib/php/php-fpm-socket-helper install \
/run/php/php${PHPVER}-fpm-%i.sock \
/etc/php/${PHPVER}/fpm/pool.d/%i.conf 84
ExecStopPost=-/usr/lib/php/php-fpm-socket-helper remove \
/run/php/php${PHPVER}-fpm-%i.sock \
/etc/php/${PHPVER}/fpm/pool.d/%i.conf 84

ExecReload=/bin/kill -USR2 $MAINPID
Restart=on-failure

PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
