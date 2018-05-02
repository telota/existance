import random

from existance.constants import PASSWORD_CHARACTERS


def make_password_proposal(length: int = 32) -> str:
    result = ''
    while len(result) < length:
        result += random.choice(PASSWORD_CHARACTERS)
    return result
