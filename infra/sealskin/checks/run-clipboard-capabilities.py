#!/usr/bin/env python3
"""Container-side runner: a private display and clipboard, never the host desktop."""
import os
from pathlib import Path
import subprocess
import time

runtime = Path('/tmp/clipboard-capability-runtime')
runtime.mkdir(mode=0o700)
environment = {**os.environ, 'DISPLAY': ':99', 'XDG_RUNTIME_DIR': str(runtime)}
display = subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1280x720x24', '-nolisten', 'tcp'],
                           env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
manager = None
try:
    for _ in range(50):
        if Path('/tmp/.X11-unix/X99').exists():
            break
        if display.poll() is not None:
            raise RuntimeError('isolated display failed')
        time.sleep(.1)
    manager = subprocess.Popen(['openbox', '--sm-disable'], env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run(['/electron/electron', '--no-sandbox', '/checks/clipboard-capabilities.cjs'],
                            env=environment, capture_output=True, text=True, timeout=45)
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr)
    raise SystemExit(result.returncode)
finally:
    for process in (manager, display):
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
