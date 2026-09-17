"""Exercise printable quit through the real native input/lifecycle path."""
import os
import subprocess
import sys
import textwrap
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
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(0, os.getpgrp())

    # BSD/macOS can invalidate the parent's slave descriptor after session
    # teardown. Measure restoration in the same live TTY, after the command
    # returns and before its process exits; still dispatch the real CLI.
    command = textwrap.dedent("""\
        import runpy, sys, termios
        original = termios.tcgetattr(0)
        sys.argv = ['linecast', 'orrery']
        code = 0
        try:
            runpy.run_module('linecast', run_name='__main__')
        except SystemExit as stopped:
            code = stopped.code or 0
        after = termios.tcgetattr(0)
        # XNU sets PENDIN when restoring ICANON: pending-input state, not
        # a changed mode. Compare every actual setting, excluding only that
        # kernel-generated bit on Darwin (xnu/bsd/kern/tty.c, ttioctl).
        if sys.platform == 'darwin':
            original[3] &= ~termios.PENDIN
            after[3] &= ~termios.PENDIN
        restored = after == original
        print('ORRERY_TTY_RESTORED=' + str(restored), flush=True)
        if not restored:
            print('ORRERY_TTY_DIFF=' + repr([
                (i, before, end) for i, (before, end)
                in enumerate(zip(original, after)) if before != end
            ]), flush=True)
        raise SystemExit(code)
    """)
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", command],
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
            readable = select.select([master], [], [], 0.05)[0]
            if readable:
                try:
                    chunk = os.read(master, 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                except OSError:
                    break
            if not sent and b"\x1b[?1049h" in output:
                os.write(master, b"q")
                sent = True
            if child.poll() is not None and not readable:
                break
        assert sent, "native command never entered its live terminal"
        assert child.wait(timeout=1) == 0, "q must request a clean exit"
        assert b"ORRERY_TTY_RESTORED=True" in output, bytes(output[-2400:])
        assert b"\x1b[?1049l" in output
        assert b"Traceback" not in output
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)
        os.close(master)
