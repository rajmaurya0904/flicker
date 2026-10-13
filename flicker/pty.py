"""PTY session spawn utility."""

import os
import pty
import subprocess


def spawn_pty(cmd: list[str]) -> tuple[str, int]:
    """
    Spawn a child process in a pseudo-terminal and return its output and exit code.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments to execute.

    Returns
    -------
    tuple[str, int]
        The output captured from the child process's PTY and the exit code.
    """
    # Create a pipe for the PTY
    master_fd, slave_fd = pty.openpty()
    try:
        # Start the process with the slave end of the PTY as its stdin/stdout/stderr
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=False,  # Keep the PTY file descriptors open
        )
        # Close the slave end in the parent process; we only need the master
        os.close(slave_fd)

        # Read output from the master end until the process exits
        output = bytearray()
        while True:
            try:
                data = os.read(master_fd, 1024)
                if not data:
                    break
                output.extend(data)
            except OSError:
                break

        # Wait for the process to terminate
        exit_code = proc.wait()
        return output.decode(errors="replace"), exit_code
    finally:
        os.close(master_fd)