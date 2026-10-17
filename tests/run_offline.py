"""Run fixture tests without provider access, OS credentials or live state."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import sys
import tempfile
import unittest
import weakref


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SOCKETS = weakref.WeakSet()


def audit(event, args):
    if event in {'socket.bind', 'socket.connect'}:
        address = args[1]
        try:
            allowed = isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise RuntimeError('Offline tests forbid external network connections')
        if event == 'socket.bind':
            FIXTURE_SOCKETS.add(args[0])
        else:
            # Even localhost gateways/collectors are forbidden: clients may
            # connect only to servers bound by these fixtures in this process.
            ports = set()
            for server in list(FIXTURE_SOCKETS):
                try:
                    ports.add(server.getsockname()[1])
                except OSError:
                    pass
            if address[1] not in ports:
                raise RuntimeError('Offline tests allow only fixture-owned local servers')
    elif event == 'subprocess.Popen':
        # Current fixtures need only a Node process whose fetch is mocked. No
        # shell, collectors, keychain, curl, Git, service or calendar commands.
        if Path(os.fsdecode(args[0])).name != 'node':
            raise RuntimeError('Offline tests forbid non-fixture subprocesses')


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / 'scripts'))
    for key in list(os.environ):
        if key.startswith('HARMONICA_') or key in {'APIFY_TOKEN', 'APIFY_API_TOKEN', 'OPENAI_API_KEY'}:
            del os.environ[key]
    with tempfile.TemporaryDirectory(prefix='harmonica-tests-') as directory:
        os.environ.update(HARMONICA_OBSERVE_HOME=str(ROOT), HARMONICA_LLM_PROVIDER='disabled',
                          HARMONICA_COMMUNITY_STATE=str(Path(directory) / 'community'),
                          HARMONICA_STATE_DIR=str(Path(directory) / 'llm'))
        sys.addaudithook(audit)
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
        return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
