"""Terminal frame capture engine."""

import os
import pty
import time


def capture_frames(cmd: list[str], interval: float = 0.1) -> tuple[list[tuple[float, str]], int]:
    """
    Spawn a child process in a pseudo-terminal and capture timestamped frames of terminal output.

    Args:
        cmd: Command and arguments to execute.
        interval: Time interval between frame captures in seconds.

    Returns:
        A list of (timestamp, frame_buffer) tuples and the process exit code.
        frame_buffer is the accumulated terminal output up to that timestamp.
    """
    pid, fd = pty.fork()
    if pid == 0:
        # Child process
        os.execvp(cmd[0], cmd)
    else:
        # Parent process
        os.set_blocking(fd, False)
        frames: list[tuple[float, str]] = []
        buffer_parts: list[str] = []
        last_capture = time.time()
        child_exited = False
        child_status = 0
        while True:
            try:
                data = os.read(fd, 1024).decode()
                if not data:
                    # EOF
                    break
                buffer_parts.append(data)
            except BlockingIOError:
                # No data available
                pass
            except OSError:
                break

            # Check if child has exited
            try:
                pid_wait, status = os.waitpid(pid, os.WNOHANG)
                if pid_wait == pid:
                    child_exited = True
                    child_status = status
                    break
            except ChildProcessError:
                break

            # Capture frame if interval elapsed
            now = time.time()
            if now - last_capture >= interval:
                frames.append((now, ''.join(buffer_parts)))
                last_capture = now

            # Yield CPU to avoid busy loop
            time.sleep(0.001)

        # If child hasn't exited yet, wait for it
        if not child_exited:
            try:
                _, status = os.waitpid(pid, 0)
                child_exited = True
                child_status = status
            except ChildProcessError:
                pass

        # Final frame if there's remaining data and no frame captured recently
        now = time.time()
        if buffer_parts and (now - last_capture >= interval or not frames):
            frames.append((now, ''.join(buffer_parts)))

        # Get exit code
        if child_exited:
            if os.WIFEXITED(child_status):
                exit_code = os.WEXITSTATUS(child_status)
            else:
                exit_code = -1
        else:
            exit_code = -1

        return frames, exit_code