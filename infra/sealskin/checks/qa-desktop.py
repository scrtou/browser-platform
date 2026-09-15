"""Control the fixture in a labelled QA browser through its real X11 desktop.

The browser uses its normal launcher and frozen environment. Only the private
QA page evaluates expressions; no browser debugging service is opened.
"""
import importlib.util
import json
from pathlib import Path
import re
import time
import uuid
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location('qa_network', Path(__file__).resolve().parents[1] / 'lifecycle/check-network-live.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


class Desktop:
    def __init__(self, worker, fixture_origin=None):
        value = json.loads(network.docker('inspect', worker).stdout)[0]
        labels = value['Config'].get('Labels', {})
        if (labels.get('io.browser-platform.owner') != 'network-qa'
                or not labels.get('io.browser-platform.home', '').startswith('network-qa-')
                or not labels.get('io.browser-platform.scope')):
            raise ValueError('desktop checks require an explicitly labelled QA Home')
        self.worker = value['Id']
        self.fixture_origin = fixture_origin
        if fixture_origin is not None:
            parsed = urlsplit(fixture_origin)
            if (parsed.scheme != 'https' or parsed.port != 18443 or parsed.path or parsed.query or parsed.fragment
                    or parsed.username or parsed.password
                    or not re.fullmatch(r'(direct|upstream)-[a-f0-9]{16}\.dns-qa\.azhen\.de', parsed.hostname or '')):
                raise ValueError('only a scoped public QA fixture origin is allowed')

    def run(self, *command):
        return network.docker('exec', '--user', '1000', '-e', 'DISPLAY=:1', self.worker, *command).stdout

    def key(self, *keys):
        self.run('xdotool', 'key', '--clearmodifiers', *keys)

    def type(self, text):
        self.run('xdotool', 'type', '--clearmodifiers', '--delay', '0', '--', text)

    def title(self):
        return self.run('xdotool', 'getactivewindow', 'getwindowname').strip()

    def available_title(self):
        # Display HTTP readiness can precede the first X11 window after a
        # normal start/resume. Treat that interval as not ready, not a failure.
        value = network.docker('exec', '--user', '1000', '-e', 'DISPLAY=:1', self.worker,
            'xdotool', 'getactivewindow', 'getwindowname', check=False)
        return value.stdout.strip() if value.returncode == 0 else ''

    def navigate(self, url):
        parsed = urlsplit(url)
        public_fixture = (self.fixture_origin is not None and parsed.scheme + '://' + parsed.netloc == self.fixture_origin
                          and parsed.path == '/client' and not parsed.fragment
                          and re.fullmatch(r'nonce=[a-f0-9]{32}', parsed.query) is not None)
        if not (public_fixture or url.startswith(('https://entry.leak.qa.test/', 'http://entry.leak.qa.test/')) or url.startswith('file:///tmp/browser-platform-')):
            raise ValueError('only QA fixture navigation is allowed')
        network.wait(lambda: bool(self.available_title()), 'QA browser window', seconds=60)
        # A resumed browser can still be restoring the address bar after its
        # X11 window appears. Verify the exact text before submitting, so a
        # focus/selection race cannot turn a network test into a different URL.
        for attempt in range(3):
            self.key('ctrl+l')
            self.key('ctrl+a')
            self.type(url)
            self.key('ctrl+a')
            self.key('ctrl+c')
            deadline = time.monotonic() + 2
            copied = False
            while time.monotonic() < deadline:
                selection = network.docker('exec', '--user', '1000', '-e', 'DISPLAY=:1', self.worker,
                    'xclip', '-selection', 'clipboard', '-o', check=False)
                if selection.returncode == 0 and selection.stdout == url:
                    copied = True
                    break
                time.sleep(.1)
            if copied:
                break
            time.sleep(.2)
        else:
            raise RuntimeError('QA address bar did not contain the requested URL')
        self.key('Return')
        time.sleep(.7)
        network.wait(lambda: self.available_title().startswith(('Private browser network check', 'Browser Platform Client QA')),
                     'QA fixture navigation', seconds=25)
        window = self.run('xdotool', 'getactivewindow').strip()
        self.run('xdotool', 'mousemove', '--window', window, '30', '100', 'click', '1')

    def evaluate(self, expression):
        nonce = uuid.uuid4().hex
        self.key('F7')
        self.key('ctrl+a')
        self.type(json.dumps({'nonce': nonce, 'expression': expression}, ensure_ascii=True))
        self.key('F8')
        network.wait(lambda: self.title().startswith('BP-QA-EVALUATED:' + nonce), 'QA expression', seconds=30)
        self.key('ctrl+c')
        time.sleep(.1)
        value = json.loads(self.run('xclip', '-selection', 'clipboard', '-o'))
        if value.get('nonce') != nonce:
            raise RuntimeError('QA clipboard result does not belong to this operation')
        if 'error' in value:
            raise RuntimeError('QA fixture expression failed: ' + value['error'] + ': ' + value.get('message', ''))
        return value.get('value')
