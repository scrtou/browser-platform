import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

from keyboard_subprocess import communicate


class KeyboardProcessTest(unittest.IsolatedAsyncioTestCase):
    async def child(self, directory, delay):
        return await asyncio.create_subprocess_exec(
            sys.executable, '-c',
            'import time,sys;from pathlib import Path;'
            'time.sleep(float(sys.argv[1]));Path(sys.argv[2]).write_text("injected")',
            str(delay), str(Path(directory) / 'output'),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

    async def test_slow_input_finishes_before_successor(self):
        with tempfile.TemporaryDirectory() as directory:
            process = await self.child(directory, .65)
            await communicate(process)
            self.assertEqual(process.returncode, 0)
            self.assertEqual((Path(directory) / 'output').read_text(), 'injected')

    async def test_timeout_reaps_before_return_and_prevents_late_input(self):
        with tempfile.TemporaryDirectory() as directory:
            process = await self.child(directory, .3)
            with self.assertRaises(asyncio.TimeoutError):
                await communicate(process, timeout=.03)
            self.assertIsNotNone(process.returncode)
            await asyncio.sleep(.35)
            self.assertFalse((Path(directory) / 'output').exists())

    async def test_cancel_reaps_before_propagating(self):
        with tempfile.TemporaryDirectory() as directory:
            process = await self.child(directory, .3)
            task = asyncio.create_task(communicate(process))
            await asyncio.sleep(.03)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertIsNotNone(process.returncode)
            await asyncio.sleep(.35)
            self.assertFalse((Path(directory) / 'output').exists())

    async def test_pipe_output_is_drained(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-c', 'import sys;sys.stdout.write("x"*200000)',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await communicate(process)
        self.assertEqual(stdout, b'x' * 200000)
        self.assertEqual(stderr, b'')

    async def test_exit_failure_remains_visible(self):
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', 'raise SystemExit(7)')
        await communicate(process)
        self.assertEqual(process.returncode, 7)


class InstallerTest(unittest.TestCase):
    def test_unknown_upstream_rejected(self):
        spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-keyboard-order.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(ValueError, 'SELKIES_INPUT_BASE_MISMATCH'):
            module.patch(b'unknown upstream')


if __name__ == '__main__':
    unittest.main()
