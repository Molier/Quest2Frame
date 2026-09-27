# SPDX-License-Identifier: GPL-3.0-only
"""Short-lived Frame sleep inhibitor with a disconnect/crash watchdog."""
import shlex
import threading


class FrameAwake:
    # Remote read timeout releases the lock even if an SSH connection becomes
    # half-open. No power settings, services, or privileged files are changed.
    command = (
        'systemd-inhibit --what=idle:sleep --mode=block --who=Quest2Frame '
        '--why=' + shlex.quote('Wireless game installation') + ' bash -c ' +
        shlex.quote('printf "Q2F_AWAKE_READY\\n"; '
                    'while IFS= read -r -t 45 pulse; do '
                    '[ "$pulse" = Q2F_KEEP_AWAKE ] || break; done')
    )

    def __init__(self, client, log):
        self.client=client;self.log=log;self.channel=None
        self.streams=();self.stop=threading.Event();self.thread=None
        self.failed=threading.Event()

    def __enter__(self):
        try:
            self.streams=self.client.exec_command(self.command,timeout=10)
            _,out,_=self.streams;self.channel=out.channel
            if out.readline().strip()!='Q2F_AWAKE_READY':
                raise RuntimeError('Frame refused the sleep inhibitor. Check systemd-inhibit permissions on Frame; no wireless installation was started.')
            self.check()
            self.thread=threading.Thread(target=self._heartbeat,daemon=True)
            self.thread.start()
            self.log('Frame keep-awake active for wireless installation (idle/suspend blocked).')
            return self
        except Exception:
            self.close()
            raise

    def check(self):
        if self.failed.is_set() or self.channel is None or self.channel.closed or self.channel.exit_status_ready():
            raise RuntimeError('Frame keep-awake connection was lost. Wireless installation stopped; reconnect Frame and retry.')

    def _heartbeat(self):
        while not self.stop.wait(10):
            try:
                self.check()
                self.channel.sendall(b'Q2F_KEEP_AWAKE\n')
            except Exception:
                self.failed.set();return

    def close(self):
        self.stop.set()
        if self.channel is not None:
            try:self.channel.shutdown_write()
            except Exception:pass
            try:self.channel.close()
            except Exception:pass
        for stream in self.streams:
            try:stream.close()
            except Exception:pass
        if self.thread is not None:self.thread.join(timeout=.2)

    def __exit__(self, *exc):
        self.close()
        self.log('Frame keep-awake released; normal power management resumes (within 45 seconds if the connection was lost).')
