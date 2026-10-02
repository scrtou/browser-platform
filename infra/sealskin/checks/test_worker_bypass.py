import errno
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('worker_bypass', Path(__file__).with_name('worker-bypass.py'))
worker_bypass = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker_bypass)


class WorkerBypassTest(unittest.TestCase):
    def test_timeouts_and_peer_refusal_never_prove_isolation(self):
        for failure in (TimeoutError(), ConnectionRefusedError(errno.ECONNREFUSED, 'refused')):
            sockets = [Mock() for _ in range(4)]
            for conn in sockets:
                conn.connect.side_effect = failure
            with patch.object(worker_bypass.socket, 'socket', side_effect=sockets):
                result = worker_bypass.probe()
            self.assertFalse(any(value['blocked'] for value in result.values()))
            self.assertTrue(all(conn.close.called for conn in sockets))

    def test_local_rejections_are_distinguished_from_reachable_paths(self):
        sockets = [Mock() for _ in range(4)]
        sockets[0].connect.side_effect = OSError(errno.ENETUNREACH, 'no route')
        sockets[1].send.side_effect = OSError(errno.EPERM, 'denied')
        with patch.object(worker_bypass.socket, 'socket', side_effect=sockets):
            result = worker_bypass.probe()
        self.assertTrue(result['public_tls']['blocked'])
        self.assertTrue(result['docker_dns']['blocked'])
        self.assertFalse(result['public_dns']['blocked'])
        self.assertFalse(result['metadata']['blocked'])

    def test_dns_requests_are_complete_questions_even_when_server_times_out(self):
        sockets = [Mock() for _ in range(4)]
        sockets[1].recv.side_effect = TimeoutError()
        sockets[2].recv.side_effect = TimeoutError()
        with patch.object(worker_bypass.socket, 'socket', side_effect=sockets):
            result = worker_bypass.probe()
        for conn, name in ((sockets[1], 'docker_dns'), (sockets[2], 'public_dns')):
            packet = conn.send.call_args.args[0]
            _, flags, questions, answers, authority, additional = struct.unpack('!6H', packet[:12])
            self.assertEqual((flags, questions, answers, authority, additional), (0x100, 1, 0, 0, 0))
            pos, labels = 12, []
            while packet[pos]:
                count = packet[pos]
                labels.append(packet[pos + 1:pos + 1 + count].decode('ascii'))
                pos += count + 1
            self.assertEqual('.'.join(labels), 'example.com')
            self.assertEqual(struct.unpack('!HH', packet[pos + 1:]), (1, 1))
            self.assertEqual(result[name]['outcome'], 'timeout_unconfirmed')
            self.assertFalse(result[name]['blocked'])


if __name__ == '__main__':
    unittest.main()
