import csv
import re
import shutil
import subprocess
import sys
import textwrap
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import requests

from existance.constants import (
    EXISTDB_INSTALLER_URL, LATEST_EXISTDB_RECORD_URL, INSTANCE_PORT_RANGE_START,
    INSTANCE_SETTINGS_FIELDS
)
from existance.templates import (
    NGINX_MAPPING_ROUTE, NGINX_MAPPING_STATUS_FILTER, TEMPLATES
)
from existance.utils import make_password_proposal, relative_path


is_semantical_version = re.compile(r'^\d+\.\d+(\.\d+)?').match
is_valid_xmx_value = re.compile(r'^\d+[kmg]]$').match


csv.register_dialect(
    'instances_settings', csv.unix_dialect,
    quoting=csv.QUOTE_NONE, skipinitialspace=True
)


__all__ = []


# exceptions


class Abort(Exception):
    """ Raised to invoke an undo of all previously executed dos. """


# bases


class ActionBase(ABC):
    def __init__(self, executor: 'PlanExecutor'):
        self.executor = executor

    def __getattr__(self, item):
        if hasattr(self.executor, item):
            return getattr(self.executor, item)
        raise AttributeError(
            "{self} has no attribute '{item}'".format(self=repr(self), item=item)
        )


class Action(ActionBase):
    @abstractmethod
    def do(self):
        pass

    @abstractmethod
    def undo(self):
        pass


def counter(action_cls: type) -> type:
    class CounterAction(Action):
        def __init__(self, executor):
            self._action = action_cls(executor)

        def do(self):
            self._action.undo()

        def undo(self):
            raise RuntimeError('This code path is not expected yet.')

    return CounterAction


class EphemeralAction(ActionBase):
    @abstractmethod
    def do(self):
        pass


# helpers


class ConcludedMessage:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        print(self.message, end=' ', flush=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            print('\033[92m✔\033[0m', flush=True)
        else:
            print('\033[91m✖️\033[0m', flush=True)


def export(obj):
    __all__.append(obj.__name__)
    return obj


def external_command(*args, **kwargs):
    args = tuple(str(x) for x in args)
    run_kwargs = {'stdin': sys.stdin, 'stdout': sys.stdout, 'stderr': sys.stderr,
                  'check': True}
    run_kwargs.update(kwargs)
    subprocess.run(args, **kwargs)
    # TODO *maybe* the input argument can be used to provide input and thus the installer
    # may not require user input


#


@export
class AddBackupTask(EphemeralAction):
    # TODO this should rather be defined in the config file
    def do(self):
        with ConcludedMessage("Adding backup job to exist's config."):
            tree = ElementTree.parse(self.context.existdb_config)

            scheduler = tree.find('./scheduler')

            job = ElementTree.SubElement(scheduler, 'job')
            job.set('name', f'{self.args.name}_consistency_check_and_backup')
            job.set('type', 'system')
            job.set('class', 'org.exist.storage.ConsistencyCheckTask')
            job.set('period', str(4 * 60 * 60 * 1000))  # every 4h
            job.set('delay', str((self.args.id - INSTANCE_PORT_RANGE_START) * 15 * 60 * 1000))  # 15min offset per instance

            for name, value in (
                ('output', '../backup'), ('backup', 'yes'), ('incremental', 'yes'),
                ('incremental-check', 'yes'), ('max', '6')
            ):
                parameter = ElementTree.SubElement(job, 'parameter')
                parameter.set('name', name)
                parameter.set('value', value)

            tree.write(self.context.existdb_config)


class AddProxyMapping(Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO make this configurable
        self.mapping_path = Path('/etc') / 'nginx' / 'proxy-mappings' / str(self.args.id)

    def do(self):
        snippet = NGINX_MAPPING_ROUTE
        trusted_clients = self.config.get('nginx', 'trusted_clients', fallback='').split(',')
        if trusted_clients:
            snippet += NGINX_MAPPING_STATUS_FILTER

        snippet.replace('<instance_id>', str(self.args.id))
        snippet.replace('<instance_name>', self.args.name)
        snippet.replace('allow <trusted_client>;', ' '.join(
                            f'allow {x};' for x in trusted_clients)
                        )

        with ConcludedMessage("Writing instance specific nginx config."):
            with self.mapping_path.open('wt') as f:
                print(snippet, file=f)
            external_command('chown', f'root:{self.args.group}', self.mapping_path)
            external_command('chmod', 'ug=rw,o=r', self.mapping_path)

    def undo(self):
        with ConcludedMessage("Removing instance specific nginx config."):
            self.mapping_path.unlink()


@export
class CalculateTargetPaths(EphemeralAction):
    def do(self):
        base = self.context.instance_dir = (
            self.args.base_directory /
            self.config['exist-db'].get('instance_dir_pattern', '{instance_name}')
                .format(instance_name=self.args.name, instance_id=self.args.id)
        )

        self.context.installation_dir = base / 'existdb'
        self.context.backup_dir = base / 'backup'
        self.context.data_dir = base / 'data'

        self.context.existdb_config = self.context.installation_dir / 'conf.xml'
        self.context.controller_config = self.context.installation_dir / 'webapp' / 'WEB-INF' / 'controller-config.xml'
        self.context.jetty_config = (
             self.context.installation_dir / 'tools' / 'jetty' / 'webapps' /
             'exist-webapp-context.xml'
        )


# TODO make this configurable
@export
class ConfigureSerialization(EphemeralAction):
    def do(self):
        with ConcludedMessage("Configuring serialization settings."):
            tree = ElementTree.parse(self.context.existdb_config)

            config = tree.find('./serializer')
            config.set('indent', 'no')

            tree.write(self.context.existdb_config)


@export
class CopyDatasnapshot(EphemeralAction):
    def do(self):
        with ConcludedMessage('Copying data snapshot to new installation.'):
            shutil.copytree(self.context.data_snapshot, self.context.data_dir)


@export
class CreateBackupDirectory(Action):
    def do(self):
        with ConcludedMessage('Creating backup folder.'):
            self.context.backup_dir.mkdir()

    def undo(self):
        with ConcludedMessage('Removing backup folder.'):
            shutil.rmtree(self.context.backup_dir)


@export
class DownloadInstaller(EphemeralAction):
    def do(self):
        self.context.installer_location = self.args.installer_cache / f'exist-installer-{self.args.version}.jar'

        if self.context.installer_location.exists():
            print(
                "Installer found at {location}. \033[92m✔\033[0m"
                .format(location=self.context.installer_location)
            )
            return

        with ConcludedMessage('Obtaining installer.'):
            response = requests.get(
                EXISTDB_INSTALLER_URL.format(version=self.args.version),
                stream=True
            )
            with self.context.installer_location.open('wb') as f:
                for chunk in response.iter_content(chunk_size=4096):
                    f.write(chunk)


@export
class DumpTemplate(EphemeralAction):
    def do(self):
        print(TEMPLATES[self.args.name])


@export
class EnableSystemdUnit(Action):
    def do(self):
        with ConcludedMessage('Enabling systemd unit for instance.'):
            external_command('systemctl', 'enable', f'existdb@{self.args.id}')

    def undo(self):
        with ConcludedMessage('Disabling systemd unit for instance.'):
            external_command('systemctl', 'disable', f'existdb@{self.args.id}')


@export
class GetInstanceName(EphemeralAction):
    def do(self):
        self.args.name = self.context.instances_settings[self.args.id]['name']


@export
class GetLatestExistVersion(EphemeralAction):
    def do(self):
        with ConcludedMessage('Obtaining latest available version.'):
            # FIXME get the full list and filter out RC releases
            self.context.latest_existdb_version = requests.get(
                LATEST_EXISTDB_RECORD_URL
            ).json()['tag_name'].split('-', maxsplit=1)[1]


@export
class InstallerPrologue(EphemeralAction):
    # TODO remove when solved: https://github.com/eXist-db/exist/issues/964

    def do(self):
        year = datetime.today().year
        print(textwrap.dedent(f"""\
            A long time ago in a galaxy far too close to be ignored…
            It is the the year {year}, you're about to install an eXist-db and in the
            process you will be challenged with the mashup of a Turing and a Weichsler
            test resembled in something baptized as 'interactive installer'.
            Of course you shouldn't worry about it - it's just a test -  or even take it
            serious, but here are some hints to get you through:
            
            When asked for a target path, you *MUST* repeat these words:
                {self.context.installation_dir}
            Will this lead the way to wisdom or just a swamp hole at the galaxy's pampa
            belt?
            
            The new oil - which was gold before - is data, put its vault there:
                {relative_path(self.context.data_dir, self.context.installation_dir)}
            
            May it be the wisdom evoked by modern computing powers you want to pretend
            or just protection against little green hoodlums, this one seems to be a good
            curse, er, administrator's password:
                {make_password_proposal(32)}
            
            Everything else is a matter of taste or not a matter at all.        
        """))


@export
class LoadRetainedConfigs(EphemeralAction):
    def do(self):
        retained_configs = {}
        with ConcludedMessage('Loading configs that will be re-used.'):

            for config in (
                    self.context.existdb_config,
                    self.context.controller_config,
                    self.context.jetty_config,
            ):
                with config.open('rt') as f:
                    retained_configs[config] = f.read()

            self.context.retained_configs = retained_configs


@export
class MakeDataDir(Action):
    # TODO remove when fixed: https://github.com/eXist-db/exist/issues/1576
    def do(self):
        if not self.context.data_dir.exists():
            with ConcludedMessage('Creating the data directory.'):
                self.context.data_dir.mkdir(parents=True)

    def undo(self):
        with ConcludedMessage('Removing data dir.'):
            shutil.rmtree(self.context.data_dir)


@export
class MakeInstanceDirectory(Action):
    def do(self):
        target = self.context.instance_dir
        with ConcludedMessage(f'Creating instance directory {target}'):
            target.mkdir(parents=True)

    def undo(self):
        target = self.context.instance_dir
        with ConcludedMessage(f'Removing instance directory {target}'):
            shutil.rmtree(self.context.instance_dir)


@export
class MakeSnapshot(Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snapshot_suffix = datetime.now().strftime('-%Y-%m-%d-%H-%M')

    def do(self):
        context = self.context
        data_dir = context.data_dir
        installation_dir = context.installation_dir

        context.data_snapshot = data_dir.with_name(data_dir.name + self.snapshot_suffix)
        context.installation_snapshot = installation_dir.with_name(installation_dir.name + self.snapshot_suffix)

        with ConcludedMessage(
                f'Snapshotting current installation and data folder with suffix {self.snapshot_suffix}'
        ):
            installation_dir.rename(context.installation_snapshot)
            shutil.copytree(data_dir, context.data_snapshot)

    def undo(self):
        context = self.context
        installation_dir = context.installation_dir
        data_dir = context.data_dir

        with ConcludedMessage('Restoring installation and data snapshot.'):
            context.installation_snapshot.rename(installation_dir)
            shutil.rmtree(data_dir)
            context.data_snapshot.rename(data_dir)


@export
class ReadInstancesSettings(EphemeralAction):
    def do(self):
        with open(self.args.instances_settings, 'rt') as f:
            self.context.instances_settings = {
                int(x['id']): x
                for x in csv.DictReader(
                    f, fieldnames=INSTANCE_SETTINGS_FIELDS,
                    dialect='instances_settings'
                )
            }


@export
class ReloadNginx(EphemeralAction):
    def do(self):
        with ConcludedMessage('Reloading nginx configuration.'):
            external_command('systemctl', 'reload', 'nginx')


@export
class RemoveUnwantedJettyConfig(EphemeralAction):
    def do(self):
        unwanted_tokens = self.config.get(
            'exist-db', 'unwanted_jetty_configs',
            fallback='jetty-ssl.xml,jetty-ssl-context.xml,jetty-https.xml'
        ).split(',')
        config_path = (
            self.context.installation_dir / 'tools' / 'jetty' / 'etc' /
            'standard.enabled-jetty-configs'
        )
        with ConcludedMessage('Disabling unwanted parts of the Jetty config.'):
            for token in unwanted_tokens:
                external_command('sed', '-i', f'/{token}/d', config_path)


@export
class RunExistInstaller(Action):
    def do(self):
        external_command(
            'java', '-jar', self.context.installer_location, '-console'
        )

    def undo(self):
        with ConcludedMessage('Removing installation folder.'):
            shutil.rmtree(self.context.installation_dir, ignore_errors=True)


@export
class SaveRetainedConfigs(EphemeralAction):
    def do(self):
        with ConcludedMessage('Restoring old configs.'):
            for config, data in self.context.retained_configs.items():
                with config.open('tw') as f:
                    print(data, file=f)


@export
class SelectInstanceID(EphemeralAction):
    def do(self):
        args = self.args
        instances_settings = self.context.instances_settings

        while args.id is None or args.id not in instances_settings:
            print('Select one of the following ids to proceed:')
            for item in instances_settings.values():
                print(f'{item["id"]}: {item["name"]}')

            value = input('> ')
            try:
                args.id = int(value)
            except ValueError:
                args.id = None


@export
class SetDesignatedExistDBVersion(EphemeralAction):
    def do(self):
        args = self.args
        proposed_version = self.context.latest_existdb_version

        while args.version is None or not is_semantical_version(args.version):
            value = input(
                'Which version of eXist-db shall be installed or upgraded to? '
                '[{proposed_version}] '
                .format(proposed_version=proposed_version)
            )
            if not value:
                args.version = proposed_version
            elif not is_semantical_version(value):
                'This is not a valid version qualifier.'
            else:
                args.version = value


@export
class SetDesignatedInstanceID(EphemeralAction):
    def do(self):
        args, instances_settings = self.args, self.context.instances_settings

        if instances_settings:
            proposed_id = max(instances_settings.keys()) + 1
        else:
            proposed_id = INSTANCE_PORT_RANGE_START

        while args.id is None or args.id in instances_settings:
            value = input(
                "Please enter the designated instance's ID [{proposed}]: "
                .format(proposed=proposed_id)
            )
            if not value:
                value = proposed_id
            if value in instances_settings:
                print(
                    "Instance ID is already in use, please select another one."
                )
            else:
                args.id = int(value)


@export
class SetDesignatedInstanceName(EphemeralAction):
    def do(self):
        args, context = self.args, self.context
        expected_pattern = r'^[a-z_-]{4,}$'  # TODO configurable?
        used_names = [x['name'] for x in context.instances_settings.values()]

        while args.name is None or args.name in used_names \
                or not re.match(expected_pattern, args.name):
            value = input(
                "Please enter the designated instance's name "
                "(must match {pattern}): ".format(pattern=expected_pattern)
            )
            if value in used_names:
                print(
                    "Instance name is already in use, please select another one."
                )
            elif not re.match(expected_pattern, value):
                print("The name must match the expected pattern.")
            else:
                args.name = value


@export
class SetDesignatedXmXValue(EphemeralAction):
    def do(self):
        args = self.args

        while args.xmx is None or not is_valid_xmx_value(args.xmx):
            value = input("What's the size for the memory allocation pool? ")
            args.xmx = value
            if not is_valid_xmx_value(value):
                print(
                    "The provided value is not valid, please enter something "
                    "like '1024m'."
                )


@export
class SetFilePermissions(EphemeralAction):
    def do(self):
        with ConcludedMessage('Adjusting file access permissions.'):
            external_command(
                'chown', '-R', f'{self.args.user}.{self.args.group}',
                self.context.instance_dir
            )
            external_command(
                'chmod', 'g+w',
                self.context.instance_dir, self.context.installation_dir,
                self.context.backup_dir, self.context.data_dir
            )

        with ConcludedMessage(
                'Allow write access to all xml-files for group-members in the '
                'application directory.'
        ):
            for xml_file in self.context.installation_dir.glob('**/*.xml'):
                external_command('chmod', 'g+w', xml_file)


@export
class SetJettyWebappContext(EphemeralAction):
    def do(self):
        with ConcludedMessage("Setting Jetty's context path."):
            tree = ElementTree.parse(self.context.jetty_config)
            tree.find("./Set[@name='contextPath']").text = f'/{self.args.name}'
            tree.write(self.context.jetty_config)


@export
class SetupLoggingAggregation(Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO make that configurable
        self.base_dir = Path('/var') / 'log' / 'existdb' / f'{self.args.id}_{self.args.name}'

    def do(self):
        with ConcludedMessage('Setting up log folder.'):
            self.base_dir.mkdir(mode=0o770, parents=True)
            external_command('chown', f'{self.args.user}:{self.args.group}', self.base_dir)
            (self.base_dir / 'jetty').symlink_to(
                self.context.installation_dir / 'tools' / 'jetty' / 'logs'
            )
            (self.base_dir / 'existdb').symlink_to(
                self.context.installation_dir / 'webapp' / 'WEB-INF' / 'logs'
            )

    def undo(self):
        with ConcludedMessage('Removing log folder.'):
            shutil.rmtree(self.base_dir)


@export
class StartSystemdUnit(Action):
    def do(self):
        with ConcludedMessage('Starting systemd unit for instance.'):
            external_command('systemctl', 'start', f'existdb@{self.args.id}')

    def undo(self):
        with ConcludedMessage('Stopping systemd unit for instance.'):
            external_command('systemctl', 'stop', f'existdb@{self.args.id}')


@export
class WriteInstanceSettings(Action):
    def do(self):
        with ConcludedMessage("Adding instance's settings."):
            _id = self.args.id
            self.context.instances_settings[_id] = {
                'id': _id,
                'name': self.args.name,
                'xmx': self.args.xmx
            }
            self._write()

    def undo(self):
        if self.args.id in self.context.instances_settings:
            with ConcludedMessage("Removing this instance's settings."):
                self.context.instances_settings.pop(self.args.id)
                self._write()

    def _write(self):
        with open(self.args.instances_settings, 'wt') as f:
            writer = csv.DictWriter(f, fieldnames=INSTANCE_SETTINGS_FIELDS, dialect='instances_settings')
            writer.writerows((x for x in self.context.instances_settings.values()))
