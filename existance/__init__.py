import argparse
import sys
from configparser import ConfigParser
from pathlib import Path
from traceback import print_exc
from types import SimpleNamespace
from typing import List, Tuple

from existance import actions
from existance.constants import TMP


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
        print('Rolling back changes… ', end ='')
        for action in self.rollback_plan:
            try:
                action()
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
    result = [
        actions.GetLatestExistVersion,
        actions.ReadInstancesSettings,
        actions.SetDesignatedInstanceID,
        actions.SetDesignatedInstanceName,
        actions.SetDesignatedExistDBVersion,
        actions.CalculateTargetPaths,
        actions.DownloadInstaller,
        actions.MakeDataDir,
    ]

    return result


def make_uninstall_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    raise NotImplementedError


def make_upgrade_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    raise NotImplementedError


def make_systemd_tenmplate_plan(args: argparse.Namespace) -> List[actions.ActionBase]:
    raise NotImplementedError


def parse_args(args: Tuple[str], config) -> argparse.Namespace:
    # TODO description
    root_parser = argparse.ArgumentParser()
    subcommands = root_parser.add_subparsers()

    root_parser.add_argument(
        '--base-directory',
        default=config['exist-db']['base_directory'], type=Path,
        help='TODO'
    )
    root_parser.add_argument(
        '--instances-settings',
        default=config['exist-db']['instances_settings'], type=Path,
        help='TODO'
    )
    root_parser.add_argument(
        '--log-directory',
        default=config['exist-db']['log_directory'], type=Path,
        help='TODO'
    )

    root_parser.add_argument(
        '--installer-cache',
        default=config['existance'].get('installer_cache', TMP), type=Path,
        help='TODO'
    )

    install_parser = subcommands.add_parser('install')
    install_parser.set_defaults(plan_factory=make_install_plan)
    install_parser.add_argument(
        '--group', default=config['exist-db']['group'],
        help='TODO',
    )
    install_parser.add_argument(
        '--id', default=None,
        help='TODO'
    )
    install_parser.add_argument(
        '--name', default=None,
        help='TODO'
    )
    install_parser.add_argument(
        '--unwanted-jetty-configs',
        default=config['exist-db']['unwanted_jetty_configs'],
        help='TODO',
    )
    install_parser.add_argument(
        '--user', default=config['exist-db']['user'],
        help='TODO',
    )
    install_parser.add_argument(
        '--version', default=None,
        help='TODO',
    )
    install_parser.add_argument(
        '--xmx',
        help='TODO',
    )

    uninstall_parser = subcommands.add_parser('uninstall')
    uninstall_parser.set_defaults(plan_factory=make_uninstall_plan)

    upgrade_parser = subcommands.add_parser('upgrade')
    upgrade_parser.set_defaults(plan_factory=make_upgrade_plan)

    systemd_template_parser = subcommands.add_parser('systemd-service-template')
    systemd_template_parser.set_defaults(plan_factory=make_systemd_tenmplate_plan)

    return root_parser.parse_args(args)


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


def main(args=sys.argv[1:]):
    # TODO fork self with sudo if not executed as root
    try:
        config = read_config()
        args = parse_args(args, config)
        actions_plan = args.plan_factory(args, config)
        executor = PlanExecutor(actions_plan, args, config)
        raise SystemExit(executor())
    except KeyboardInterrupt:
        print('Received keyboard interrupt, rolling back.')
        executor.do_rollback()
    except SystemExit as e:
        exit_code = e.code
    except Exception:
        print('Please report this unhandled exception:')
        print_exc(file=sys.stdout)
        exit_code = 3
    finally:
        sys.exit(exit_code)


if __name__ == '__main__':
    main()
