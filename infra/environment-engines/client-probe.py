#!/usr/bin/env python3
"""Run the synthetic display client and retain resource evidence on any exit."""
import json
from pathlib import Path
import runpy
import shutil

try:
    runpy.run_path(str(Path(__file__).with_name('check-dynamic-client.py')),run_name='__main__')
finally:
    values={}
    for name in ['memory.events','memory.peak','memory.max','cpu.stat','cpu.max','pids.events']:
        path=Path('/sys/fs/cgroup')/name
        if path.is_file():values[name]=path.read_text()
    disk=shutil.disk_usage('/tmp');values['tmp']={'total':disk.total,'used':disk.used,'free':disk.free}
    (Path('/qa-output')/'client-resources.json').write_text(json.dumps(values,indent=2)+'\n')
