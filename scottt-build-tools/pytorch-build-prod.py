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



def ensure_venv(venv_dir: Path) -> Path:
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


def build_environment(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    rocm_root = args.rocm_root
    add_path_entries(env, rocm_root / "bin", rocm_root / "lib" / "llvm" / "bin")
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
        "--checkout-dir",
        args.pytorch_audio_dir,
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
        *shared_args,
    ]
    vision_checkout_cmd = [
        python_path,
        pytorch_tools_dir / "pytorch_vision_repo.py",
        "checkout",
        "--checkout-dir",
        args.pytorch_vision_dir,
        "--torch-dir",
        args.pytorch_dir,
    ]
    if args.require_related_commits:
        vision_checkout_cmd.append("--require-related-commit")
    if args.checkout_depth is not None:
        vision_checkout_cmd.extend(["--depth", str(args.checkout_depth)])
    if args.checkout_jobs is not None:
        vision_checkout_cmd.extend(["--jobs", str(args.checkout_jobs)])

    run_command(audio_checkout_cmd, cwd=pytorch_tools_dir, env=env)
    run_command(vision_checkout_cmd, cwd=pytorch_tools_dir, env=env)


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
    if args.require_related_commits is not None:
        return args.require_related_commits
    return args.pytorch_origin.rstrip("/").endswith("ROCm/pytorch.git") and args.pytorch_ref.startswith("release/")


def parse_args() -> argparse.Namespace:
    repo_root = default_therock_repo()
    parser = argparse.ArgumentParser(description="Checkout and build PyTorch for Windows + ROCm")
    parser.add_argument(
        "action",
        nargs="?",
        choices=("checkout", "build", "all"),
        default="all",
        help="Run checkout, build, or both",
    )
    parser.add_argument("--drive-letter", type=normalize_drive_letter, default="C")
    parser.add_argument("--therock-repo", type=Path, default=repo_root)
    parser.add_argument("--gpu-target", default="gfx1151")
    parser.add_argument("--pytorch-origin", default="https://github.com/pytorch/pytorch.git")
    parser.add_argument("--pytorch-ref", default="nightly")
    parser.add_argument(
        "--require-related-commits",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Require torch related_commits pins for audio and vision. Defaults to enabled for ROCm release branches.",
    )
    parser.add_argument("--checkout-depth", type=int)
    parser.add_argument("--checkout-jobs", type=int, default=10)
    parser.add_argument("--clean", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--build-audio", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--build-vision", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--version-suffix")
    args = parser.parse_args()

    drive_root = Path(f"{args.drive_letter}:/")
    args.workspace_root = drive_root / "w"
    args.output_root = drive_root / "o"
    args.torch_root = drive_root / "t"
    args.rocm_root = args.output_root / f"r-{args.gpu_target}" / "build" / "dist" / "rocm"
    args.pytorch_dir = args.torch_root / "pytorch"
    args.pytorch_audio_dir = args.torch_root / "audio"
    args.pytorch_vision_dir = args.torch_root / "vision"
    args.output_dir = args.torch_root / "pyout"
    args.venv_dir = args.torch_root / "venv"
    args.require_related_commits = infer_require_related_commits(args)
    return args


def main() -> int:
    args = parse_args()
    if not args.therock_repo.exists():
        raise FileNotFoundError(f"TheRock repo not found at '{args.therock_repo}'")
    if not args.rocm_root.exists():
        raise FileNotFoundError(f"ROCm distribution root not found at '{args.rocm_root}'")

    args.torch_root.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rocm_version = parse_hip_version(args.rocm_root)
    python_path = ensure_venv(args.venv_dir)
    ensure_rocm_shim_installed(
        args.venv_dir,
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
    print(f"  Torch origin/ref:  {args.pytorch_origin} @ {args.pytorch_ref}")
    print(f"  Checkout dirs:     {args.pytorch_dir}, {args.pytorch_audio_dir}, {args.pytorch_vision_dir}")
    print(f"  Output dir:        {args.output_dir}")
    print(f"  Build venv:        {args.venv_dir}")

    if args.action in ("checkout", "all"):
        checkout_repositories(args, env, python_path)
    if args.action in ("build", "all"):
        run_build(args, env, python_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
