#!/usr/bin/env python3
"""Probe raw Worker paths without treating a timeout as proof of isolation."""
import errno
import json
import socket
import struct


def probe():
    query = struct.pack('!HHHHHH', 0x727f, 0x0100, 1, 0, 0, 0)
    query += b'\x07example\x03com\x00' + struct.pack('!HH', 1, 1)
    targets = [('public_tls', '1.1.1.1', 443, socket.SOCK_STREAM),
               ('docker_dns', '127.0.0.11', 53, socket.SOCK_DGRAM),
               ('public_dns', '1.1.1.1', 53, socket.SOCK_DGRAM),
               ('metadata', '169.254.169.254', 80, socket.SOCK_STREAM)]
    outcomes = {}
    for name, address, port, kind in targets:
        conn = socket.socket(socket.AF_INET, kind)
        conn.settimeout(2)
        result = {'blocked': False, 'stage': 'connect'}
        try:
            conn.connect((address, port))
            if kind == socket.SOCK_DGRAM:
                result['stage'] = 'send'
                conn.send(query)
                result['stage'] = 'receive'
                conn.recv(4096)
            result['outcome'] = 'connected_or_replied'
        except TimeoutError:
            result['outcome'] = 'timeout_unconfirmed'
        except OSError as error:
            # Refused connections and arbitrary errors can come from the peer;
            # only explicit local route/permission failures prove rejection here.
            result.update(outcome='os_error', error_code=errno.errorcode.get(error.errno, 'UNKNOWN'),
                          blocked=error.errno in (errno.EPERM, errno.EACCES, errno.ENETUNREACH, errno.EHOSTUNREACH))
        finally:
            conn.close()
        outcomes[name] = result
    return outcomes


if __name__ == '__main__':
    print(json.dumps(probe()))
