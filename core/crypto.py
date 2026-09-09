"""Encrypted storage for server credentials.

A server connection never holds a secret value. Its env/headers keep a
``${secret:NAME}`` reference, the value lives encrypted in the secrets table,
and it is decrypted only for the moment a connection is actually made.
"""
import os
import re
from pathlib import Path

from cryptography.fernet import Fernet

SECRET_REF_PATTERN = re.compile(r"\$\{secret:([A-Za-z0-9_.\-]+)\}")

# Kept in the user's home directory rather than beside the database: the
# project's .gitignore covers *.sqlite3 but nothing that would match a key
# file, and a key inside the repo is one `git add -A` away from being pushed.
DEFAULT_KEY_PATH = Path.home() / ".ai-assistant" / "secret.key"

MASK = "***"


def secret_ref(name: str) -> str:
    """The reference that goes into a server's env/headers in place of a
    value."""
    return "${secret:" + name + "}"


def load_key(path=DEFAULT_KEY_PATH) -> bytes:
    """Reads the encryption key, generating it on first use.

    The file is created with 0600 from the start rather than chmod'ed
    afterwards, so it is never briefly readable by other users.
    """
    path = Path(path)
    if path.exists():
        return path.read_bytes().strip()

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = Fernet.generate_key()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process won the race; its key is the one that counts.
        return path.read_bytes().strip()
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    return key


class SecretBox:
    """Encrypts and decrypts secret values with a key kept outside the
    database, so a copy of the .sqlite3 file on its own reveals nothing."""

    def __init__(self, key: bytes | None = None):
        self._fernet = Fernet(key or load_key())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")


def referenced_names(value) -> set[str]:
    """Every secret name referenced anywhere inside a string, list or dict."""
    found = set()
    if isinstance(value, str):
        found.update(SECRET_REF_PATTERN.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            found |= referenced_names(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= referenced_names(item)
    return found


def substitute(value, lookup):
    """Replaces every ``${secret:NAME}`` using `lookup(name)`, recursing into
    lists and dicts.

    Returns the substituted copy plus the set of values that were filled in,
    so the caller can scrub them out of anything it later stores or logs. A
    value with no reference in it is returned untouched, which is what keeps
    servers configured before this existed working unchanged.
    """
    used = set()

    def _walk(node):
        if isinstance(node, str):
            def replace(match):
                resolved = lookup(match.group(1))
                if resolved is None:
                    return match.group(0)
                used.add(resolved)
                return resolved
            return SECRET_REF_PATTERN.sub(replace, node)
        if isinstance(node, dict):
            return {key: _walk(item) for key, item in node.items()}
        if isinstance(node, (list, tuple)):
            return [_walk(item) for item in node]
        return node

    return _walk(value), used


def scrub(text: str, values) -> str:
    """Removes secret values from text that is about to be stored or shown -
    a crashing server can echo its own environment into stderr."""
    if not text:
        return text
    for value in values:
        if value:
            text = text.replace(value, MASK)
    return text