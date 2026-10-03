#!/usr/bin/env python3
"""QA-only CDP attachment. Never included in the Worker image or production app."""
import importlib.util
import sys
import os
import re
spec=importlib.util.spec_from_file_location('chromix_launcher','/usr/local/lib/browser-platform/chromix-launcher.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=m.arguments
extra=['--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222']
spki=os.environ.get('CHROMIX_QA_SPKI','')
if spki:
    assert re.fullmatch(r'[A-Za-z0-9+/]{43}=',spki)
    extra.append('--ignore-certificate-errors-spki-list='+spki)
def qa_arguments(*args):
    flags = original(*args)
    if os.environ.get('CHROMIX_QA_NATIVE_SCREEN') == '1':
        # Diagnostic only: bypass public-mode screen defaults, retain explicit
        # seeds and scalar defaults. This is not an accepted production persona.
        seed = args[1]
        flags = [v for v in flags if not v.startswith(('--fingerprint=', '--fingerprint-screen-'))]
        extra_seeds = ['--uxr-fingerprint-seed='+str(seed),
                       '--uxr-canvas-seed='+str(seed), '--uxr-audio-seed='+str(seed),
                       '--fingerprint-hardware-concurrency=8',
                       '--fingerprint-device-memory=8', '--fingerprint-storage-quota=102400']
        flags = flags[:-1] + extra_seeds + flags[-1:]
    if os.environ.get("CHROMIX_QA_NATIVE_DPI") == "1":
        flags = [v for v in flags if not v.startswith("--force-device-scale-factor=")]
    return flags[:-1] + extra + flags[-1:]
m.arguments=qa_arguments
if os.environ.get('CHROMIX_QA_NATIVE_SCREEN') == '1':
    # The QA runner bypasses the fixed entrypoint and removes desktop locks.
    # Satisfy the old launcher's local contract only inside this diagnostic
    # process; the parent /init and Xvfb retain their dynamic configuration.
    os.environ['SELKIES_MANUAL_WIDTH']='1280'
    os.environ['SELKIES_MANUAL_HEIGHT']='720'
sys.argv=['chromix-launcher.py','launch',os.environ.get('SEALSKIN_URL','about:blank')]
raise SystemExit(m.main())
