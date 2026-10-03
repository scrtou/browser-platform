"""Select the verified window policy before the normal desktop starts."""
from pathlib import Path
import re

def configure(window_class,auto):
    if window_class not in ('chromium','firefox','camoufox'):raise ValueError('DISPLAY_CLASS_INVALID')
    # The packaged Chromix executable reports Chromium-browser, not chromium.
    # Match its actual WM_CLASS so the base wildcard cannot maximize fixed mode.
    actual_class='Chromium-browser' if window_class=='chromium' else window_class
    rule='<application class="'+actual_class+'" name="*"><position force="yes"><x>0</x><y>0</y></position><maximized>'+('yes' if auto else 'no')+'</maximized><decor>no</decor></application>'
    for p in (Path('/etc/xdg/openbox/rc.xml'),Path('/etc/xdg/openbox/rc.xml.bak')):
        if not p.exists():continue
        s=p.read_text()
        if s.count('</applications>')!=1:raise ValueError('DISPLAY_CONFIG_INVALID')
        for cls in {window_class,actual_class}:
            s=re.sub(r'<application class="'+re.escape(cls)+r'"(?: name="\*")?>.*?</application>','',s,flags=re.S)
        p.write_text(s.replace('</applications>',rule+'</applications>'))
