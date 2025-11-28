#!/usr/bin/env python

import os
import sys
import subprocess
import time
from pathlib import Path

LLVM_DIR = '/o/r-st/build/dist/rocm/lib/llvm'

def program_name():
    return os.path.basename(sys.argv[0])

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

AOTRITON_NOIMAGE_MODE = (program_name() == 'aotriton-noimage-build.py')

fork_name = 'aotriton'
os.environ['AOTRITON_SOURCE_DIR'] = f'/w/{fork_name}'
os.environ['AOTRITON_BUILD_DIR'] = f'/o/{fork_name}-{gpu_target}/build'

if sys.platform == 'win32':
    # Workaround cl.exe amd_hip_vector_types.h
    os.environ['CC'] = 'clang-cl'
    os.environ['CXX'] = 'clang-cl'

triton_wheel_path = None
if not AOTRITON_NOIMAGE_MODE and sys.platform == 'win32':
    triton_wheel_path = Path('/work/triton-lshqqytiger/python/dist/triton-3.3.0+gitf8727c94-cp313-cp313-win_amd64.whl')
    triton_wheel_path.resolve(strict=True)

source_dir = Path(os.environ['AOTRITON_SOURCE_DIR']).resolve(strict=True)
build_dir = Path(os.environ['AOTRITON_BUILD_DIR']).resolve()
if not build_dir.exists():
    build_dir.mkdir(parents=True, exist_ok=True)
venv_dir = build_dir / 'venv'

if sys.platform == 'win32':
    Python3_EXECUTABLE = None
    Python3_INCLUDE_DIR = None
    Python3_LIBRARY = None
else:
    # Python3_EXECUTABLE = str(venv_dir / "bin" / "python")
    Python3_EXECUTABLE = "/usr/bin/python"
    Python3_INCLUDE_DIR = "/usr/include/python3.13"
    Python3_LIBRARY = "/usr/lib64/libpython3.13.so"

CCACHE_EXECUTABLE = "ccache"

# --- Setup ---
caches_dir = Path("/caches")
ccache_dir = caches_dir / "ccache"
pip_cache_dir = caches_dir / "pip"

if sys.platform == 'win32':
    os.environ['PKG_CONFIG'] = 'C:/Strawberry/perl/bin/pkg-config.bat'
    os.environ['PKG_CONFIG_PATH'] = '/o/xz/lib/pkgconfig'

print(f"--- Configuration ---")
print(f"Source Directory: {source_dir}")
print(f"Cache Directory: {caches_dir}")
print(f"LLVM_SYSPATH: {os.environ.get('LLVM_SYSPATH')}")
print(f"LLVM_INCLUDE_DIRS: {os.environ.get('LLVM_INCLUDE_DIRS')}")
print(f"LLVM_LIBRARY_DIR: {os.environ.get('LLVM_LIBRARY_DIR')}")
print(f"PKG_CONFIG_DIR: {os.environ.get('PKG_CONFIG_DIR')}")
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

use_ccache = False
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
                                 #stdout=sys.stdout, stderr=sys.stderr) # Redirect streams directly
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

cmd = [
    "uv",
    "venv",
    "--python", PYTHON_VER,
    "--allow-existing",
    str(venv_dir),
]
run_command(cmd)

BUILD_PYTHON_BINDINGS = True

if not AOTRITON_NOIMAGE_MODE:
    # https://github.com/astral-sh/uv/issues/8721
    cmd = [
        "uv",
        "pip",
        "install", "torch",
        "--python", str(venv_dir),
    ]
    run_command(cmd)

use_aotriton_target_arch = True
build_aotriton_09 = False
if build_aotriton_09:
    if gpu_target == 'gfx1151':
        use_aotriton_target_arch = False
        TARGET_GPUS = 'Navi3.5'
    elif gpu_target == 'gfx1100':
        use_aotriton_target_arch = False
        TARGET_GPUS = 'Navi31'
    elif gpu_target == 'gfx1101':
        use_aotriton_target_arch = False
        TARGET_GPUS = 'Navi32'
    elif gpu_target == 'gfx1201':
        use_aotriton_target_arch = False
        TARGET_GPUS = 'RX9070XT'
    else:
        raise TypeError(f"Don't know GPU mapping for aotriton 0.9 for {gpu_target}")

cmd = [
    "cmake",
    #"--trace",
    "-GNinja",
    f"-DVENV_DIR={str(venv_dir)}",
    f"-DCMAKE_INSTALL_PREFIX={str((build_dir / 'install_dir').resolve())}",
	"-DCMAKE_BUILD_TYPE=Release",
	"-DAOTRITON_GPU_BUILD_TIMEOUT=0",
    # AOTRITON_NO_PYTHON must be OFF and AOTRITON_NAME_SUFFIX must be set to run the unit tests
	f"-DAOTRITON_NO_PYTHON={'ON' if BUILD_PYTHON_BINDINGS else 'OFF'}",
	"-DHIP_PLATFORM=amd",
    f"-DAOTRITON_NOIMAGE_MODE={'ON' if AOTRITON_NOIMAGE_MODE else 'OFF' }",
    "-S", str(source_dir.resolve()),
    "-B", str(build_dir.resolve()),
    #"--debug-find",
]


if use_aotriton_target_arch:
    cmd.extend([
        f"-DAOTRITON_TARGET_ARCH={gpu_target}"
    ])
else:
    if TARGET_GPUS is not None:
        cmd.extend([
            f"-DTARGET_GPUS={TARGET_GPUS}"
        ])

if BUILD_PYTHON_BINDINGS:
    if Python3_EXECUTABLE:
        cmd.extend([
            f"-DPython3_EXECUTABLE={Python3_EXECUTABLE}",
        ])
    if Python3_INCLUDE_DIR:
        cmd.extend([
            "-DPython3_INCLUDE_DIR={Python3_INCLUDE_DIR}",
        ])
        cmd.extend([
            "-DPython3_LIBRARY={Python3_LIBRARY}",
        ])

if triton_wheel_path is not None:
    cmd.append(f"-DINSTALL_TRITON_FROM_WHEEL={str(triton_wheel_path.resolve())}")

if sys.platform == 'win32':
    cmd.append('-Ddlfcn-win32_DIR=/o/dlfcn/share/dlfcn-win32')

cmd.extend(sys.argv[1:]) # Add extra arguments from script call
run_command(cmd)

if sys.platform == 'win32':
    # Set HIP_PATH to dir containing `bin/ld-lld.exe` for triton\backends\amd\compiler.py
    #   lld = Path(os.path.join( os.environ['HIP_PATH'] , 'bin', 'ld.lld.exe' ))
    os.environ['HIP_PATH'] = LLVM_DIR

cmd = [
    "ninja", "install"
]
if sys.platform == 'win32' and (not AOTRITON_NOIMAGE_MODE):
    cmd.extend(['-j', '1'])
else:
    cmd.extend(['-j', '100'])
run_command(cmd, cwd=build_dir)

print("\nBuild script completed successfully.")
