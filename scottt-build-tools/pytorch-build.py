#!/usr/bin/env python

import os
import sys
import subprocess
import time
from pathlib import Path

def gpu_target_read():
    with open(os.path.expanduser('~/THEROCK-GPU-TARGET')) as f:
        gpu_target = f.read().strip()
    print(f'gpu_target: {gpu_target}')
    if gpu_target == '':
        raise RuntimeError('Try:\n\techo gfx1151 > $HOME/THEROCK-GPU-TARGET\n')
    return gpu_target

# --- Configuration ---
gpu_target = gpu_target_read()

# We need to install `torch` in the virtual env so we need to create the venv and specify
# the python version used
PYTHON_VER = '3.13'

source_dir = Path('/w/torch')
build_dir = Path('/o/torch/build')
# NOTE: Python version of Triton wheel must match Python version used to build AOTriton

os.environ['AOTRITON_INSTALLED_PREFIX'] = f"/o/aotriton-{gpu_target}/build/install_dir"
os.environ['CMAKE_PREFIX_PATH'] = f"/o/r-{gpu_target}/build/dist/rocm"
os.environ['USE_KINETO'] = 'OFF'
os.environ['PYTORCH_ROCM_ARCH'] = gpu_target
os.environ['USE_ROCM'] = 'ON'
os.environ['BUILD_TEST'] = '0'
os.environ['USE_FLASH_ATTENTION'] = 'ON'
os.environ['USE_MEM_EFF_ATTENTION'] = 'ON'
if sys.platform == 'win32':
    os.environ['CC'] = 'clang-cl'
    os.environ['CXX'] = 'clang-cl'
os.environ['DISTUTILS_USE_SDK'] = '1'
USE_CMAKE = True

if not build_dir.exists():
    build_dir.mkdir(parents=True, exist_ok=True)

venv_dir = build_dir / '.venv'

CCACHE_EXECUTABLE = "ccache"

# --- Setup ---
caches_dir = Path("/caches")
ccache_dir = caches_dir / "ccache"
pip_cache_dir = caches_dir / "pip"

print(f"--- Configuration ---")
print(f"Source Directory: {source_dir}")
print(f"Cache Directory: {caches_dir}")
print(f"Script Arguments: {sys.argv[1:]}")
print(f"---------------------")

def should_change_caches_dir():
    return sys.platform == 'win32'

if should_change_caches_dir():
    print(f"Ensuring directories exist...")
    ccache_dir.mkdir(parents=True, exist_ok=True)
    pip_cache_dir.mkdir(parents=True, exist_ok=True)

print("Setting environment variables...")
if should_change_caches_dir():
    os.environ['CCACHE_DIR'] = str(ccache_dir.resolve())
    os.environ['PIP_CACHE_DIR'] = str(pip_cache_dir.resolve())

# Don't use ccache on Windows due to "duplicate symbols" bug
use_ccache = (sys.platform != 'win32')
if use_ccache:
    print(f"Configuring CMake to use ccache ('{CCACHE_EXECUTABLE}')...")
    os.environ['CMAKE_C_COMPILER_LAUNCHER'] = CCACHE_EXECUTABLE
    os.environ['CMAKE_CXX_COMPILER_LAUNCHER'] = CCACHE_EXECUTABLE
else:
    print("Skipping ccache configuration.")
    os.environ.pop('CMAKE_C_COMPILER_LAUNCHER', None)
    os.environ.pop('CMAKE_CXX_COMPILER_LAUNCHER', None)

print(f"CCACHE_DIR = {os.environ.get('CCACHE_DIR')}")
print(f"PIP_CACHE_DIR = {os.environ.get('PIP_CACHE_DIR')}")
print(f"CMAKE_C_COMPILER_LAUNCHER = {os.environ.get('CMAKE_C_COMPILER_LAUNCHER')}")
print(f"CMAKE_CXX_COMPILER_LAUNCHER = {os.environ.get('CMAKE_CXX_COMPILER_LAUNCHER')}")

# --- Helper function to run commands ---
def run_command(cmd_list, cwd=None):
    """Runs a command, prints it, times it, and checks for errors."""
    print(f"\n--- Executing: {' '.join(map(str, cmd_list))} ---", flush=True)
    start_time = time.monotonic()
    try:
        # Use shell=False (default) for better security and argument handling
        # check=True raises CalledProcessError on non-zero exit code (like set -e)
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

# --- Build Steps ---

# Pytorch:
# -- ROCM_PATH environment variable is not set and /opt/rocm does not exist.
# Building without ROCm support.
if os.environ.get('ROCM_PATH') is None:
    p_result = subprocess.run(['hipconfig', '--rocmpath'], capture_output=True, text=True, check=True)
    os.environ['ROCM_PATH'] =  p_result.stdout.strip()

if True:
    cmd = [
        "uv",
        "venv",
        "--python", PYTHON_VER,
        "--allow-existing",
        str(venv_dir),
    ]
    run_command(cmd)

cmd = [
    "uv",
    "pip",
    "install", "-r", str(source_dir / "requirements.txt"),
    "--python", str(venv_dir),
]
run_command(cmd)

venv_bin_dir = venv_dir / Path('bin')
venv_python_bin = venv_dir / Path('bin') / Path('python')
if sys.platform == 'win32':
    venv_bin_dir = venv_dir / Path('Scripts')
    venv_python_bin = venv_dir / Path('Scripts') / Path('python.exe')

if USE_CMAKE:
    cmd = [
        venv_python_bin,
        "setup.py",
        "build", "--cmake-only",
    ]
    run_command(cmd, cwd=source_dir)

    # os.environ['PATH'] = os.pathsep.join([str(venv_bin_dir), os.environ.get('PATH', '')])
    print('PATH:', os.environ['PATH'])
    cmd = [
        "cmake",
        #"--trace",
        "-GNinja",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DPython_EXECUTABLE={venv_python_bin}",
        f"-DPYTORCH_ROCM_ARCH={gpu_target}",
        "-DUSE_ROCM=ON",
        "-DUSE_KINETO=OFF",
        "-DUSE_FLASH_ATTENTION=ON",
        "-S", str(source_dir.resolve()),
        "-B", str(build_dir.resolve()),
    ]
    cmd.extend(sys.argv[1:]) # Add extra arguments from script call
    run_command(cmd)
    # sys.exit(17)

cmd = [
    venv_python_bin,
    "setup.py",
    "bdist_wheel",
]
run_command(cmd, cwd=source_dir)

print("\nBuild script completed successfully.")
