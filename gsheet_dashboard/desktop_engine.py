"""Packaged desktop entry point: authenticated loopback service on an OS-assigned port."""
import json
import os
import sys
import threading
from pathlib import Path

# Explicit development-only dependency path for embedded Python build environments.
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if os.environ.get('DATATRACE_DEV_DEPS'):
        sys.path.insert(0, os.environ['DATATRACE_DEV_DEPS'])


def process_job():
    """Windows kills browser descendants if this engine exits or crashes."""
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    class BASIC(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
    class EXTENDED(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise OSError(ctypes.get_last_error(), 'Cannot establish desktop process cleanup')
    return handle


def main():
    if not os.environ.get('DATATRACE_DESKTOP_TOKEN') or not os.environ.get('DATATRACE_DATA_DIR'):
        raise RuntimeError('Launch this engine through Tv Tracker.')
    job_handle = process_job()
    from waitress import create_server
    from server import create_app
    shutdown = threading.Event()
    # A locked credential vault must not consume scheduled captures or retry cloud work.
    app = create_app(start_scheduler=os.environ.get('DATATRACE_CONNECTION_RECOVERY') != '1')
    app.config['DESKTOP_SHUTDOWN'] = shutdown.set
    server = create_server(app, host='127.0.0.1', port=0, threads=6)
    threading.Thread(target=server.run, daemon=True).start()
    print('DATATRACE_READY ' + json.dumps({'port': server.effective_port}), flush=True)
    shutdown.wait()
    app.extensions['stop_scheduler'].set()
    server.close()
    # Keep the native Job Object alive for the full engine lifetime.
    return job_handle


if __name__ == '__main__':
    main()
