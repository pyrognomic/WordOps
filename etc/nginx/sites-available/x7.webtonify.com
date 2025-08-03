
server {


    server_name x7.webtonify.com www.x7.webtonify.com;


    access_log /var/log/nginx/x7.webtonify.com.access.log rt_cache;
    error_log /var/log/nginx/x7.webtonify.com.error.log;

    # acl start
    include /etc/nginx/acls/secure-x7.webtonify.com.conf;

    # acl end



    root /var/www/x7.webtonify.com/htdocs;


    index index.php index.html index.htm;


    include common/php84.conf;
    
    include common/wpcommon-php84.conf;
    include common/locations-wo.conf;
    include /var/www/x7.webtonify.com/conf/nginx/*.conf;

}
