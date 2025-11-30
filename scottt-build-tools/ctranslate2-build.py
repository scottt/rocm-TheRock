#!/usr/bin/env python

import os
import sys
import subprocess
import time
from pathlib import Path
import pprint

def gpu_target_read():
    with open(os.path.expanduser('~/THEROCK-GPU-TARGET')) as f:
        gpu_target = f.read().strip()
    print(f'gpu_target: {gpu_target}')
    if gpu_target == '':
        raise RuntimeError('Try:\n\techo gfx1151 > $HOME/THEROCK-GPU-TARGET\n')
    return gpu_target

def command_output(args):
    try:
        r = subprocess.run(args,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"Error output: {e.stderr}")
        raise
    return r.stdout

def program_name():
    return os.path.basename(sys.argv[0])

# --- Configuration ---
gpu_target = gpu_target_read()

source_dir = Path('/w/CTranslate2-rocm/')
build_dir = Path('/o/CTranslate2-rocm/build')
venv_dir = build_dir / '../venv'
venv_dir = venv_dir.resolve()

caches_dir = Path("/cache")
ccache_dir = caches_dir / "ccache"
pip_cache_dir = caches_dir / "pip"

env = {}
env['PYTORCH_ROCM_ARCH'] = gpu_target

env['HIPCXX'] = os.path.join(command_output(['hipconfig', '-l']), 'clang')

if sys.platform == 'win32':
    env['CC'] = env['HIPCXX']
    env['CXX'] = env['HIPCXX']
else:
    env['CC'] = 'clang'
    env['CXX'] = 'clang++'

env['HIP_PATH'] = command_output(['hipconfig', '-R'])
env['ROCM_PATH'] = env['HIP_PATH']
env['HIP_PLATFORM'] = command_output(['hipconfig', '--platform'])

# The "CTRANSLATE2_ROOT" envvar is used by CTranslate2-rocm/python/setup.py
# to allow us to specify the prefix for the CTranslate2 headers and library
# during `python setup.py bdist_wheel`
env['CTRANSLATE2_ROOT'] = str(venv_dir)

source_dir = source_dir.resolve(strict=True)
build_dir = build_dir.resolve()
if not build_dir.exists():
    build_dir.mkdir(parents=True, exist_ok=True)

CCACHE_EXECUTABLE = "ccache"

CMAKE_BUILD_OPTIONS = [
    ('WITH_MKL', 'OFF'),
    ('WITH_HIP', 'ON'),
    ('CMAKE_HIP_ARCHITECTURES', gpu_target),
    ('BUILD_TESTS', 'ON'),
    ('WITH_CUDNN', 'ON'),
    ('OPENMP_RUNTIME', 'NONE'),
    # Install in `lib/` not `lib64/` so `bdist_wheel` can find the library
    ("CMAKE_INSTALL_LIBDIR", "lib"),
    # CMake hip compiler test could erroneously fail on Windows
    ("CMAKE_HIP_COMPILER_FORCED", "ON"),
]

# --- Helper functions ---

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

def cmake_cli_cache_variable_list_from_build_options(opts):
    return [ '-D%s=%s' % x for x in opts ]

# --- Setup ---
print(f"--- Configuration ---")
print(f"Source Directory: {source_dir}")
print(f"Cache Directory: {caches_dir}")
print(f"Script Arguments: {sys.argv[1:]}")
print(f"---------------------")

print(f"Ensuring directories exist...")
ccache_dir.mkdir(parents=True, exist_ok=True)
pip_cache_dir.mkdir(parents=True, exist_ok=True)

print("Setting environment variables...")
env['CCACHE_DIR'] = str(ccache_dir.resolve())
env['PIP_CACHE_DIR'] = str(pip_cache_dir.resolve())

# Don't use ccache on Windows due to "duplicate symbols" bug
use_ccache = (sys.platform != 'win32')
if use_ccache:
    print(f"Configuring CMake to use ccache ('{CCACHE_EXECUTABLE}')...")
    env['CMAKE_C_COMPILER_LAUNCHER'] = CCACHE_EXECUTABLE
    env['CMAKE_CXX_COMPILER_LAUNCHER'] = CCACHE_EXECUTABLE
else:
    print("Skipping ccache configuration.")
    env.pop('CMAKE_C_COMPILER_LAUNCHER', None)
    env.pop('CMAKE_CXX_COMPILER_LAUNCHER', None)

print('CMake build options:')
pprint.pprint(CMAKE_BUILD_OPTIONS)

print('Environment variables changed:')
pprint.pprint(env)
os.environ.update(env)

print(f"CCACHE_DIR: {os.environ.get('CCACHE_DIR')}")
print(f"PIP_CACHE_DIR: {os.environ.get('PIP_CACHE_DIR')}")
print(f"CMAKE_C_COMPILER_LAUNCHER: {os.environ.get('CMAKE_C_COMPILER_LAUNCHER')}")
print(f"CMAKE_CXX_COMPILER_LAUNCHER: {os.environ.get('CMAKE_CXX_COMPILER_LAUNCHER')}")

# --- Build Steps ---

# Configure
cmd = [
    "cmake",
    "-S", source_dir,
    "-B", build_dir,
    "-G", "Ninja",
    #'--trace-expand',
] + cmake_cli_cache_variable_list_from_build_options(CMAKE_BUILD_OPTIONS)
run_command(cmd)

# Build
cmd = [
    "cmake",
    "--build", build_dir,
]
cpu_count = os.cpu_count()
if cpu_count and cpu_count > 1:
     cmd.extend(["--", f"-j{max(1, cpu_count - 1)}"]) # Pass '-jN' to underlying Ninja
     print(f"Using parallel build flag: -j{max(1, cpu_count - 1)}")
run_command(cmd)

# Install

cmd = [
    "cmake",
    "--install", build_dir,
    "--prefix", venv_dir,
]
run_command(cmd)

# Python version used to create venv
python_ver = '%d.%d' % (sys.version_info.major, sys.version_info.minor)

if True:
    cmd = [
        "uv",
        "venv",
        "--python", python_ver,
        "--allow-existing",
        str(venv_dir),
    ]
    run_command(cmd)

cmd = [
    "uv",
    "pip",
    "install", "-r", str(source_dir / "python" / "install_requirements.txt"),
    "--python", str(venv_dir),
]
run_command(cmd)

venv_bin_dir = venv_dir / Path('bin')
venv_python_bin = venv_dir / Path('bin') / Path('python')
if sys.platform == 'win32':
    venv_bin_dir = venv_dir / Path('Scripts')
    venv_python_bin = venv_dir / Path('Scripts') / Path('python.exe')

# Build Python Wheel
cmd = [
    venv_python_bin,
    "setup.py",
    "bdist_wheel",
]
run_command(cmd, cwd=source_dir / "python")

print("\n%s completed successfully." % (program_name(),))
