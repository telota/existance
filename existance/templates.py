EXISTCTL_TEMPLATE = """\
#!/bin/bash

# author: martin.wagner@bbaw.de
# last-updated: 2017-05-16

# This script is intended to control several instances of eXist-db on one host.
# Each instance is identified by the IP port it's supposed to listen on.
# The main motivation stems from the need to handle multiple instances in a
# unified way without repeated setup tasks and scripts that drift eventually
# apart.
# In particular it can be used in a systemd unit template, e.g.:
#     systemctl enable existdb@8000.service

# As a side-effect it provides a single view on the configured maxiumum values
# that a JVM may allocate in $instances_settings.

# This script depends on eXist-db 3.2 or greater,
# otherwise, these patches have to be applied:
# https://github.com/eXist-db/exist/pull/1347

# args:
#   $1: the action to execute; one of `start`, `stop` or `restart`
#   $2: the instance's id to be handled

# environment variables:
#   DEBUG: verbose behaviour if set to 'on'

# Example usages:
#   existctl start 8000
#   DEBUG=on existctl restart 8000
#   existctl stop 8000


set -e

[ "$DEBUG" = "on" ] && set -x
[ "$USER" = "existdb" ] || exec sudo -u existdb DEBUG="${DEBUG:=off}" $0 "${@}"

action=$1
instance_id=$2

instances_root=/opt
instances_settings="${instances_root}/exist_instances_settings.csv"
instance_dir=$(find ${instances_root} -maxdepth 1 -type d -name "exist_*_${instance_id}" -print -quit)
bin_dir="${instance_dir}/existdb/bin"
pid_dir="/tmp/exist_pids"
pid_file="${pid_dir}/${instance_id}.pid"
app_port=$instance_id

export EXIST_HOME="${instance_dir}/existdb"

[ -d $pid_dir ] || mkdir $pid_dir

get_settings () {
    local line
    line=$(egrep -v "^#" $instances_settings | egrep "^${instance_id},")
    xmx=$(echo $line | cut -d "," -f 3 | tr -d "[:space:]")
}

start () {
    if [ -f $pid_file ] && [ -e "/proc/$(cat $pid_file)" ]; then
        echo "Instance ${instance_id} seems to be running."
        exit 1
    fi
    rm -f $pid_file

    get_settings

    export JAVA_HOME=$(readlink -f "$(which java)" | rev  | cut -d/ -f 3- | rev )
    export JAVA_OPTIONS="-Xms128m -Xmx${xmx} -Dfile.encoding=UTF-8 -Djetty.port=${app_port}"
    ( ${bin_dir}/startup.sh --forking --pidfile ${pid_file} & ) </dev/null &>/dev/null
    while [ ! -f ${pid_file} ]; do sleep 0.2; done
}

purge_runtime_files () {
    rm -f $pid_file
    find $EXIST_HOME -name "*.l?ck" -type f -delete
}

stop () {
    local pid
    local timeout

    if [ ! -f $pid_file ]; then
        echo "${pid_file} not found."
        exit 1
    fi

    pid=$(cat $pid_file)

    if [ ! -e /proc/$pid ]; then
        echo "Process ${pid} is not running."
        purge_runtime_files
        exit 1
    fi

    kill -SIGTERM $pid

    timeout=30
    while [ $timeout -gt 0 ] && [ -e /proc/$pid ]; do
        sleep 1
        timeout=$(($timeout - 1))
    done

    if [ -e /proc/$pid ]; then
        kill -SIGKILL $pid
    fi

    if [ -e /proc/$pid ]; then
        echo "eXist-db instance ${instance_id} did not stop properly."
        exit 1
    fi

    purge_runtime_files
}

case $action in
  "start") start ;;
  "stop") stop ;;
  "restart") stop ; start ;;
  *) echo "Invalid action: $action"; exit 1 ;;
esac
"""

NGINX_SITE_TEMPLATE = """\
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name <hostname>;

    ssl_certificate /etc/ssl/certs/<hostname>.pem;
    ssl_certificate_key /etc/ssl/private/<hostname>.key;

    include /etc/nginx/proxy-mappings/*;
}
"""


SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=eXist-db instance; id: %i
After=network.target
AssertPathExistsGlob=/opt/exist_*_%i

[Service]
Type=forking
ExecStart=/usr/local/bin/existctl start %i
ExecStop=/usr/local/bin/existctl stop %i
ExecReload=/usr/local/bin/existctl restart %i
User=existdb
PIDFile=/tmp/exist_pids/%i.pid
Restart=always

[Install]
WantedBy=multi-user.target
"""


TEMPLATES = {
    'existctl': EXISTCTL_TEMPLATE,
    'nginx-site': NGINX_SITE_TEMPLATE,
    'systemd-unit': SYSTEMD_UNIT_TEMPLATE,
}
