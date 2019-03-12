# existance

A management tool for [eXist-db] instances on modern Linux hosts.


## Features

* Install, uninstall and upgrade eXist-db instances with a uniform CLI tool.
* Integrates eXist-db instances with [systemd].
  - Ensures that enabled instances are started and stopped with the operating
    system.
  - Monitors instances and restarts crashed ones.
  - Doesn't require a compatibility layer for what you otherwise probably
    hacked together for SysV init ‒ 80's authenticism is such a misery.
  - Opens the opportunity to leverage `systemd`'s capabilities like resource
    constraints.
* Sets up configuration for proxying the instances with [nginx].
  - Access eXist-db web interfaces by their name mapped to a path.
  - One TLS-handling service per system is enough.
  - The cool kids serve applications' static assets with it.
* Defines periodic backup tasks for each instance.
* Aggregates log files in a canonical location for which log rotation can
  easily be configured.
* Enjoy the nostalgic feeling when using CLI dialogues.
  Yes, 90's authenticism is disgusting.


## Requirements

The tool requires a Python 3.6 (or newer) interpreter and the notorious
[requests] package installed. The latter is installed as dependency.

The aforementioned service manager and web server must be installed and
configured:

### systemd

`existance` relies on a `systemd` service template that goes by the name
`existdb@.service` and should be located in `/etc/systemd/system` on
Debian-based systems. It can be installed with:

    existance template systemd-unit > /etc/systemd/system/existdb@.service
    chown root.root /etc/systemd/system/existdb@.service

Assertions and the configured executing user may need to be adapted to your
environment.

This `systemd` unit itself relies on a control script that can properly start
and stop eXist-db instances on POSIX systems. It is expected to be available
as `/usr/local/bin/existctl` (for other locations the `systemd` units needs to
be adapted). Quiet obviously, this is how you get it:

    existance template existctl > /usr/local/bin/existctl
    chown existdb.root /usr/local/bin/existctl


### nginx

`existance` writes partial web server configurations to route requests whose
path start with an instance's name to the instance's Jetty process in the
directory `/etc/nginx/proxy-mappings`.
A template for such configuration can also be produced with the `template`
subcommand.
Make sure to include these in your general web server configuration
(`include /etc/nginx/proxy-mappings/*`) for the designated site. 

A **very basic** stub for a site configuration can be obtained with:

    existance template nginx-site > /etc/nginx/sites-available/existdb
    chown root.root /etc/nginx/sites-available/existdb


## Some supplemental architectural notes

All installed instances are recorded in a central `csv` file. It is used by the
mentioned `existctl` script and can be used for more tooling like monitoring as
directory. It only holds the instances' name, id and the maximal allocatable
memory for the JVM - name and id must never be changed manually.

A central paradigm is that an instance's id is used as the port that its Jetty
is listening to. Hence the restriction of available ports is a transitive
property of the id. As eXist-db should be run as unprivileged user, the use of
unprivileged ports is implied.

The id is also consumed by the `systemd` unit template, e.g. to disable the
instance or rather service in this context:

    systemctl disable existdb@8001

As the whole setup is targeted for production environments, an integrity
testing and backup task is configured with each installation. To avoid heavy
impact on a system's resources the tasks are spread with 15 minute intervals.
The backups accumulate indefinitely, so be advised to regularly run something
like

    find /opt -mindepth 3 -maxdepth 3  -path "*/backup/*" -mtime +7 -delete


## Installing existance

Clone or download the source code and run this command from the folder that
contains the `setup.py`:

    sudo python3.6 -m pip install .

This installs `existance` globally, you can omit the `sudo` command and add the
`--user` option after the `install` subcommand.


## Configuring existance

A configuration file that defines common properties of all installations is
expected either at `/etc/existance.ini` or as `.existance.ini` in your home
directory where the latter takes precedence. It must contain definitions for
all keys that are presented in this sample:


```ini
[existance]

# installation files are cached here for repeated usage
installer_cache = /var/cache/existance

[exist-db]

# the system user and usergroup that an installed / upgraded instance
# will be run as
user = existdb
group = existdb-users

# the instances' directories will be located within this directory
base_directory = /opt
# the pattern must be congruent with the variable `instance_dir`'s value in the
# existctl script and the assertion's argument in the systemd unit file
instance_dir_pattern = exist_{instance_name}_{instance_id}
# this file serves as index of all instances and a few settings
instances_settings = %(base_directory)s/exist_instances_settings.csv

# the various log data is grouped within this directory
log_directory = /var/logs/existdb

# the default -XmX value for new instances
XmX_default = 1024m
```

These configuration parameters can be defined optionally. Where a value is
documented, it is the default.

```ini
[exist-db]
# this list contains names of Jetty configuration files that are not to be
# used, e.g. because a modern web server can do the job for all instances
unwanted_jetty_configs = jetty-ssl.xml,jetty-ssl-context.xml,jetty-https.xml

[nginx]
# this value can be set with a comma-separated list of IPs and networks (CIDR)
# that are allowed to access sensible parts of the web application.
trusted_clients = 
```

There are still many opinionated values hardcoded in the tool respectively the
accompanying script and configuration templates based on our concrete needs.
You're welcome to request extended configurability or to contribute patches in
this regard.


## Usage

`existance` knows and dispatches to some subcommands that perform operations
and are described below.

For a full reference of the available command-line parameters use
`existance --help` and `existance <subcommand> --help`.

The general parameters should only be used to override the values from the
configuration file. Subcommand-specific parameters that are needed and not
provided at the command line will be asked for.

### install

In a nutshell this command:

- proposes some sensible configuration values unless provided
- downloads and caches an eXist-db installer if needed
- updates the instances directory / settings file
- invokes the installer after giving you some advices
- performs further configurations as mentioned above
- starts the newly installed instance

E.g., on a host that is configured to serve the domain `exist.mydomain.web`,
after running

    existance install --name my_project

the instance's dashboard is available at https://exist.mydomain.web/my_project/
and you're good to go.

### uninstall

This is basically the opposite of the previous and you can get rid of an
instance as easy as you type:

    existance uninstall --id <id>

### upgrade

Is the prospect of upgrading such a complex setup frightening you? With
`existance` it doesn't need to. Just the targeted instance and version need to
be specified:

    existance upgrade --id <id> --version <version>

Make sure you test your upgrade path with test instances as there may be issues
arising with old data and new software.
Consult the release notes of all versions released between the currently
installed and the designated versions!

The software and the data folder are kept with a datetime suffix. If an error
occurs during the upgrade, these are restored.

### template

TBA


## Further recommendations

We highly recommend to monitor the used hosts' and instances' resources to be
ahead of possible instabilities.



[eXist-db]: https://exist-db.org/
[nginx]: https://nginx.org/
[requests]: http://docs.python-requests.org/
[systemd]: https://www.freedesktop.org/wiki/Software/systemd/
