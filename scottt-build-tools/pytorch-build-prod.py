#!/usr/bin/env python

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap

def run_command(cmd: list[str | Path], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    cmd = [str(part) for part in cmd]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    location = cwd if cwd is not None else Path.cwd()
    print(f"++ Exec [{location}]$ {shlex.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=str(location), env=merged_env, check=True)


def capture_command(
    cmd: list[str | Path], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> str:
    cmd = [str(part) for part in cmd]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    location = cwd if cwd is not None else Path.cwd()
    print(f"++ Capture [{location}]$ {shlex.join(cmd)}", flush=True)
    return subprocess.check_output(cmd, cwd=str(location), env=merged_env, text=True).strip()


def script_root() -> Path:
    return Path(__file__).resolve().parent


def default_therock_repo() -> Path:
    return script_root().parents[1] / "r"


def normalize_drive_letter(value: str) -> str:
    value = value.strip().rstrip(":").upper()
    if len(value) != 1 or not value.isalpha():
        raise argparse.ArgumentTypeError(f"Expected a Windows drive letter, got '{value}'")
    return value


def parse_hip_version(rocm_root: Path) -> str:
    version_file = rocm_root / "share" / "hip" / "version"
    if not version_file.exists():
        raise FileNotFoundError(f"Expected ROCm HIP version file at '{version_file}'")
    version_parts: dict[str, str] = {}
    for raw_line in version_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        version_parts[key] = value
    try:
        return ".".join(
            [
                version_parts["HIP_VERSION_MAJOR"],
                version_parts["HIP_VERSION_MINOR"],
                version_parts["HIP_VERSION_PATCH"].split("-", 1)[0],
            ]
        )
    except KeyError as exc:
        raise RuntimeError(f"Could not parse ROCm version from '{version_file}'") from exc


def get_python_executable(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    else:
        return venv_dir / "bin" / "python"


def get_pip_executable(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    else:
        return venv_dir / "bin" / "pip"



def python_exe_from_venv(venv_dir: Path) -> Path:
    python_exe = get_python_executable(venv_dir)
    if not python_exe.exists():
        run_command([sys.executable, "-m", "venv", venv_dir])
    return python_exe


def write_rocm_shim(shim_root: Path, *, rocm_root: Path, rocm_version: str, target_family: str) -> None:
    package_root = shim_root / "src" / "rocm_sdk"
    package_root.mkdir(parents=True, exist_ok=True)
    pyproject_path = shim_root / "pyproject.toml"
    pyproject_path.write_text(
        textwrap.dedent(
            f"""
            [build-system]
            requires = ["setuptools>=68"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "rocm"
            version = "{rocm_version}"
            description = "Local ROCm shim for PyTorch Windows builds"
            requires-python = ">=3.10"

            [tool.setuptools]
            package-dir = {{"" = "src"}}

            [tool.setuptools.packages.find]
            where = ["src"]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package_root / "__init__.py").write_text(
        textwrap.dedent(
            f"""
            import os
            from pathlib import Path
            import platform

            __version__ = "{rocm_version}"
            _ROCM_ROOT = Path(r"{rocm_root}")


            def _prepend_path(path: Path) -> None:
                existing = os.environ.get("PATH", "")
                os.environ["PATH"] = str(path) + os.pathsep + existing if existing else str(path)


            def initialize_process(*, preload_shortnames=None, check_version=None, **kwargs):
                if check_version and str(check_version) != __version__:
                    raise RuntimeError(
                        f"Requested ROCm version {{check_version}} but shim provides {{__version__}}"
                    )
                bin_dir = _ROCM_ROOT / "bin"
                llvm_bin_dir = _ROCM_ROOT / "lib" / "llvm" / "bin"
                if platform.system() == "Windows":
                    if hasattr(os, "add_dll_directory"):
                        if bin_dir.exists():
                            os.add_dll_directory(str(bin_dir))
                        if llvm_bin_dir.exists():
                            os.add_dll_directory(str(llvm_bin_dir))
                if bin_dir.exists():
                    _prepend_path(bin_dir)
                if llvm_bin_dir.exists():
                    _prepend_path(llvm_bin_dir)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package_root / "__main__.py").write_text(
        textwrap.dedent(
            f"""
            import argparse
            import sys
            from pathlib import Path

            from . import __version__

            ROCM_ROOT = Path(r"{rocm_root}")
            ROCM_TARGET = "{target_family}"


            def main(argv=None):
                parser = argparse.ArgumentParser(prog="rocm_sdk")
                subparsers = parser.add_subparsers(dest="command", required=True)

                path_parser = subparsers.add_parser("path")
                path_group = path_parser.add_mutually_exclusive_group(required=True)
                path_group.add_argument("--root", action="store_true")
                path_group.add_argument("--cmake", action="store_true")
                path_group.add_argument("--bin", action="store_true")

                subparsers.add_parser("version")
                subparsers.add_parser("targets")

                args = parser.parse_args(argv)
                if args.command == "version":
                    print(__version__)
                    return 0
                if args.command == "targets":
                    print(ROCM_TARGET)
                    return 0
                if args.command == "path":
                    if args.root:
                        print(ROCM_ROOT)
                    elif args.cmake:
                        print(ROCM_ROOT / "lib" / "cmake")
                    elif args.bin:
                        print(ROCM_ROOT / "bin")
                    else:
                        parser.error("missing path selector")
                    return 0
                parser.error(f"unknown command: {{args.command}}")
                return 2


            if __name__ == "__main__":
                raise SystemExit(main(sys.argv[1:]))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def ensure_rocm_shim_installed(
    venv_dir: Path, *, rocm_root: Path, rocm_version: str, target_family: str
) -> None:
    shim_root = venv_dir / "rocm-shim"
    write_rocm_shim(
        shim_root,
        rocm_root=rocm_root,
        rocm_version=rocm_version,
        target_family=target_family,
    )
    pip_exe = get_pip_executable(venv_dir)
    run_command([python_executable(venv_dir), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "packaging"])
    run_command([pip_exe, "install", "--force-reinstall", shim_root])


def python_executable(venv_dir: Path) -> Path:
    return get_python_executable(venv_dir)


def add_path_entries(env: dict[str, str], *entries: Path) -> None:
    existing = env.get("PATH", "")
    valid_entries = [str(entry) for entry in entries if entry.exists()]
    if not valid_entries:
        return
    env["PATH"] = os.pathsep.join(valid_entries + ([existing] if existing else []))


def _find_msvc_tools_dir() -> Path | None:
    """Find the MSVC tools directory (containing link.exe, cl.exe, etc.)."""
    import shutil
    cl_path = shutil.which("cl") or shutil.which("cl.exe")
    if cl_path:
        return Path(cl_path).resolve().parent
    return None


def build_environment(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    rocm_root = args.rocm_root
    add_path_entries(env, rocm_root / "bin", rocm_root / "lib" / "llvm" / "bin")
    # On Windows, ensure MSVC tools dir (link.exe) comes before Git's /usr/bin/link.
    if sys.platform == "win32":
        msvc_dir = _find_msvc_tools_dir()
        if msvc_dir:
            env["PATH"] = str(msvc_dir) + os.pathsep + env.get("PATH", "")
    env["ROCM_PATH"] = str(rocm_root)
    env["ROCM_HOME"] = str(rocm_root)
    env["HIP_PATH"] = str(rocm_root)
    env["HIP_ROOT_DIR"] = str(rocm_root)
    env["HIP_DEVICE_LIB_PATH"] = str(rocm_root / "lib" / "llvm" / "amdgcn" / "bitcode")
    env["ROCM_SDK_TARGET_FAMILY"] = args.gpu_target
    return env


def checkout_repositories(args: argparse.Namespace, env: dict[str, str], python_path: Path) -> None:
    pytorch_tools_dir = args.therock_repo / "external-builds" / "pytorch"
    torch_checkout_cmd = [
        python_path,
        pytorch_tools_dir / "pytorch_torch_repo.py",
        "checkout",
        "--checkout-dir",
        args.pytorch_dir,
        "--gitrepo-origin",
        args.pytorch_origin,
        "--repo-hashtag",
        args.pytorch_ref,
    ]
    if args.checkout_depth is not None:
        torch_checkout_cmd.extend(["--depth", str(args.checkout_depth)])
    torch_checkout_cmd.extend(["--jobs", str(args.checkout_jobs)])
    run_command(torch_checkout_cmd, cwd=pytorch_tools_dir, env=env)

    shared_args = [
        "--torch-dir",
        args.pytorch_dir,
    ]
    if args.require_related_commits:
        shared_args.append("--require-related-commit")
    if args.checkout_depth is not None:
        shared_args.extend(["--depth", str(args.checkout_depth)])
    if args.checkout_jobs is not None:
        shared_args.extend(["--jobs", str(args.checkout_jobs)])

    audio_checkout_cmd = [
        python_path,
        pytorch_tools_dir / "pytorch_audio_repo.py",
        "checkout",
        "--checkout-dir",
        args.pytorch_audio_dir,
        *shared_args
    ]
    run_command(audio_checkout_cmd, cwd=pytorch_tools_dir, env=env)
    vision_checkout_cmd = [
        python_path,
        pytorch_tools_dir / "pytorch_vision_repo.py",
        "checkout",
        "--checkout-dir",
        args.pytorch_vision_dir,
        *shared_args
    ]
    run_command(vision_checkout_cmd, cwd=pytorch_tools_dir, env=env)

    if sys.platform != 'win32':
        apex_checkout_cmd = [
            python_path,
            pytorch_tools_dir / "pytorch_apex_repo.py",
            "checkout",
            *shared_args
        ]
        run_command(apex_checkout_cmd, cwd=pytorch_tools_dir, env=env)
        triton_checkout_cmd = [
            python_path,
            pytorch_tools_dir / "pytorch_triton_repo.py",
            "checkout",
            *shared_args
        ]
        run_command(triton_checkout_cmd, cwd=pytorch_tools_dir, env=env)

def build_rocm_python_packages(args: argparse.Namespace, env: dict[str, str], python_path: Path) -> None:
    build_script = args.therock_repo / "build_tools" / "build_python_packages.py"
    artifact_dir = args.output_root / f"r-{args.gpu_target}" / "build" / "artifacts"
    dest_dir = args.output_root / f"r-{args.gpu_target}" / "python-packages"
    run_command(
        [python_path, build_script,
         "--artifact-dir", artifact_dir,
         "--dest-dir", dest_dir],
        env=env,
    )


def run_build(args: argparse.Namespace, env: dict[str, str], python_path: Path) -> None:
    pytorch_tools_dir = args.therock_repo / "external-builds" / "pytorch"
    build_script = pytorch_tools_dir / "build_prod_wheels.py"
    build_cmd: list[str | Path] = [
        python_path,
        build_script,
        "build",
        "--output-dir",
        args.output_dir,
        "--pytorch-dir",
        args.pytorch_dir,
        "--pytorch-audio-dir",
        args.pytorch_audio_dir,
        "--pytorch-vision-dir",
        args.pytorch_vision_dir,
        "--pytorch-rocm-arch",
        args.gpu_target,
        "--no-build-triton",
        "--no-build-apex",
        "--no-enable-pytorch-flash-attention-windows",
    ]
    if args.clean:
        build_cmd.append("--clean")
    if args.build_audio is not None:
        build_cmd.extend(
            ["--build-pytorch-audio" if args.build_audio else "--no-build-pytorch-audio"]
        )
    if args.build_vision is not None:
        build_cmd.extend(
            [
                "--build-pytorch-vision"
                if args.build_vision
                else "--no-build-pytorch-vision"
            ]
        )
    if args.version_suffix:
        build_cmd.extend(["--version-suffix", args.version_suffix])
    run_command(build_cmd, cwd=pytorch_tools_dir, env=env)


def infer_require_related_commits(args: argparse.Namespace) -> bool:
    '''ROCm has a fork of Pytorch that has as "related_commits" file that points to known-good git-refs
    in the torch-{vision,audio,apex,...} repos.

    For example:
    develop branch: 

    Examples:

    * develop : https://github.com/ROCm/pytorch/blob/release/2.10/related_commits
    ubuntu|pytorch|torchvision|main|218d2ab791d437309f91e0486eb9fa7f00badc17|https://github.com/pytorch/vision

    * release/2.10 branch: https://github.com/ROCm/pytorch/blob/release/2.10/related_commits
    ubuntu|pytorch|torchvision|release/0.25|82df5f599578b383987510836bb05ea97dcc9669|https://github.com/pytorch/vision

    The fields are `os | source | project | branch | commit | origin`

    The `related_commits` file is not used when building nighly versions of Pytorch  ("Tip-on-Tip")
    Note that upstream Pytorch has a `.ci/docker/ci_commit_pints/{triton,...}.txt` which TheRock only uses for Triton in Pytorch
    '''
    return (args.pytorch_ref != "nightly")

def infer_pytorch_origin(args: argparse.Namespace) -> str:
    'Infer the GIT URL to use for Pytorch'
    if args.pytorch_origin is not None:
        return args.pytorch_origin
    if args.pytorch_ref == "nightly":
        return "https://github.com/pytorch/pytorch.git"
    else: # only the ROCm/pytorch repo has the "related_commits" file with reference to other repos
        return "https://github.com/ROCm/pytorch.git"


def pytorch_branch_name_to_version(branch_name):
    'release/2.10 -> 2.10'
    if branch_name.startswith('release/'):
        return branch_name[len('release/'):]
    return branch_name


def parse_args(argv) -> argparse.Namespace:
    repo_root = default_therock_repo()
    parser = argparse.ArgumentParser(description="Checkout and build PyTorch for Windows + ROCm")
    parser.add_argument(
        "action",
        nargs="?",
        choices=("checkout", "build", "all"),
        default="all",
        help="Run checkout, build, or both",
    )
    if sys.platform == "win32":
        parser.add_argument("--drive-letter", type=normalize_drive_letter, default="C")
    parser.add_argument("--therock-repo", type=Path, default=repo_root)
    parser.add_argument("--gpu-target", default="gfx1151")
    parser.add_argument("--pytorch-origin", default=None)
    parser.add_argument("--pytorch-ref", default="nightly")
    parser.add_argument("--checkout-depth", type=int)
    parser.add_argument("--checkout-jobs", type=int, default=10)
    parser.add_argument("--clean", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--build-audio", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--build-vision", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--version-suffix")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        drive_root = Path(f"{args.drive_letter}:/")
    else:
        drive_root = "/"
    args.workspace_root = drive_root / "w"
    args.output_root = drive_root / "o"
    if args.pytorch_ref == "nightly":
        args.torch_root = drive_root / "t"
    else:
        args.torch_root = drive_root / f't-{pytorch_branch_name_to_version(args.pytorch_ref)}'
    args.rocm_root = args.output_root / f"r-{args.gpu_target}" / "build" / "dist" / "rocm"
    args.pytorch_dir = args.torch_root / "torch"
    args.pytorch_audio_dir = args.torch_root / "audio"
    args.pytorch_vision_dir = args.torch_root / "vision"
    args.output_dir = args.output_root / "t"
    args.pytorch_build_venv_dir = args.torch_root / "venv"
    args.require_related_commits = infer_require_related_commits(args)
    args.pytorch_origin = infer_pytorch_origin(args)
    args.therock_build_venv_dir= args.therock_repo / ".venv"
    return args

main_function_map = {}

def main_function(func):
    global main_function_map
    main_function_map[func.__name__.replace('_','-')] = func
    return func

@main_function
def pytorch_build_prod(argv) -> int:
    args = parse_args(argv)
    if not args.therock_repo.exists():
        raise FileNotFoundError(f"TheRock repo not found at '{args.therock_repo}'")
    if not args.rocm_root.exists():
        raise FileNotFoundError(f"ROCm distribution root not found at '{args.rocm_root}'")

    args.torch_root.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rocm_version = parse_hip_version(args.rocm_root)
    python_path = python_exe_from_venv(args.pytorch_build_venv_dir)
    ensure_rocm_shim_installed(
        args.pytorch_build_venv_dir,
        rocm_root=args.rocm_root,
        rocm_version=rocm_version,
        target_family=args.gpu_target,
    )
    env = build_environment(args)

    print("--- Configuration ---")
    print(f"  TheRock repo:      {args.therock_repo}")
    print(f"  ROCm root:         {args.rocm_root}")
    print(f"  ROCm version:      {rocm_version}")
    print(f"  GPU target:        {args.gpu_target}")
    print(f"  Torch origin and ref:  {args.pytorch_origin} @ {args.pytorch_ref}")
    print(f"  Checkout dirs:     {args.pytorch_dir}, {args.pytorch_audio_dir}, {args.pytorch_vision_dir}")
    print(f"  Output dir:        {args.output_dir}")
    print(f"  Build venv:        {args.pytorch_build_venv_dir}")

    if args.action in ("checkout", "all"):
        checkout_repositories(args, env, python_path)
    if args.action in ("build", "all"):
        run_build(args, env, python_path)
    return 0

@main_function
def therock_build_python_packages(argv) -> int:
    args = parse_args(argv)
    if not args.therock_repo.exists():
        raise FileNotFoundError(f"TheRock repo not found at '{args.therock_repo}'")
    if not args.rocm_root.exists():
        raise FileNotFoundError(f"ROCm distribution root not found at '{args.rocm_root}'")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    rocm_version = parse_hip_version(args.rocm_root)
    python_path = python_exe_from_venv(args.therock_build_venv_dir)

    print("--- Configuration ---")
    print(f"  TheRock repo:      {args.therock_repo}")
    print(f"  ROCm root:         {args.rocm_root}")
    print(f"  ROCm version:      {rocm_version}")
    print(f"  GPU target:        {args.gpu_target}")
    print(f"  Output dir:        {args.output_dir}")
    print(f"  Build venv:        {args.therock_build_venv_dir}")
    build_rocm_python_packages(args, env=build_environment(args), python_path=python_path)
    return 0

def main_function_dispatch(name, args):
    if name.endswith(".py"):
        name = name[:-len(".py")]
    try:
        f = main_function_map[name]
    except KeyError:
        sys.stderr.write('%s is not a valid command name\n' % (name,))
        sys.exit(2)
    return f(args)

def program_name():
    return os.path.basename(sys.argv[0])

if __name__ == '__main__':
    main_function_dispatch(program_name(), sys.argv[1:])
    sys.exit(0)