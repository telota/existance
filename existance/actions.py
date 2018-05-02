import re
import shutil
import textwrap
from abc import ABC, abstractmethod
from csv import DictReader
from datetime import datetime

import requests

from existance.constants import (
    EXISTDB_INSTALLER_URL, LATEST_EXISTDB_RECORD_URL
)
from existance.utils import make_password_proposal


is_semantical_version = re.compile(r'^\d+\.\d+(\.\d+)?').match
is_valid_xmx_value = re.compile(r'^\d+[kmg]]$').match


__all__ = []


def export(obj):
    __all__.append(obj.__name__)
    return obj


class Abort(Exception):
    """ Raised to invoke an undo of all previously executed dos. """


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


class EphemeralAction(ActionBase):
    @abstractmethod
    def do(self):
        pass


class ConcludedMessage:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        print(self.message, end=' ')

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            print('✔')
        else:
            print('✖️')

#


@export
class CalculateTargetPaths(EphemeralAction):
    def do(self):
        base = self.context.target_base = (
            self.args.base_directory /
            self.config['exist-db'].get('instance_dir_pattern', '{instance_name}')
                .format(instance_name=self.args.name, instance_id=self.args.id)
        )
        self.context.target_dir = base / 'existdb'
        self.context.target_data_dir = base / 'data'


@export
class DownloadInstaller(EphemeralAction):
    def do(self):
        self.context.installer_location = (
            self.config['existance']['installer_cache'] /
            'exist-installer-{version}.jar'.format(version=self.args.version)
        )

        if self.context.installer_location.exists():
            print(
                "Installer found at {location}. '✔'"
                .format(location=self.context.installer_location)
            )
            return

        with ConcludedMessage('Obtaining installer'):
            response = requests.get(
                EXISTDB_INSTALLER_URL.format(version=self.args.version),
                stream=True
            )
            with self.context.installer_location.open('wb') as f:
                for chunk in response.iter_content(chunk_size=4096):
                    f.write(chunk)

            # TODO file ownership?


@export
class GetLatestExistVersion(EphemeralAction):
    def do(self):
        self.context.latest_existdb_version = requests.get(
            LATEST_EXISTDB_RECORD_URL
        ).json()['tag_name']


@export
class InstallerPrologue(EphemeralAction):
    # TODO remove when solved: https://github.com/eXist-db/exist/issues/964

    def do(self):
        year = datetime.today().year
        print(textwrap.dedent(f"""
            A long time ago in a galaxy far too close to be ignored…
            It is the the year {year}, you're about to install an eXist-db and in the
            process you will be challenged with the mashup of a Turing and a Weichsler
            test resembled in something baptized as 'interactive installer'.
            Of course you shouldn't worry about it - it's just a test -  or even take it
            serious, but here are some hints to get you through:
            
            When asked for a target path, you *MUST* repeat these words:
                {self.context.target_dir}
            Will this lead the way to wisdom or just a swamp hole at the galaxy's pampa
            belt?
            
            The new oil - which was gold before - is data, put its vault there:
                {self.context.target_data_dir.reloative_to(self.context.target_dir)}
            
            May it be the wisdom evoked by modern computing powers you want to pretend
            or just protection against little green hoodlums, this one seems to be a good
            curse, er, administrator's password:
                {make_password_proposal(32)}
            
            Everything else is a matter of taste or not a matter at all.        
        """).strip())


@export
class MakeDataDir(Action):
    # TODO remove when fixed: https://github.com/eXist-db/exist/issues/1576
    def __init__(self):
        self.created = False

    def do(self):
        if not self.context.target_data_dir.exists():
            try:
                self.context.target_data_dir.mkdir()
            except Exception:
                self.created = self.context.target_data_dir.exists()
                raise

    def undo(self):
        if self.created:
            shutil.rmtree(self.context.target_data_dir)


@export
class ReadInstancesSettings(EphemeralAction):
    def do(self):
        with open(self.args.instances_settings, 'rt') as f:
            self.context.instances_settings = {
                int(x['id']): x for x in DictReader(f, fieldnames=('id', 'name', 'xmx'))
            }


@export
class SetDesignatedExistDBVersion(EphemeralAction):
    def do(self):
        args = self.args
        proposed_version = self.context.latest_existdb_version

        while args.version is None or not is_semantical_version(args.version):
            value = input(
                'Which version of eXist-db shall be installed or upgraded to? '
                '[{proposed_version}]'
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
        proposed_id = max(instances_settings) + 1

        while args.id is None or args.id in instances_settings:
            value = input(
                "Please enter the designated instance's ID [{proposed}]: "
                .format(proposed=proposed_id)
            )
            if not value:
                args.id = proposed_id
            if value in instances_settings:
                print(
                    "Instance ID is already in use, please select another one."
                )


@export
class SetDesignatedInstanceName(EphemeralAction):
    def do(self):
        args, context = self.args, self.context
        expected_pattern = r'^[a-z_-]{4,}$'  # TODO configurable?
        used_names = [x['name'] for x in context.instances_settings]

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
        xmx_default = self.config['exist-db'].get('XmX_default', '1024m')

        while args.xmx is None or not is_valid_xmx_value(args.xmx):
            value = input(
                "What's the size for the memory allocation pool? "
                "[{xmx_default}]".format(xmx_default=xmx_default)
            )
            if not value:
                args.xmx = xmx_default
            elif not is_valid_xmx_value(value):
                print(
                    "The provided value is not valid, please enter something "
                    "like '1024m'."
                )
