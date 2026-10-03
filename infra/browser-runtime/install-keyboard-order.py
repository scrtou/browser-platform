#!/usr/bin/env python3
"""Patch the pinned Selkies X11 input subprocess lifecycle."""
import hashlib
from pathlib import Path
import shutil

ASSET = Path('/lsiopy/lib/python3.14/site-packages/selkies/input_handler.py')
BASE_SHA256 = '00fb38a48c0249d54d1bae0e27d093b5aeab62a49ea8542e21edfc4e86a76779'


def patch(raw):
    if hashlib.sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError('SELKIES_INPUT_BASE_MISMATCH')
    source = raw.decode()
    replacements = [
        ('from asyncio import subprocess',
         'from asyncio import subprocess\nfrom .keyboard_subprocess import communicate as keyboard_communicate', 1),
        ('await asyncio.wait_for(process.communicate(), timeout=0.5)',
         'await keyboard_communicate(process)', 2),
        ('await asyncio.wait_for(process_key.communicate(), timeout=1.0)',
         'await keyboard_communicate(process_key)', 1),
        ('await asyncio.wait_for(process_type.communicate(), timeout=1.0)',
         'await keyboard_communicate(process_type)', 1),
        ('                            await self.on_message(f"co,end,{char_to_type}")\n'
         '                            self.atomically_typed_keys.add(keysym)',
         '                            if await self.on_message(f"co,end,{char_to_type}") is not False:\n'
         '                                self.atomically_typed_keys.add(keysym)', 1),
        ('                    await keyboard_communicate(process)\n'
         '            except Exception as e: logger_webrtc_input.warning(f"Error with co,end type: {e}")',
         '                    await keyboard_communicate(process)\n'
         '                    if process.returncode != 0:\n'
         '                        raise RuntimeError("KEYBOARD_INJECTION_FAILED")\n'
         '            except Exception:\n'
         '                logger_webrtc_input.warning("Keyboard text injection failed")\n'
         '                return False', 1),
    ]
    for old, new, count in replacements:
        if source.count(old) != count:
            raise ValueError('SELKIES_INPUT_ANCHOR_MISMATCH')
        source = source.replace(old, new)
    compile(source, str(ASSET), 'exec')
    return source.encode()


def main():
    raw = patch(ASSET.read_bytes())
    shutil.copy2(Path(__file__).with_name('keyboard_subprocess.py'), ASSET.with_name('keyboard_subprocess.py'))
    ASSET.write_bytes(raw)


if __name__ == '__main__':
    main()
