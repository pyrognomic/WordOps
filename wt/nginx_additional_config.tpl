# Limit access to avoid brute force attack
location = /wp-login.php {
    limit_req zone=one burst=1 nodelay;
    include fastcgi_params;
    fastcgi_pass php${PHPVER_STRIPPED}-${SLUG};
}
# Prevent DoS attacks on wp-cron
location = /wp-cron.php {
    limit_req zone=two burst=1 nodelay;
    include fastcgi_params;
    fastcgi_pass php${PHPVER_STRIPPED}-${SLUG};
}
# Prevent DoS attacks with xmlrpc.php
location = /xmlrpc.php {
    # Whitelist Jetpack IP ranges, Allow all Communications Between Jetpack and WordPress.com
    allow 122.248.245.244/32;
    allow 54.217.201.243/32;
    allow 54.232.116.4/32;
    allow 192.0.80.0/20;
    allow 192.0.96.0/20;
    allow 192.0.112.0/20;
    allow 195.234.108.0/22;

    # Deny all other requests
    deny all;

    # Disable access and error logging
    access_log off;
    log_not_found off;

    # Limit the rate of requests to prevent DoS attacks
    limit_req zone=two burst=1 nodelay;

    # Pass the request to PHP-FPM backend
    include fastcgi_params;
    fastcgi_pass php${PHPVER_STRIPPED}-${SLUG};
}
# Disable wp-config.txt
location = /wp-config.txt {
    deny all;
    access_log off;
    log_not_found off;
}
location = /robots.txt {
# Some WordPress plugin gererate robots.txt file
# Refer #340 issue
    try_files $uri $uri/ /index.php?$args @robots;
    access_log off;
    log_not_found off;
}
# fallback for robots.txt with default wordpress rules
location @robots {
    return 200 "User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n";
}
# webp rewrite rules for jpg and png images
# try to load alternative image.png.webp before image.png
location /wp-content/uploads {
    location ~ \.(png|jpe?g)$ {
        add_header Vary "Accept-Encoding";
        more_set_headers 'Access-Control-Allow-Origin : *';
        more_set_headers  "Cache-Control : public, no-transform";
        access_log off;
        log_not_found off;
        expires max;
        try_files $uri$avif_suffix $uri$webp_suffix $uri =404;
    }
    location ~* \.(php|gz|log|zip|tar|rar|xz)$ {
        #Prevent Direct Access Of PHP Files & Backups from Web Browsers
        deny all;
    }
}
# webp rewrite rules for EWWW testing image
location /wp-content/plugins/ewww-image-optimizer/images {
    location ~ \.(png|jpe?g)$ {
        add_header Vary "Accept-Encoding";
        more_set_headers 'Access-Control-Allow-Origin : *';
        more_set_headers  "Cache-Control : public, no-transform";
        access_log off;
        log_not_found off;
        expires max;
        try_files $uri$avif_suffix $uri$webp_suffix $uri =404;
    }
    location ~ \.php$ {
    #Prevent Direct Access Of PHP Files From Web Browsers
        deny all;
    }
}
# enable gzip on static assets - php files are forbidden
location /wp-content/cache {
# Cache css & js files
    location ~* \.(?:css(\.map)?|js(\.map)?|.html)$ {
        more_set_headers 'Access-Control-Allow-Origin : *';
        access_log off;
        log_not_found off;
        expires 1y;
    }
    location ~ \.php$ {
        #Prevent Direct Access Of PHP Files From Web Browsers
        deny all;
    }
}
# Deny access to any files with a .php extension in the uploads directory
# Works in sub-directory installs and also in multisite network
# Keep logging the requests to parse later (or to pass to firewall utilities such as fail2ban)
location ~* /(?:uploads|files)/.*\.php$ {
    deny all;
}
# mitigate DoS attack CVE with WordPress script concatenation
# add the following line to wp-config.php
# define( 'CONCATENATE_SCRIPTS', false );
location ~ \/wp-admin\/load-(scripts|styles).php {
    deny all;
}
# Protect Easy Digital Download files from being accessed directly.
location ~ ^/wp-content/uploads/edd/(.*?)\.zip$ {
    rewrite / permanent;
}
