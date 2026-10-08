"""Local browser connections, encrypted for the current Windows account."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse


ENVIRONMENT = {
    'spreadsheetId': 'DATATRACE_SPREADSHEET_ID',
    'fullTrackerTitle': 'DATATRACE_FULL_TRACKER',
    'remainingTrackerTitle': 'DATATRACE_REMAINING_TRACKER',
    'queueUrl': 'DATATRACE_QUEUE_URL',
    'username': 'DATATRACE_USERNAME',
    'password': 'DATATRACE_PASSWORD',
    'serviceAccount': 'GOOGLE_SERVICE_ACCOUNT_JSON',
}


def protect(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Saving browser connections requires Windows credential encryption.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    method = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        operation = 'unlock' if decrypt else 'encrypt'
        raise ValueError(f'Windows could not {operation} the saved connections. '
                         'Start the local server with start-local.bat under the Windows account '
                         'that saved these settings, then retry.')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def load_environment(directory):
    path = Path(directory) / 'settings.vault.browser'
    if path.exists():
        settings = json.loads(protect(path.read_bytes(), decrypt=True))
        for field, variable in ENVIRONMENT.items():
            if field in settings:
                os.environ[variable] = settings[field]


def service_account(raw):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 65536:
        raise ValueError('Choose a service-account JSON file smaller than 64 KB.')
    try:
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get('type') != 'service_account'
                or not re.fullmatch(r'[^\s@]+@[^\s@]+\.gserviceaccount\.com', value.get('client_email', ''))
                or value.get('token_uri') != 'https://oauth2.googleapis.com/token'
                or not value.get('project_id')):
            raise ValueError()
        from google.oauth2.service_account import Credentials
        Credentials.from_service_account_info(value)
    except Exception:
        raise ValueError('Choose a valid Google service-account JSON key using Google\'s official token endpoint.') from None
    return json.dumps(value)


def current(config):
    value = {field: os.environ.get(variable, '') for field, variable in ENVIRONMENT.items()}
    value.update(spreadsheetId=config.SPREADSHEET_ID, fullTrackerTitle=config.FULL_TRACKER_TITLE,
                 remainingTrackerTitle=config.REMAINING_TRACKER_TITLE, queueUrl=config.QUEUE_URL)
    raw = value['serviceAccount'] or 'service_account.json'
    if not raw.lstrip().startswith('{'):
        path = Path(raw)
        try:
            raw = (path if path.is_absolute() else config.BASE_DIR / path).read_text(encoding='utf-8-sig')
        except OSError:
            raw = ''
    value['serviceAccount'] = raw
    return value


def public(settings):
    result = {key: value for key, value in settings.items() if key not in ('password', 'serviceAccount')}
    try:
        account = json.loads(settings['serviceAccount'])
        email = account.get('client_email', '') if isinstance(account, dict) else ''
    except (ValueError, TypeError):
        email = ''
    return dict(result, passwordSet=bool(settings['password']), serviceAccountEmail=email,
                googleConfigured=bool(settings['spreadsheetId'] and email))


def validate(payload, previous):
    if not isinstance(payload, dict):
        raise ValueError('Settings must be an object.')
    settings = dict(previous)
    for field in ENVIRONMENT:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str) or len(value) > (65536 if field == 'serviceAccount' else 4096):
            raise ValueError(f'Invalid {field}.')
        if field in ('password', 'serviceAccount'):
            if value:
                settings[field] = service_account(value) if field == 'serviceAccount' else value
        else:
            settings[field] = value.strip()
    match = re.fullmatch(r'https://docs\.google\.com/spreadsheets/d/([\w-]+)(?:[/?#].*)?', settings['spreadsheetId'])
    if match:
        settings['spreadsheetId'] = match[1]
    if not re.fullmatch(r'[a-zA-Z0-9_-]{20,150}', settings['spreadsheetId']):
        raise ValueError('Enter a valid Google Sheets URL or spreadsheet ID.')
    for field in ('fullTrackerTitle', 'remainingTrackerTitle'):
        value = settings[field]
        if not value or len(value) > 100 or re.search(r'[\[\]:*?/\\]', value):
            raise ValueError('Tracker tab names must be valid and no longer than 100 characters.')
    if settings['fullTrackerTitle'] == settings['remainingTrackerTitle']:
        raise ValueError('The two tracker tab names must be different.')
    url = urlparse(settings['queueUrl'])
    if (url.scheme != 'https' or url.netloc != 'tv.datatracetitle.com'
            or url.username or url.password):
        raise ValueError('Use an HTTPS queue URL on tv.datatracetitle.com.')
    if settings['serviceAccount']:
        settings['serviceAccount'] = service_account(settings['serviceAccount'])
    return settings


def save(directory, settings):
    directory = Path(directory)
    raw = json.dumps(settings).encode('utf-8')
    encrypted = protect(raw)
    if protect(encrypted, decrypt=True) != raw:
        raise ValueError('Windows could not verify the encrypted settings.')
    fd, temporary = tempfile.mkstemp(prefix='settings.vault.', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / 'settings.vault.browser')
    finally:
        Path(temporary).unlink(missing_ok=True)
    for field, variable in ENVIRONMENT.items():
        os.environ[variable] = settings[field]
