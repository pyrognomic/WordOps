[global]
pid = ${PHP_MASTER_PID}
error_log = ${PHP_MASTER_LOG_FILE}
log_level = notice
emergency_restart_threshold = 10
emergency_restart_interval = 1m
process_control_timeout = 10s
include = ${PHP_POOL_CONF_FILE}
