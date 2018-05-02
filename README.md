# existance

A management tool for eXist-db instances on modern Linux hosts.


## Features

* TODO


## Configuration

A configuration file that defines common properties of all installations es
expected either at `/etc/existance.ini` or as `.existance.ini` in your home
directory where the latter takes precedence. It must contain definitions for
all keys that are presented in this sample:


```ini
[existance]

installer_cache = /var/lib/cache/existance

[exist-db]

user = existdb
group = telota

base_directory = /opt
instance_dir_pattern = exist_{instance_name}_{instance_id}
instances_settings = %(base_directory)s/exist_instances_settings.csv

log_directory = /var/logs/existdb

XmX_default = 1024m

unwanted_jetty_configs = jetty-ssl.xml,jetty-ssl-context.xml,jetty-https.xml
```


## Usage

### install

### uninstall

### upgrade

### systemd-service-template
