"""Build the self-contained engine; run with the Python used for desktop dependencies."""
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
DEPS = ROOT / '.desktop-build' / 'deps'
if DEPS.is_dir():
    sys.path[:] = [str(DEPS)] + [entry for entry in sys.path if 'site-packages' not in entry and entry != str(DEPS)]
import PyInstaller.__main__

arguments = [
    str(ROOT / 'gsheet_dashboard' / 'desktop_engine.py'), '--name=datatrace-engine',
    '--onedir', '--console', '--noconfirm',
    f'--distpath={ROOT / ".desktop-build" / "backend"}',
    f'--workpath={ROOT / ".desktop-build" / "pyinstaller"}',
    f'--specpath={ROOT / ".desktop-build"}',
    f'--paths={ROOT / "gsheet_dashboard"}',
    f'--paths={DEPS}',
    f'--add-data={ROOT / "gsheet_dashboard" / "sync_config.json"};.',
    f'--add-data={ROOT / "gsheet_dashboard" / "remaining_products.json"};.',
    f'--add-data={ROOT / "gsheet_dashboard" / "frontend" / "dist"};frontend/dist',
    f'--add-data={ROOT / "gsheet_dashboard" / "status_colors.json"};.',
    f'--add-data={ROOT / "gsheet_dashboard" / "default_trackers"};default_trackers',
    '--collect-data=certifi', '--collect-data=tzdata',
]
for package in ('streamlit', 'plotly', 'statsmodels', 'matplotlib', 'scipy', 'IPython', 'pytest', 'tkinter', 'PIL', 'torch', 'sympy', 'pyarrow', 'numba', 'notebook'):
    arguments.append(f'--exclude-module={package}')
PyInstaller.__main__.run(arguments)

extractor = ROOT / '.desktop-build' / 'extractor'
extractor.mkdir(parents=True, exist_ok=True)
for filename in ('scrape_datatrace.js', 'browser_options.cjs', 'sync_config.json'):
    shutil.copy2(ROOT / 'gsheet_dashboard' / filename, extractor / filename)
for filename in ('package.json', 'package-lock.json'):
    shutil.copy2(ROOT / 'desktop' / 'extractor' / filename, extractor / filename)
shutil.copytree(ROOT / 'desktop' / 'extractor' / 'node_modules', extractor / 'node_modules', dirs_exist_ok=True)
print('Desktop engine and extraction dependencies are ready.')
