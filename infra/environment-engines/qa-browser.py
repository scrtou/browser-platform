#!/usr/bin/env python3
"""QA-only debug attachment; never installed in a production image/app."""
import importlib.util
import json
from pathlib import Path
import sys
p=Path('/run/browser-platform/environment.json');spec=json.loads(p.read_bytes())
engine='camoufox' if '/camoufox-' in spec['schemaVersion'] else 'chromix' if '/chromix-' in spec['schemaVersion'] else 'firefox'
if engine=='camoufox':
    import os
    sys.path.insert(0,'/usr/local/lib/browser-platform')
    import environment
    artifact=environment.load_artifact(p,os.environ['BROWSER_PLATFORM_ARTIFACT_SHA256'])
    original_exec=os.execve
    def execute(path,args,env):original_exec(path,args[:-1]+['--remote-debugging-port=9222']+args[-1:],env)
    os.execve=execute
    environment.launch(artifact,['https://example.com/'])
    raise SystemExit(0)
sys.path.insert(0,'/usr/local/lib/browser-platform')
source=importlib.util.spec_from_file_location('launcher','/usr/local/lib/browser-platform/'+engine+'-launcher.py')
m=importlib.util.module_from_spec(source);source.loader.exec_module(m)
original=m.arguments
def arguments(*args):
    values=original(*args)
    extra=['--remote-debugging-port=9222']
    if engine=='chromix':extra+=['--remote-debugging-address=127.0.0.1']
    return values[:-1]+extra+values[-1:]
m.arguments=arguments
sys.argv=[engine,'launch','https://example.com/']
raise SystemExit(m.main())
