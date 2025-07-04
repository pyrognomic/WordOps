[${SLUG}]
user = ${PHPFPM_USER}
group = ${PHPFPM_USER}

; socket for this site
listen = ${PHP_POOL_SOCK}
listen.owner = ${PHPFPM_USER}
listen.group = ${PHPFPM_USER}
listen.mode = 0660
listen.backlog = 32768

; process manager
pm = ondemand
pm.max_children = 50
pm.start_servers = 10
pm.min_spare_servers = 5
pm.max_spare_servers = 15
pm.max_requests = 1500
request_terminate_timeout = 300

; logging
catch_workers_output = yes
access.log = ${PHP_POOL_ACCESS_LOG_FILE}
slowlog = ${PHP_POOL_SLOW_LOG_FILE}

; disable functions
php_admin_value[disable_functions] = disable_functions = \
  exec,shell_exec,system,passthru,popen,proc_open,proc_close,proc_terminate,proc_nice,pcntl_exec,dl,\
  link,symlink,highlight_file,show_source,fpassthru,virtual,escapeshellcmd,ini_alter,\
  diskfreespace,tmpfile,getmyuid,posix_ctermid,posix_getcwd,posix_getegid,posix_geteuid,posix_getgid,\
  posix_getgrgid,posix_getgrnam,posix_getgroups,posix_getlogin,posix_getpgid,posix_getpgrp,\
  posix_getpid,posix_getppid,posix_getpwuid,posix_getrlimit,posix_getsid,posix_getuid,\
  posix_isatty,posix_kill,posix_mkfifo,posix_setegid,posix_seteuid,posix_setgid,posix_setpgid,\
  posix_setsid,posix_setuid,posix_times,posix_ttyname,posix_uname,\
  socket_accept,socket_bind,socket_clear_error,socket_close,socket_connect,\
  socket_listen,socket_create_listen,socket_create_pair,socket_read,stream_socket_server

; restrict filesystem
php_admin_value[open_basedir] = "${WEBROOT}:/usr/share/php/:/tmp/:/var/run/nginx-cache/:/dev/urandom:/dev/shm:/var/lib/php/sessions/"
