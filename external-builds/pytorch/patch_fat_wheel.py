"""Given a torch .whl, patches it so that it contains ROCm on Linux and Windows.

This lets us have a standalone PyTorch wheel (albeit a big one) that does not need
a separate ROCm installation. While we have better means of packaging, this approach
has the benefit of simplicity, since you can build ROCm separately, then build PyTorch,
then smash them together vs dealing with 'packaging' stuff explicitly.
"""

import argparse
from pathlib import Path
import sys
import os
import glob
import tempfile
import zipfile
import subprocess
import shlex
import shutil
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "build_tools"))
from _therock_utils.pattern_match import PatternMatcher


def run(args):
    wheel_input_path: Path = args.wheel_path
    wheel_output_path: Path = args.output_path
    wheel_input_fname = wheel_input_path.name
    if not args.output_path:
        # Derive from the wheel path.
        distribution, version, *rest = wheel_input_fname.split("-")
        if "+" in version:
            version, version_extra = version.split("+", maxsplit=2)
            version_extra = f"rocm_{version_extra}"
        else:
            version_extra = "rocm"
        version = f"{version}+{version_extra}"
        wheel_output_fname = "-".join([distribution, version] + rest)
        wheel_output_path = wheel_input_path.with_name(wheel_output_fname)

    missing_sysdeps = []
    if sys.platform == 'linux':
        # Assume building on manylinux-2_28
        missing_sysdeps.append(Path('/usr/lib64/libgomp.so.1'))
        missing_sysdeps.append(Path('/usr/lib64/libquadmath.so.0'))
        missing_sysdeps.append(Path('/usr/lib64/libgfortran.so.5'))
        missing_sysdeps.append(Path('/usr/lib64/libatomic.so.1'))

    print(f"Processing {wheel_input_path} to {wheel_output_path}")
    delete = False
    with tempfile.TemporaryDirectory(dir=wheel_output_path.parent, delete=delete) as td:
        print(f'Temporary Dir: {str(td)}')
        process_wheel(wheel_input_path, wheel_output_path, args.rocm_path, Path(td),
                      missing_sysdeps, args)

def exec_cmd(args: list[str | Path], cwd: Path):
    args = [str(arg) for arg in args]
    print(f"++ Exec [{cwd}]$ {shlex.join(args)}")
    subprocess.check_call(args, cwd=str(cwd), stdin=subprocess.DEVNULL)

def capture(args: list[str | Path], cwd: Path) -> str:
    args = [str(arg) for arg in args]
    print(f"++ Exec [{cwd}]$ {shlex.join(args)}")
    return subprocess.check_output(
        args, cwd=str(cwd), stdin=subprocess.DEVNULL
    ).decode()

def resolve_symlinks(lib_path: Path):
    all_paths: list[Path] = [lib_path]
    all_paths.extend([Path(p) for p in glob.glob(f"{str(lib_path)}.*")])
    return all_paths

def prefix_soname(lib_path: Path,
                      prefix_to_add: str,
                      args: argparse.Namespace,
                      ):
    orig_paths = resolve_symlinks(lib_path)
    lib_path_canon = lib_path.resolve()
    orig_soname = capture(
        [args.patchelf, "--print-soname", str(lib_path)], cwd=Path.cwd()
    ).strip()
    soname_prefix = ""
    soname_stem = orig_soname
    if orig_soname.startswith("lib"):
        soname_prefix = "lib"
        soname_stem = orig_soname[len("lib") :]
    new_soname = f"{soname_prefix}{prefix_to_add}{soname_stem}"
    new_lib_path = lib_path.parent / f"{new_soname}"
    if new_lib_path.exists():
        new_lib_path.unlink()
    print(f"Prefixing SONAME {orig_soname} -> {new_soname} for {lib_path_canon}")
    lib_path_canon.rename(new_lib_path)
    exec_cmd(
        [
            args.patchelf,
            "--set-soname",
            new_soname,
            new_lib_path,
        ],
        cwd=Path.cwd(),
    )
    # Remove old links.
    for orig_path in orig_paths:
        if orig_path.is_symlink():
            print(f"Removing original link: {orig_path}")
            orig_path.unlink()

    # Establish new dev symlink.
    lib_path.symlink_to(new_lib_path.name)
    return orig_soname, new_soname

def process_missing_sysdep(missing_sysdep: Path,
                           soname_prefix: str,
                           dest_dir: Path,
                           dependent_lib_dir: Path,
                           args: argparse.Namespace,
                           ):
    'Copy `missing_sysdep` to `dest_dir`, change its soname, then update libs in `dependent_lib_dir` to use the new name'

    print(f"Copying missing sysdep: {missing_sysdep} to {dest_dir}")
    Path(dest_dir).mkdir(exist_ok=True, parents=True)
    shutil.copy(missing_sysdep, dest_dir)
    lib_path = dest_dir / os.path.basename(missing_sysdep)
    orig_soname, new_soname = prefix_soname(lib_path, soname_prefix, args)

    for i in glob.glob(str(dependent_lib_dir / '*.so*')):
        exec_cmd(
            [
                args.patchelf,
                "--replace-needed",
                orig_soname,
                new_soname,
                i,
            ],
            cwd=Path.cwd(),
        )

def set_rpath(libs: List[str], run_paths: List[str], args: argparse.Namespace):
    rpath_str = os.path.pathsep.join(run_paths)
    for i in libs:
        exec_cmd(
            [
                args.patchelf,
                "--set-rpath", rpath_str,
                i,
            ],
            cwd=Path.cwd(),
        )

def process_wheel(
    wheel_input_path: Path, wheel_output_path: Path, rocm_path: Path, temp_dir: Path,
    missing_sysdeps: List[Path],
    args: argparse.Namespace,
):
    print("Extracting wheel...")
    with zipfile.ZipFile(wheel_input_path, "r") as zip_in:
        zip_in.extractall(temp_dir)

    if sys.platform == 'win32':
        init_py = temp_dir / "torch" / "__init__.py"
        print("Patching __init__.py")
        patch_init_py(init_py)

    print("Copying rocm")
    if sys.platform == 'win32':
        pm = PatternMatcher(
            excludes=[
                # The full compiler is big and not needed. Strip.
                "lib/llvm/**",
                # On windows, outside of clients, sysdeps are static.
                "lib/rocm_sysdeps/**",
                # Currently, outside of clients, we don't need host math libs.
                "lib/host-math/**",
                # Don't need any EXEs
                "bin/*.exe",
            ]
        )
    else:
        pm = PatternMatcher(
            excludes=[
                # Only ship the llvm libraries
                "lib/llvm/bin",
                "lib/llvm/include",
                "lib/llvm/amdgcn",
                # libhipsolver.so needs host-math/libcholmod.so.5
                "lib/host-math/include",
                # Only ship sysdeps/lib
                "lib/rocm_sysdeps/bin",
                "lib/rocm_sysdeps/share",
                "lib/rocm_sysdeps/include",
                # Don't need any executables
                "bin/*",
            ]
        )
    pm.add_basedir(rocm_path)
    temp_torch_dir = temp_dir / "torch"
    temp_torch_lib_dir = temp_torch_dir / "lib"
    temp_rocm_dir = temp_torch_lib_dir / "rocm"
    pm.copy_to(destdir=temp_rocm_dir)

    temp_rocm_sysdeps_lib_dir = temp_rocm_dir / "lib" / "rocm_sysdeps" / "lib"
    if missing_sysdeps:
        for i in missing_sysdeps:
            process_missing_sysdep(i, 'rocm_sysdeps_',
                                   temp_rocm_sysdeps_lib_dir, temp_torch_lib_dir, args)

    if sys.platform == 'linux':
        set_rpath(glob.glob(os.path.join(temp_torch_dir, "*.so*")),
                  ["$ORIGIN/lib"],
                  args)
        set_rpath(# libaotriton_v2.so{.0.9.2}
                  glob.glob(os.path.join(temp_torch_lib_dir, "*.so*")),
                  ["$ORIGIN",
                   "$ORIGIN/rocm/lib",
                   "$ORIGIN/rocm/lib/rocm_sysdeps/lib"],
                  args)

    print(f"Saving wheel to {wheel_output_path}")
    if wheel_output_path.exists():
        wheel_output_path.unlink()
    dest_pm = PatternMatcher()
    dest_pm.add_basedir(temp_dir)
    with zipfile.ZipFile(wheel_output_path, "w") as zip_out:
        for relpath, direntry in dest_pm.matches():
            if direntry.is_dir():
                continue
            if sys.platform == 'win32' and direntry.is_symlink():
                continue
            zip_out.write(direntry.path, relpath)


def patch_init_py(init_py_path: Path):
    # On Windows, patch the directories that pytorch adds to 
    # `os.add_dll_directory()` in `torch/__init__.py`
    #
    # https://github.com/pytorch/pytorch/blob/v2.7.0/torch/__init__.py#L223
    # https://docs.python.org/3/library/os.html#os.add_dll_directory` 
    lines = init_py_path.read_text().splitlines(keepends=True)
    with open(init_py_path, "w") as out:
        for line in lines:
            if "for dll_path in dll_paths:" in line:
                indent_count = len(line) - len(line.lstrip())
                indent = line[0:indent_count]
                patch_line = f"{indent}dll_paths.insert(0, os.path.join(os.path.join(th_dll_path, 'rocm', 'bin')))\n"
                print("Insert:")
                print(f"+{patch_line}")
                print(f" {line}")
                out.write(patch_line)
            out.write(line)


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("wheel_path", type=Path, help="Path to wheel file to alter")
    p.add_argument(
        "rocm_path", type=Path, help="Path to build/dist/rocm or equiv to embed"
    )
    p.add_argument("--output-path", type=Path, help="Optional path of the output wheel")
    p.add_argument("--patchelf", default="patchelf", help="Path to patchelf command")
    args = p.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main(sys.argv[1:])
