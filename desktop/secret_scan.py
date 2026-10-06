"""Fail closed on recognizable credentials without printing their values."""
from pathlib import Path
import re
import subprocess

PATTERNS = (
    ('private key', re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*[A-Za-z0-9+/=\s]{128,}-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('GitHub access token', re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b')),
)


def check_bytes(name, data):
    normalized = data.replace(b'\\n', b'\n').replace(b'\\r', b'\r')
    for kind, pattern in PATTERNS:
        if pattern.search(normalized):
            raise ValueError(f'Release blocked: recognizable {kind} in {name}. Secret value withheld.')


def main():
    root = Path(__file__).resolve().parent.parent
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root).decode().split('\0')
    checked = 0
    for name in sorted(set(paths) - {''}):
        file = root / name
        if file.is_file() and not file.is_symlink():
            check_bytes(name, file.read_bytes())
            checked += 1
    print(f'Credential-format scan passed: {checked} source files. This supplements account-key rotation and review.')


if __name__ == '__main__':
    main()
