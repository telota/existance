import argparse
import os
import sys
from argparse import RawDescriptionHelpFormatter
from configparser import ConfigParser
from pathlib import Path
from textwrap import dedent
from traceback import print_exc
from types import SimpleNamespace
from typing import List, Tuple

from existance import actions
from existance.constants import TMP


#


POSSIBLE_CONFIG_LOCATIONS = (Path('~') / '.existance.ini', Path('/etc') / 'existance.ini')

cli_parser = None


#


class PlanExecutor:
    def __init__(self, plan: List[actions.ActionBase], args: argparse.Namespace,
                 config: ConfigParser):

        self.plan = plan
        self.args = args
        self.config = config

        self.context = SimpleNamespace()
        self.rollback_plan = []

    def __call__(self) -> int:
        return self.execute_plan()

    def do_rollback(self):
        print('Rolling back changes… ')
        for action in self.rollback_plan:
            try:
                action.undo()
            except KeyboardInterrupt:
                pass
            except Exception:
                print('Please report this unhandled exception:')
                print_exc()
                print('The rollback is continued anyway.')

    def execute_plan(self) -> int:
        """ Runs all designated actions and rolls back on encountered errors.

        :returns: The exit code that shall be emitted.
        """

        for action in self.plan:
            try:
                action = action(self)
                if not isinstance(action, actions.EphemeralAction):
                    self.rollback_plan.insert(0, action)
                action.do()
            except KeyboardInterrupt:
                print('Process aborted.')
                self.do_rollback()
                raise SystemExit(1)
            except Exception:
                print('Please report this unhandled exception:')
                print_exc()
                self.do_rollback()
                raise SystemExit(3)

        return 0


# initialization


def make_install_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    return [
        actions.GetLatestExistVersion,

        actions.ReadInstancesSettings,
        actions.SetDesignatedInstanceID,
        actions.SetDesignatedInstanceName,
        actions.SetDesignatedExistDBVersion,
        actions.CalculateTargetPaths,

        actions.DownloadInstaller,
        actions.MakeInstanceDirectory,
        actions.MakeDataDir,
        actions.InstallerPrologue,
        actions.RunExistInstaller,
        actions.CreateBackupDirectory,
        actions.SetFilePermissions,
        actions.SetJettyWebappContext,
        actions.AddBackupTask,
        actions.ConfigureSerialization,
        actions.AddProxyMapping,
        actions.SetupLoggingAggregation,
        actions.WriteInstanceSettings,
        actions.EnableSystemdUnit,
        actions.StartSystemdUnit,
        actions.ReloadNginx,
    ]


def make_template_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    return [
        actions.DumpTemplate,
    ]



def make_uninstall_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    return [
        actions.ReadInstancesSettings,
        actions.SelectInstanceID,
        actions.GetInstanceName,
        actions.CalculateTargetPaths,

        actions.counter(actions.StartSystemdUnit),
        actions.counter(actions.EnableSystemdUnit),
        actions.counter(actions.WriteInstanceSettings),
        actions.counter(actions.AddProxyMapping),
        actions.ReloadNginx,
        actions.counter(actions.MakeInstanceDirectory),
        actions.counter(actions.SetupLoggingAggregation),
    ]


def make_upgrade_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    return [
        actions.GetLatestExistVersion,

        actions.ReadInstancesSettings,
        actions.SelectInstanceID,
        actions.GetInstanceName,
        actions.SetDesignatedExistDBVersion,
        actions.CalculateTargetPaths,

        actions.counter(actions.StartSystemdUnit),
        actions.LoadRetainedConfigs,
        actions.MakeSnapshot,

        actions.DownloadInstaller,
        actions.MakeDataDir,
        actions.InstallerPrologue,
        actions.RunExistInstaller,

        actions.SaveRetainedConfigs,
        actions.RemoveUnwantedJettyConfig,
        actions.counter(actions.MakeDataDir),
        actions.CopyDatasnapshot,

        actions.SetFilePermissions,
        actions.StartSystemdUnit,
    ]


#


def add_id_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        '--id', type=int,
        help='Specifies the id of an existing or new instance.'
    )


def add_version_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        '--version',
        help='Specifies the version to install or to upgrade to.',
    )


def make_argparser(config: ConfigParser) -> argparse.ArgumentParser:
    global cli_parser

    if cli_parser is not None:
        return cli_parser

    cli_parser = argparse.ArgumentParser(formatter_class=RawDescriptionHelpFormatter)
    cli_parser.description = dedent("""\
    existance is a tool to manage several instances of eXist-db instances on a
    single host. It assumes systemd as the operating system's service manager and
    nginx as TLS-terminating proxy.
    
    For guidance on a first setup of all needed components, see the online 
    documentation and the help for the template subcommand.
    
    The general parameters should only be used to bypass the settings in the global
    configuration.
    
    In order to use any of the management commands the executing user's effective
    id must be 0, the tool will try to elevate privileges with the sudo command.
    
    The online documentation is currently available at:
    https://github.com/telota/existance/blob/master/README.md
    """)
    cli_parser.epilog = "Help for the subcommands can be printed by invoking them" \
                        "with the --help argument."

    subcommands = cli_parser.add_subparsers()

    cli_parser.add_argument(
        '--base-directory', type=Path, metavar='DIRPATH',
        default=config.get('exist-db', 'base_directory'),
        help='The base folder of the exist-db instances.'
    )
    cli_parser.add_argument(
        '--instances-settings', type=Path, metavar='FILEPATH',
        default=config.get('exist-db', 'instances_settings'),
        help='The file that collects a few information about the instances.'
    )
    cli_parser.add_argument(
        '--log-directory', type=Path, metavar='DIRPATH',
        default=config.get('exist-db', 'log_directory'),
        help='The base folder where the different log files folders of an instance '
             'are linked for quick access.'
    )
    cli_parser.add_argument(
        '--installer-cache', type=Path, metavar='DIRPATH',
        default=config.get('existance', 'installer_cache', fallback=TMP),
        help='A folder that is used as cache for eXist-db installation files.'
    )
    cli_parser.add_argument(
        '--user',
        default=config.get('exist-db', 'user'),
        help='The system user that is supposed to run the installed instances.',
    )
    cli_parser.add_argument(
        '--group',
        default=config.get('exist-db', 'group'),
        help='The system usergroup that is supposed to run the installed instances.',
    )
    cli_parser.add_argument(
        '--unwanted-jetty-configs', metavar='FILENAMES',
        default=config.get('exist-db', 'unwanted_jetty_configs'),
        help='A comma-separated list of Jetty configuration files that will be '
             'deactivated from the eXist-db distribution defaults.',
    )

    install_parser = subcommands.add_parser('install')
    install_parser.description = 'Installs a new eXist-db instance.'

    install_parser.set_defaults(plan_factory=make_install_plan)
    add_id_arg(install_parser)
    install_parser.add_argument(
        '--name',
        help='Specifies the name of the new instance.'
    )
    add_version_arg(install_parser)
    install_parser.add_argument(
        '--xmx', metavar='VALUE',
        default=config.get('exist-db', 'XmX_default'),
        help='Specifies the assigned XmX value for the new instance.',
    )

    uninstall_parser = subcommands.add_parser('uninstall')
    uninstall_parser.description = 'Uninstalls an existing instance.'
    uninstall_parser.set_defaults(plan_factory=make_uninstall_plan)
    add_id_arg(uninstall_parser)

    upgrade_parser = subcommands.add_parser('upgrade')
    upgrade_parser.description = 'Upgrades an existing instance to a new version.'
    upgrade_parser.set_defaults(plan_factory=make_upgrade_plan)
    add_id_arg(upgrade_parser)
    add_version_arg(upgrade_parser)

    template_parser = subcommands.add_parser('template')
    template_parser.description = 'Writes templates for required scripts and configuration files to stdout.'
    template_parser.set_defaults(plan_factory=make_template_plan)
    template_parser.add_argument('name', choices=('existctl', 'nginx-site', 'systemd-unit'))

    return cli_parser


def parse_args(args: Tuple[str], config: dict) -> argparse.Namespace:
    parser = make_argparser(config)
    return parser.parse_args(args)


def read_config():
    config = ConfigParser()

    for location in POSSIBLE_CONFIG_LOCATIONS:
        location = location.resolve()
        if location.is_file():
            config.read(location)
            break
    else:
        print(f'No valid configuration file found in '
              f'{" or ".join(str(x) for x in POSSIBLE_CONFIG_LOCATIONS)}.')
        raise SystemExit(1)

    return config


# main


def main(command=sys.argv[0], args=sys.argv[1:]):
    try:
        if '--help' not in sys.argv[1:]:
            if os.geteuid() != 0:
                os.execvp('sudo', ['sudo', command] + args)
            config = read_config()
        else:
            config = {}

        args = parse_args(args, config)
        actions_plan = args.plan_factory(args)
        executor = PlanExecutor(actions_plan, args, config)
        raise SystemExit(executor())
    except KeyboardInterrupt:
        print('\nReceived keyboard interrupt, rolling back.')
        executor.do_rollback()
        exit_code = 1
    except SystemExit as e:
        exit_code = e.code
    except Exception:
        print('\nPlease report this unhandled exception:')
        print_exc(file=sys.stdout)
        exit_code = 3
    finally:
        sys.exit(exit_code)


if __name__ == '__main__':
    main()
