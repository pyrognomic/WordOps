location / {
  try_files $uri $uri/ /index.php$is_args$args;
}
location ~ \.php$ {
  try_files $uri =404;
  include fastcgi_params;
  fastcgi_pass php${PHPVER_STRIPPED}-${SLUG};
}
