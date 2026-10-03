#!/usr/bin/env python3
"""Exercise original and patched pinned on_message using real delayed children."""
import argparse
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types

from keyboard_subprocess import communicate


def handler_class(source, subprocess):
    tree = ast.parse(source)
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'on_message')
    namespace = {'asyncio': asyncio, 'subprocess': subprocess,
                 'keyboard_communicate': communicate,
                 'logger_webrtc_input': types.SimpleNamespace(warning=lambda *_: None)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<pinned-on-message>', 'exec'), namespace)
    return type('Handler', (), {'on_message': namespace['on_message']})


async def run(source, fail=False):
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'text'
        output.write_text('')
        async def launch(*args, **kwargs):
            assert args == ('xdotool', 'type', '-')
            script = ('raise SystemExit(7)' if fail else
                      'import time,sys;time.sleep(.65);open(sys.argv[1],"a").write("-")')
            return await asyncio.create_subprocess_exec(sys.executable, '-c', script, str(output), **kwargs)
        subprocess = types.SimpleNamespace(create_subprocess_exec=launch, PIPE=asyncio.subprocess.PIPE)
        handler = handler_class(source, subprocess)()
        handler.is_wayland = False
        handler.active_modifiers = set()
        handler.MODIFIER_KEYSYMS = set()
        handler.atomically_typed_keys = set()
        releases = []
        async def key(keysym, down):
            if down:
                with output.open('a') as f:
                    f.write(chr(keysym))
            else:
                releases.append(keysym)
        handler.send_x11_keypress = key
        for character in 'resize-check':
            await handler.on_message('kd,' + str(ord(character)))
            await handler.on_message('ku,' + str(ord(character)))
        await asyncio.sleep(.3)
        return output.read_text(), releases


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-keyboard-order.py'))
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    raw = args.source.read_bytes()
    patched = installer.patch(raw)
    before, _ = await run(raw)
    after, _ = await run(patched)
    failed, released = await run(patched, fail=True)
    assert before == 'resizecheck-', before
    assert after == 'resize-check', after
    assert failed == 'resizecheck' and ord('-') in released
    print(json.dumps({'result': 'PASS', 'old_failure_reproduced': True,
                      'patched_delayed_input_ordered': True, 'failed_text_keyup_preserved': True}))


if __name__ == '__main__':
    asyncio.run(main())
