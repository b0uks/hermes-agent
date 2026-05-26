"""Friendly host-side Docker launcher for Hermes.

This module intentionally shells out to the local Docker CLI instead of using a
Docker SDK dependency. It is for users who want Docker deployment ergonomics
without copying long ``docker run`` commands from the docs.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


DEFAULT_IMAGE = "nousresearch/hermes-agent:latest"
DEFAULT_GATEWAY_PORT = 8642
DEFAULT_DASHBOARD_PORT = 9119
DEFAULT_TUI_DIR = "/opt/hermes/ui-tui"


def _default_data_dir() -> Path:
    return Path(os.environ.get("HERMES_DOCKER_HOME", "~/.hermes")).expanduser()


def _sanitize_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("._-")
    return value.lower() or "default"


def generate_container_name(data_dir: str | Path, *, role: str = "gateway") -> str:
    """Generate a stable Docker container name from the host data directory."""
    resolved = Path(data_dir).expanduser().resolve()
    raw_base = resolved.name
    if raw_base in {"", ".hermes"}:
        base = "default"
    else:
        base = _sanitize_name(raw_base)
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]
    prefix = f"hermes-{base}-{digest}"
    return prefix if role == "gateway" else f"{prefix}-{_sanitize_name(role)}"


def _docker(*, dry_run: bool = False) -> str:
    docker = shutil.which("docker")
    if docker:
        return docker
    if dry_run:
        return "docker"
    if not docker:
        print("Error: docker not found on PATH.", file=sys.stderr)
        sys.exit(1)
    return docker


def _run(cmd: list[str], *, dry_run: bool = False) -> int:
    if dry_run:
        print(shlex.join(cmd))
        return 0
    return subprocess.call(cmd)


def _capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def _ensure_data_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _uid_gid_env() -> list[str]:
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        return []
    return [
        "-e",
        f"HERMES_UID={os.getuid()}",
        "-e",
        f"HERMES_GID={os.getgid()}",
    ]


def _image(args: argparse.Namespace) -> str:
    return args.image or os.environ.get("HERMES_DOCKER_IMAGE") or DEFAULT_IMAGE


def _remainder(args: argparse.Namespace) -> list[str]:
    items = list(getattr(args, "hermes_args", None) or [])
    if items and items[0] == "--":
        return items[1:]
    return items


def _name(args: argparse.Namespace, *, role: str = "gateway") -> str:
    return args.name or generate_container_name(args.data_dir, role=role)


def _base_run_args(args: argparse.Namespace, *, interactive: bool, name: str) -> list[str]:
    data_dir = _ensure_data_dir(Path(args.data_dir))
    flags = ["-it", "--rm"] if interactive else ["-d"]
    user_env = list(args.env or [])
    cmd = [
        _docker(dry_run=args.dry_run),
        "run",
        *flags,
        "--name",
        name,
        "-v",
        f"{data_dir}:/opt/data",
        *_uid_gid_env(),
    ]
    if not any(item.split("=", 1)[0] == "HERMES_TUI_DIR" for item in user_env):
        cmd.extend(["-e", f"HERMES_TUI_DIR={DEFAULT_TUI_DIR}"])
    for item in user_env:
        cmd.extend(["-e", item])
    return cmd


def _container_exists(name: str) -> bool:
    result = _capture([_docker(), "inspect", "--format", "{{.Id}}", name])
    return result.returncode == 0


def _container_running(name: str) -> bool:
    result = _capture([_docker(), "inspect", "--format", "{{.State.Running}}", name])
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def cmd_setup(args: argparse.Namespace) -> int:
    name = _name(args, role=f"setup-{os.getpid()}")
    cmd = _base_run_args(args, interactive=True, name=name)
    cmd.extend([_image(args), "setup"])
    return _run(cmd, dry_run=args.dry_run)


def cmd_gateway(args: argparse.Namespace) -> int:
    name = _name(args)
    docker = _docker(dry_run=args.dry_run)

    if not args.dry_run and _container_exists(name):
        action = "running" if _container_running(name) else "started"
        if action == "started":
            code = _run([docker, "start", name])
            if code != 0:
                return code
        print(f"Hermes gateway container {action}: {name}")
        return 0

    cmd = _base_run_args(args, interactive=False, name=name)
    cmd.extend(["--restart", args.restart])
    if not args.no_api_port:
        cmd.extend(["-p", f"{args.api_port}:8642"])
    if args.dashboard:
        cmd.extend(["-p", f"{args.dashboard_port}:9119", "-e", "HERMES_DASHBOARD=1"])
        if args.dashboard_tui:
            cmd.extend(["-e", "HERMES_DASHBOARD_TUI=1"])
    cmd.extend([_image(args), "gateway", "run"])
    code = _run(cmd, dry_run=args.dry_run)
    if code == 0 and not args.dry_run:
        print(f"Hermes gateway container launched: {name}")
    return code


def _chat_container_name(args: argparse.Namespace, role: str = "chat") -> str:
    if args.name:
        return args.name
    stamp = f"{role}-{int(time.time())}-{os.getpid()}"
    return generate_container_name(args.data_dir, role=stamp)


def cmd_chat(args: argparse.Namespace) -> int:
    name = _chat_container_name(args)
    cmd = _base_run_args(args, interactive=True, name=name)
    hermes_args = _remainder(args)
    if args.tui and "--tui" not in hermes_args:
        hermes_args.insert(0, "--tui")
    cmd.extend([_image(args), *hermes_args])
    return _run(cmd, dry_run=args.dry_run)


def cmd_continue(args: argparse.Namespace) -> int:
    name = _chat_container_name(args, "continue")
    cmd = _base_run_args(args, interactive=True, name=name)
    hermes_args = ["--tui", "--continue"]
    if args.session:
        hermes_args.append(args.session)
    hermes_args.extend(_remainder(args))
    cmd.extend([_image(args), *hermes_args])
    return _run(cmd, dry_run=args.dry_run)


def cmd_resume(args: argparse.Namespace) -> int:
    name = _chat_container_name(args, "resume")
    cmd = _base_run_args(args, interactive=True, name=name)
    hermes_args = ["--tui", "--resume", args.session]
    hermes_args.extend(_remainder(args))
    cmd.extend([_image(args), *hermes_args])
    return _run(cmd, dry_run=args.dry_run)


def cmd_exec(args: argparse.Namespace) -> int:
    name = _name(args)
    hermes_args = _remainder(args)
    if not hermes_args:
        hermes_args = ["--tui"]
    cmd = [
        _docker(dry_run=args.dry_run),
        "exec",
        "-it",
        "-u",
        "hermes",
        name,
        "hermes",
        *hermes_args,
    ]
    return _run(cmd, dry_run=args.dry_run)


def cmd_shell(args: argparse.Namespace) -> int:
    name = _name(args)
    shell = args.shell or "bash"
    cmd = [_docker(dry_run=args.dry_run), "exec", "-it", "-u", "hermes", name, shell]
    return _run(cmd, dry_run=args.dry_run)


def cmd_stop(args: argparse.Namespace) -> int:
    return _run([_docker(dry_run=args.dry_run), "stop", _name(args)], dry_run=args.dry_run)


def cmd_rm(args: argparse.Namespace) -> int:
    return _run([_docker(dry_run=args.dry_run), "rm", "-f", _name(args)], dry_run=args.dry_run)


def cmd_logs(args: argparse.Namespace) -> int:
    cmd = [_docker(dry_run=args.dry_run), "logs"]
    if args.follow:
        cmd.append("-f")
    if args.tail:
        cmd.extend(["--tail", str(args.tail)])
    cmd.append(_name(args))
    return _run(cmd, dry_run=args.dry_run)


def cmd_status(args: argparse.Namespace) -> int:
    name = _name(args)
    cmd = [
        _docker(dry_run=args.dry_run),
        "ps",
        "-a",
        "--filter",
        f"name=^{name}$",
        "--format",
        "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
    ]
    return _run(cmd, dry_run=args.dry_run)


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        default=str(_default_data_dir()),
        help="Host directory mounted as /opt/data (default: ~/.hermes)",
    )
    parser.add_argument(
        "--name",
        help="Docker container name (default: generated from --data-dir)",
    )
    parser.add_argument(
        "--image",
        help=f"Docker image (default: {DEFAULT_IMAGE}, or HERMES_DOCKER_IMAGE)",
    )
    parser.add_argument(
        "-e",
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Additional environment variable for docker run (repeatable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the docker command instead of running it",
    )


def build_parser(prog: str = "hermes docker") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Launch and manage Hermes Agent Docker containers",
    )
    sub = parser.add_subparsers(dest="docker_command", required=True)

    setup = sub.add_parser("setup", help="Run setup wizard in a one-shot container")
    _add_common_flags(setup)
    setup.set_defaults(func=cmd_setup)

    gateway = sub.add_parser("gateway", aliases=["start"], help="Start gateway container")
    _add_common_flags(gateway)
    gateway.add_argument("--restart", default="unless-stopped", help="Docker restart policy")
    gateway.add_argument("--api-port", type=int, default=DEFAULT_GATEWAY_PORT)
    gateway.add_argument("--no-api-port", action="store_true", help="Do not publish port 8642")
    gateway.add_argument("--dashboard", action="store_true", help="Run dashboard sidecar in the same container")
    gateway.add_argument("--dashboard-port", type=int, default=DEFAULT_DASHBOARD_PORT)
    gateway.add_argument("--dashboard-tui", action="store_true", help="Expose embedded TUI in dashboard")
    gateway.set_defaults(func=cmd_gateway)

    chat = sub.add_parser("chat", help="Run an interactive ephemeral chat container")
    _add_common_flags(chat)
    chat.add_argument("--no-tui", dest="tui", action="store_false", default=True)
    chat.add_argument("hermes_args", nargs=argparse.REMAINDER, help="Arguments passed to hermes")
    chat.set_defaults(func=cmd_chat)

    cont = sub.add_parser("continue", aliases=["c"], help="Resume the latest session in Docker")
    _add_common_flags(cont)
    cont.add_argument("session", nargs="?", help="Optional session title/name")
    cont.add_argument("hermes_args", nargs=argparse.REMAINDER, help="Extra arguments passed to hermes")
    cont.set_defaults(func=cmd_continue)

    resume = sub.add_parser("resume", aliases=["r"], help="Resume a session by ID or title in Docker")
    _add_common_flags(resume)
    resume.add_argument("session", help="Session ID or title")
    resume.add_argument("hermes_args", nargs=argparse.REMAINDER, help="Extra arguments passed to hermes")
    resume.set_defaults(func=cmd_resume)

    exec_p = sub.add_parser("exec", help="Run hermes inside the persistent gateway container")
    _add_common_flags(exec_p)
    exec_p.add_argument("hermes_args", nargs=argparse.REMAINDER, help="Arguments passed to hermes")
    exec_p.set_defaults(func=cmd_exec)

    shell = sub.add_parser("shell", help="Open a shell inside the persistent gateway container")
    _add_common_flags(shell)
    shell.add_argument("--shell", help="Shell to execute (default: bash)")
    shell.set_defaults(func=cmd_shell)

    stop = sub.add_parser("stop", help="Stop the persistent gateway container")
    _add_common_flags(stop)
    stop.set_defaults(func=cmd_stop)

    rm = sub.add_parser("rm", help="Remove the persistent gateway container")
    _add_common_flags(rm)
    rm.set_defaults(func=cmd_rm)

    logs = sub.add_parser("logs", help="Show gateway container logs")
    _add_common_flags(logs)
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("--tail", default="100", help="Number of lines to show")
    logs.set_defaults(func=cmd_logs)

    status = sub.add_parser("status", help="Show gateway container status")
    _add_common_flags(status)
    status.set_defaults(func=cmd_status)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser("hermes-docker")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


def command_main(args: argparse.Namespace) -> int:
    argv = getattr(args, "docker_args", None)
    parser = build_parser("hermes docker")
    parsed = parser.parse_args(list(argv or []))
    return parsed.func(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
