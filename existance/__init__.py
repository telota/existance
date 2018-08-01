import argparse
import os
import sys
from configparser import ConfigParser
from pathlib import Path
from traceback import print_exc
from types import SimpleNamespace
from typing import List, Tuple

from existance import actions
from existance.constants import TMP


#


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
        print('Rolling back changes… ', end='')
        for action in self.rollback_plan:
            try:
                action.undo()
            except KeyboardInterrupt:
                pass
            except Exception:
                print('Please report this unhandled exception:')
                print_exc()
                print('The rollback is continued anyway.')
        print('✔')

    def execute_plan(self) -> int:
        """ Runs all designated actions and rolls back on encountered errors.

        :returns: The exit code that shall be emitted.
        """

        for action in self.plan:
            try:
                action = action(self)
                action.do()
            except Exception:
                if not isinstance(action, actions.EphemeralAction):
                    self.rollback_plan.insert(0, action)
                self.do_rollback()
                raise
            else:
                if not isinstance(action, actions.EphemeralAction):
                    self.rollback_plan.insert(0, action)

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


def make_systemd_template_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    raise NotImplementedError


#


def add_id_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        '--id', default=None, type=int,
        help='TODO'
    )


def add_version_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        '--version', default=None,
        help='TODO',
    )


def make_argparser(config: dict) -> argparse.ArgumentParser:
    global cli_parser

    if cli_parser is not None:
        return cli_parser

    # TODO description
    cli_parser = argparse.ArgumentParser()
    subcommands = cli_parser.add_subparsers()

    cli_parser.add_argument(
        '--base-directory',
        default=config['exist-db']['base_directory'], type=Path,
        help='TODO'
    )
    cli_parser.add_argument(
        '--instances-settings',
        default=config['exist-db']['instances_settings'], type=Path,
        help='TODO'
    )
    cli_parser.add_argument(
        '--log-directory',
        default=config['exist-db']['log_directory'], type=Path,
        help='TODO'
    )

    cli_parser.add_argument(
        '--installer-cache',
        default=config['existance'].pop('installer_cache', TMP), type=Path,
        help='TODO'
    )
    cli_parser.add_argument(
        '--user', default=config['exist-db']['user'],
        help='TODO',
    )
    cli_parser.add_argument(
        '--group', default=config['exist-db']['group'],
        help='TODO',
    )
    cli_parser.add_argument(
        '--unwanted-jetty-configs',
        default=config['exist-db']['unwanted_jetty_configs'],
        help='TODO',
    )

    install_parser = subcommands.add_parser('install')
    install_parser.set_defaults(plan_factory=make_install_plan)
    add_id_arg(install_parser)
    install_parser.add_argument(
        '--name', default=None,
        help='TODO'
    )
    add_version_arg(install_parser)
    install_parser.add_argument(
        '--xmx',
        help='TODO',
    )

    uninstall_parser = subcommands.add_parser('uninstall')
    uninstall_parser.set_defaults(plan_factory=make_uninstall_plan)
    add_id_arg(uninstall_parser)

    upgrade_parser = subcommands.add_parser('upgrade')
    upgrade_parser.set_defaults(plan_factory=make_upgrade_plan)
    add_id_arg(upgrade_parser)
    add_version_arg(upgrade_parser)

    systemd_template_parser = subcommands.add_parser('systemd-service-template')
    systemd_template_parser.set_defaults(plan_factory=make_systemd_template_plan)

    return cli_parser


def parse_args(args: Tuple[str], config: dict) -> argparse.Namespace:
    parser = make_argparser(config)
    return parser.parse_args(args)


def read_config():
    config = ConfigParser()

    for location in (
            Path('~') / '.existance.ini', Path('/etc') / 'existance.ini'
    ):
        location = location.resolve()
        if location.is_file():
            config.read(location)
            break
    else:
        print('No valid configuration file found.')
        raise SystemExit(1)

    # TODO validate config for completeness

    return config


# main


def main(command=sys.argv[0], args=sys.argv[1:]):
    try:
        if os.geteuid() != 0:
            os.execvp('sudo', ['sudo', command] + args)
        config = read_config()
        args = parse_args(args, config)
        if not hasattr(args, 'plan_factory'):
            cli_parser.print_help()
            raise SystemExit(0)
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
