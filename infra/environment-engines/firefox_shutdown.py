#!/usr/bin/env python3
"""Reuse the image's reviewed X11 close protocol with the native Firefox lock."""
import fcntl
import importlib.util
import os
from pathlib import Path
s=importlib.util.spec_from_file_location('firefox_x11',Path(__file__).with_name('firefox_x11_shutdown.py'))
x11=importlib.util.module_from_spec(s);s.loader.exec_module(x11)
x11.LAUNCHER=b'/usr/local/lib/browser-platform/firefox-launcher.py'
def home_released():
    try:fd=os.open('/config/.firefox/worker.lock',os.O_RDWR|os.O_NOFOLLOW)
    except FileNotFoundError:return True
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
    except BlockingIOError:return False
    finally:os.close(fd)
x11.home_released=home_released
if __name__=='__main__':raise SystemExit(x11.main())
