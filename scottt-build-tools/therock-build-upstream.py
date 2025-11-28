#!/usr/bin/env python

import os
import sys
import subprocess
import platform
import time
import signal
from pathlib import Path

def run_command(cmd_list, cwd=None):
    """Runs a command, prints it, times it, and checks for errors."""
    print(f"\n--- Executing: {' '.join(map(str, cmd_list))} ---", flush=True)
    start_time = time.monotonic()
    try:
        process = subprocess.run(cmd_list, cwd=cwd, check=True, text=True)
    except FileNotFoundError:
        print(f"ERROR: Command not found: {cmd_list[0]}. Is it installed and in PATH?", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Command failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    end_time = time.monotonic()
    print(f"--- Command finished successfully in {end_time - start_time:.2f} seconds ---", flush=True)
    return process

def gpu_target_read():
    with open(os.path.expanduser('~/THEROCK-GPU-TARGET')) as f:
        gpu_target = f.read().strip()
    print(f'gpu_target: {gpu_target}')
    if gpu_target == '':
        raise RuntimeError('Try:\n\techo gfx1151 > $HOME/THEROCK-GPU-TARGET\n')
    return gpu_target

def build(gpu_target):
    script_dir = Path(os.path.dirname(sys.argv[0]))
    fork_name = 'r'
    os.environ['THEROCK_OUTPUT_DIR'] = os.path.expanduser(f'/o/{fork_name}-{gpu_target}')
    os.environ['THEROCK_SOURCE_DIR'] = os.path.expanduser(f'/w/{fork_name}')
    os.environ['THEROCK_INTERACTIVE'] = '1'
        # "-DTHEROCK_ENABLE_ALL=ON",
        # "-DTHEROCK_RESET_FEATURES=ON",
    therock_build_cmd = [
        sys.executable,
        script_dir / 'therock-build.py',
        f"-DTHEROCK_AMDGPU_FAMILIES={gpu_target}",
        "-DTHEROCK_ENABLE_ALL=OFF",
        "-DTHEROCK_BUNDLE_SYSDEPS=ON",
        "-DTHEROCK_ENABLE_HOST_BLAS=ON",
        "-DTHEROCK_ENABLE_COMPILER=ON",
        "-DTHEROCK_ENABLE_HIPIFY=ON",
        "-DTHEROCK_ENABLE_HIP_RUNTIME=ON",
        "-DTHEROCK_ENABLE_PRIM=ON",
        "-DTHEROCK_ENABLE_BLAS=ON",
        "-DTHEROCK_ENABLE_RAND=ON",
        "-DTHEROCK_ENABLE_FFT=ON",
        "-DTHEROCK_BUILD_TESTING=ON",
        "-DTHEROCK_ENABLE_SPARSE=ON",
        "-DTHEROCK_ENABLE_SOLVER=ON",
        "-DTHEROCK_ENABLE_COMM_LIBS=OFF",
        "-DTHEROCK_ENABLE_RCCL=OFF",
        "-DTHEROCK_ENABLE_MIOPEN=ON",
        "-DTHEROCK_ENABLE_COMPOSABLE_KERNEL=ON",
    ]
    run_command(therock_build_cmd)

gpu_target = gpu_target_read()
build(gpu_target)
