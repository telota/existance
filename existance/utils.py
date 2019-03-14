import random
import subprocess
from pathlib import Path

from existance.constants import (
    INTERACTIVE_SUBPROCESS_KWARGS,
    PASSWORD_CHARACTERS,
    SEPARATOR
)


def external_command(*args, **kwargs) -> subprocess.CompletedProcess:
    # TODO *maybe* the input argument can be used to provide input and thus the
    #      installer may not require user input

    args = tuple(str(x) for x in args)
    run_kwargs = {} if "capture_output" in kwargs else INTERACTIVE_SUBPROCESS_KWARGS
    result = subprocess.run(args, **{'check': True, **run_kwargs, **kwargs})
    return result


def make_password_proposal(length: int = 32) -> str:
    result = ""
    while len(result) < length:
        result += random.choice(PASSWORD_CHARACTERS)
    return result


def relative_path(target: Path, source: Path) -> Path:
    for path in (target, source):
        assert path.is_absolute()

    source_parts, target_parts = list(source.parts), list(target.parts)

    while source_parts[0] == target_parts[0]:
        source_parts, target_parts = source_parts[1:], target_parts[1:]

    if len(source_parts) >= len(target_parts):
        while source_parts:
            source_parts.pop()
            target_parts.insert(0, "..")
        return Path(SEPARATOR.join(target_parts))
    else:
        raise NotImplementedError
