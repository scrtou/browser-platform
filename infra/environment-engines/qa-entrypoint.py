#!/usr/bin/env python3
"""QA candidate boot: same Camoufox validation, before a report exists."""
import os
import sys
sys.path.insert(0,'/usr/local/lib/browser-platform')
import environment
from display_config import configure
artifact=environment.load_artifact('/run/browser-platform/environment.json',os.environ['BROWSER_PLATFORM_ARTIFACT_SHA256'])
configure('camoufox',environment.automatic(artifact['spec']))
os.execv('/init',['/init'])
