"""Scrub configured secrets from formatted logs, including exception tracebacks."""
import json
import logging
import os
import re


def redact(value):
    value = str(value)
    secrets = [os.getenv(name, '') for name in ('DATATRACE_PASSWORD', 'DATATRACE_DESKTOP_TOKEN', 'GOOGLE_SERVICE_ACCOUNT_JSON')]
    try:
        account = json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '{}'))
        secrets.extend([account.get('private_key', ''), account.get('private_key_id', '')])
    except (ValueError, TypeError):
        pass
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        value = value.replace(secret, '[redacted]').replace(secret.replace('\n', '\\n'), '[redacted]')
    return re.sub(r'-----BEGIN (?:RSA )?PRIVATE KEY-----.*?-----END (?:RSA )?PRIVATE KEY-----', '[redacted private key]', value, flags=re.S)


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def protect_logs(logger):
    for handler in logger.handlers:
        handler.setFormatter(RedactingFormatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))
