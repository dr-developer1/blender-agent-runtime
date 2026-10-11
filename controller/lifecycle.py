"""Shared isolated Blender launch and headless test facilities."""
import os
from pathlib import Path
import subprocess
import tempfile


class BlenderProcessError(RuntimeError):
    """Launch, lifecycle or transport failure (not a runtime command error)."""


def isolated_environment(directory):
    env = os.environ.copy()
    for name in ('BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS', 'BLENDER_USER_DATAFILES'):
        location = Path(directory) / name.lower()
        location.mkdir()
        env[name] = str(location)
    return env


def blender_command(executable, script):
    return [executable, '--background', '--factory-startup', '--disable-autoexec',
            '--threads', '1', '--python-exit-code', '1', '--python', str(script)]


def run_headless(script, *, executable='blender', timeout=60):
    """Run a trusted local test script in a fresh Blender; preserve nonzero status."""
    script = Path(script).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='bar-test-') as directory:
        try:
            return subprocess.run(blender_command(executable, script),
                                  env=isolated_environment(directory), cwd=directory,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BlenderProcessError(f'Headless Blender test failed: {exc}') from exc
