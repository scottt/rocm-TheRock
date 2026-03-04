import os
import sys
import subprocess
import platform
import time
import signal
from pathlib import Path

# --- Configuration ---
output_base_dir = Path(os.environ['THEROCK_OUTPUT_DIR']).resolve()
source_dir = Path(os.environ['THEROCK_SOURCE_DIR']).resolve()

CCACHE_EXECUTABLE = "ccache"

# --- Setup ---

build_dir = output_base_dir / "build"
caches_dir = output_base_dir / ".." / "caches"
ccache_dir = caches_dir / "ccache"
pip_cache_dir = caches_dir / "pip"

print(f"--- Configuration ---")
print(f"Source Directory: {source_dir}")
print(f"Output Base Directory: {output_base_dir}")
print(f"Build Directory: {build_dir}")
print(f"Cache Directory: {caches_dir}")
print(f"Script Arguments: {sys.argv[1:]}")
print(f"---------------------")

print(f"Ensuring directories exist...")
ccache_dir.mkdir(parents=True, exist_ok=True)
pip_cache_dir.mkdir(parents=True, exist_ok=True)
build_dir.mkdir(parents=True, exist_ok=True) # Also ensure build dir exists early

print("Setting environment variables...")
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
    # Ensure they are unset if they existed before
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

def posix_memory_gb():
    # Get the number of memory pages and the size of each page in bytes
    # "number of pages of physical memory" https://linux.die.net/man/3/sysconf
    pages = os.sysconf('SC_PHYS_PAGES')
    page_size = os.sysconf('SC_PAGE_SIZE')
    return pages * page_size / (1024**3)

if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

    # Define the structure required by the Windows API
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("sullAvailExtendedVirtual", ctypes.c_uint64),
        ]

        def __init__(self):
            # The structure size must be set before calling the function
            self.dwLength = ctypes.sizeof(self)
            super().__init__()

    def windows_memory_gb():
        stat = MEMORYSTATUSEX()
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys / (1024**3)
        else:
            raise ctypes.WinError()
else:
    def windows_memory_gb():
        raise RuntimeError('not implemented')

def system_memory_gb():
    if sys.platform == 'win32':
        return windows_memory_gb()
    else:
        return posix_memory_gb()

# --- Build Steps ---

# 1. CMake Configure Step
# Pass through any extra arguments given to this python script ($@)
cmake_configure_cmd = [
    "cmake",
    "-G", "Ninja", # Make sure Ninja is installed and in PATH
    "-S", str(source_dir.resolve()),
    "-B", str(build_dir.resolve()),
]
cmake_configure_cmd.extend(sys.argv[1:]) # Add extra arguments from script call

run_command(cmake_configure_cmd)

# 2. CMake Build Step
cmake_build_cmd = [
    "cmake",
    "--build", str(build_dir.resolve())
]
cpu_count = os.cpu_count()
mem_gb = system_memory_gb()
if mem_gb < 256 and cpu_count >= 128:
    cpu_count = 70
if cpu_count and cpu_count > 1:
    cmake_build_cmd.extend(["--", f"-j{max(1, cpu_count)}"]) # Pass '-jN' to underlying Ninja
    print(f"Using parallel build flag: -j{max(1, cpu_count)}")

run_command(cmake_build_cmd)

print("\nBuild script completed successfully.")
