import random
from pathlib import Path

from existance.constants import PASSWORD_CHARACTERS, SEPARATOR


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
