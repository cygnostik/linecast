"""Exercise printable quit through the real native input/lifecycle path."""
import os
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX controlling terminal")
def test_native_q_exits_and_restores_terminal():
    import fcntl
    import pty
    import select
    import struct
    import termios

    master, slave = pty.openpty()
    keep = os.dup(slave)
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    original = termios.tcgetattr(keep)

    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(0, os.getpgrp())

    child = subprocess.Popen(
        [sys.executable, "-B", "-m", "linecast", "orrery"],
        stdin=slave, stdout=slave, stderr=slave,
        env=dict(os.environ, TERM="xterm-256color", LINECAST_COLOR="none"),
        preexec_fn=controlling_terminal,
    )
    os.close(slave)
    output = bytearray()
    sent = False
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            if not sent and b"\x1b[?1049h" in output:
                os.write(master, b"q")
                sent = True
            if child.poll() is not None:
                break
        assert sent, "native command never entered its live terminal"
        assert child.poll() == 0, "q must request a clean exit, not wait for a signal"
        assert termios.tcgetattr(keep) == original
        assert b"\x1b[?1049l" in output
        assert b"Traceback" not in output
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)
        os.close(keep)
        os.close(master)
