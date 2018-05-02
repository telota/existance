import re
from abc import ABC, abstractmethod
from csv import DictReader
from pathlib import Path

import requests

from existance.constants import (
    EXISTDB_INSTALLER_URL, LATEST_EXISTDB_RECORD_URL
)


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


#


@export
class DownloadInstaller(EphemeralAction):
    def do(self):
        self.context.installer_location = (
            self.config['existance']['installer_cache'] /
            'exist-installer-{version}.jar'.format(version=self.args.version)
        )

        if self.context.installer_location.exists():
            print(
                "Installer found at {location}."
                .format(location=self.context.installer_location)
            )
            return

        print('Obtaining installer', end='')
        response = requests.get(
            EXISTDB_INSTALLER_URL.format(version=self.args.version),
            stream=True
        )
        with self.context.installer_location.open('wb') as f:
            for chunk in response.iter_content(chunk_size=4096):
                f.write(chunk)
        print('✔')


@export
class GetLatestExistVersion(EphemeralAction):
    def do(self):
        self.context.latest_existdb_version = requests.get(
            LATEST_EXISTDB_RECORD_URL
        ).json()['tag_name']


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
