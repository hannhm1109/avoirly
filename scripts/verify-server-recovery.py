"""Restore an off-server encrypted snapshot to an internal, unpublished Docker stack.

Run as the Linux operator with sudo. Account credentials and the independently
saved backup key are read from stdin, never command arguments. No production
container, database, object or DNS record is changed by this drill.
"""

import argparse
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


def run(*command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, **kwargs).stdout


def environment_file(path, values):
    if any("\n" in str(value) or "\r" in str(value) for value in values.values()):
        raise ValueError("Multiline environment unsupported")
    path.write_text(
        "".join(key + "=" + str(value) + "\n" for key, value in values.items())
    )
    path.chmod(0o600)
    return str(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/home/ubuntu/avoirly-infra"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or not args.archive.is_file():
        raise ValueError("Root and an operator-created encrypted archive are required")
    root = args.root.resolve()
    source = (args.source or root / "avoirly").resolve()
    if source.parent != root:
        raise ValueError("Recovery helper source must be within the operator root")
    payload = json.loads(sys.stdin.read())
    if len(payload["accounts"]) != 2 or not payload.get("backup_key"):
        raise ValueError(
            "Two synthetic accounts and the offline backup key are required"
        )
    parent = root / "recovery-drills"
    parent.mkdir(mode=0o700, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="verify-", dir=parent))
    prefix = "avoirly-dr-" + uuid4().hex[:12]
    containers = []
    network = False
    stage = "unseal"
    try:
        key_file = environment_file(
            temporary / "key.env", {"AVOIRLY_BACKUP_KEY": payload["backup_key"]}
        )
        # Decrypt using the independently saved key and ciphertext copied back
        # from the Windows recovery destination, rather than the server export.
        image = payload["ops_image"]
        run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "--env-file",
            key_file,
            "-v",
            str(args.archive.resolve()) + ":/input.bin:ro",
            "-v",
            str(temporary) + ":/verify",
            "-v",
            str(source / "scripts/unseal-recovery.py") + ":/operator.py:ro",
            image,
            "python",
            "/operator.py",
        )
        (temporary / "access.private.json").write_text(json.dumps(payload))
        (temporary / "access.private.json").chmod(0o600)
        snap = temporary / "snapshot"
        manifest = json.loads((snap / "manifest.json").read_text())
        stage = "configuration"
        config = json.loads(
            run(
                "docker",
                "compose",
                "--env-file",
                str(snap / "runtime/.env"),
                "-f",
                str(snap / "runtime/docker-compose.yml"),
                "-f",
                str(snap / "deployment/supabase-private.yaml"),
                "-f",
                str(snap / "deployment/compose.yaml"),
                "config",
                "--format",
                "json",
            )
        )
        services = config["services"]
        run("docker", "network", "create", "--internal", prefix)
        network = True

        def start(
            service,
            *,
            mounts=(),
            command=None,
            aliases=(),
            env_extra=None,
            entrypoint=None,
        ):
            values = dict(services[service].get("environment", {}))
            values.update(env_extra or {})
            name = prefix + "-" + service
            arguments = [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                prefix,
                "--network-alias",
                service,
                "--log-driver",
                "local",
                "--log-opt",
                "max-size=5m",
            ]
            process_env = dict(os.environ)
            for key, value in values.items():
                if value is not None:
                    arguments += ["-e", key]
                    process_env[key] = str(value)
            for alias in aliases:
                arguments += ["--network-alias", alias]
            for mount in mounts:
                arguments += ["-v", mount]
            actual_entrypoint = (
                entrypoint
                if entrypoint is not None
                else services[service].get("entrypoint")
            )
            extra = []
            if actual_entrypoint:
                if isinstance(actual_entrypoint, str):
                    actual_entrypoint = [actual_entrypoint]
                arguments += ["--entrypoint", actual_entrypoint[0]]
                extra += actual_entrypoint[1:]
            actual_command = (
                command
                if command is not None
                else services[service].get("command") or []
            )
            if isinstance(actual_command, str):
                raise TypeError("Ambiguous recovery command")
            arguments += [services[service]["image"]] + extra + actual_command
            containers.append(name)
            run(*arguments, env=process_env)
            return name

        stage = "database"
        database = temporary / "database"
        custom = temporary / "postgresql-custom"
        for folder in [database, custom, snap / "runtime/tls"]:
            for path in [folder, *folder.rglob("*")]:
                if path.is_symlink():
                    raise ValueError("Unexpected database symlink")
                os.chown(path, 100, 101)
        database_command = [
            x.replace("log_min_messages=fatal", "log_min_messages=warning")
            for x in services["db"]["command"]
        ]
        start(
            "db",
            command=database_command,
            mounts=[
                str(database) + ":/var/lib/postgresql/data",
                str(custom) + ":/etc/postgresql-custom",
                str(snap / "runtime/tls") + ":/var/lib/postgresql/tls:ro",
            ],
            aliases=["supabase-db"],
        )
        for attempt in range(60):
            check = subprocess.run(
                [
                    "docker",
                    "exec",
                    prefix + "-db",
                    "pg_isready",
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                ],
                capture_output=True,
                check=False,
            )
            if check.returncode == 0:
                break
            time.sleep(1)
        else:
            raise ValueError("Recovered database did not start")
        # Full snapshots intentionally omit older application-archive bytes so
        # nesting cannot extend document retention. Remove only those historical
        # object references from this isolated restored database, never production.
        excluded = snap / "excluded-backup-bucket.txt"
        if excluded.exists():
            if excluded.read_text().strip() != "avoirly-backups":
                raise ValueError("Unexpected excluded backup bucket")
            run(
                "docker",
                "exec",
                "-i",
                prefix + "-db",
                "psql",
                "-U",
                "supabase_admin",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-q",
                input=(
                    b"BEGIN; SET LOCAL storage.allow_delete_query = 'true'; "
                    b"DELETE FROM storage.objects WHERE bucket_id = 'avoirly-backups'; COMMIT;\n"
                ),
            )
        stage = "auth-storage-gateway"
        start("auth", aliases=["supabase-auth"])
        start("rest")
        start("storage", mounts=[str(temporary / "storage") + ":/var/lib/storage"])
        gateway_mounts = []
        for volume in services["api-gw"].get("volumes", []):
            filename = Path(volume["source"]).name
            if filename not in {
                "envoy.yaml",
                "cds.yaml",
                "lds.template.yaml",
                "docker-entrypoint.sh",
            }:
                raise ValueError("Unexpected gateway configuration mount")
            relative = Path("envoy") / filename
            gateway_mounts.append(
                str(snap / "runtime/api" / relative) + ":" + volume["target"]
            )
        start("api-gw", mounts=gateway_mounts)
        ca_mount = str(temporary / "tls/cert.pem") + ":/recovery-ca.pem:ro"
        start(
            "avoirly-api",
            mounts=[ca_mount],
            env_extra={"SSL_CERT_FILE": "/recovery-ca.pem"},
        )
        start(
            "avoirly-web",
            mounts=[ca_mount],
            env_extra={"NODE_EXTRA_CA_CERTS": "/recovery-ca.pem"},
        )
        origins = [
            services["avoirly-api"]["environment"][x]
            for x in ["AVOIRLY_WEB_ORIGIN", "AVOIRLY_API_ORIGIN", "SUPABASE_URL"]
        ]
        hosts = [urlparse(x).hostname for x in origins]
        if any(not re.fullmatch("[a-z0-9.-]+", host or "") for host in hosts):
            raise ValueError("Invalid recovered origin")
        caddyfile = temporary / "Caddyfile"
        caddyfile.write_text(
            "\n".join(
                "https://"
                + host
                + " {\n tls /tls/cert.pem /tls/key.pem\n reverse_proxy "
                + target
                + "\n}"
                for host, target in zip(
                    hosts,
                    ["avoirly-web:3000", "avoirly-api:8000", "api-gw:8000"],
                    strict=True,
                )
            )
        )
        caddy_name = prefix + "-tls"
        arguments = ["docker", "run", "-d", "--name", caddy_name, "--network", prefix]
        for host in hosts:
            arguments += ["--network-alias", host]
        arguments += [
            "-v",
            str(caddyfile) + ":/etc/caddy/Caddyfile:ro",
            "-v",
            str(temporary / "tls") + ":/tls:ro",
            "caddy:2.10.2-alpine",
        ]
        containers.append(caddy_name)
        run(*arguments)
        stage = "isolated-service-probe"
        probe_env = {
            key: value
            for key, value in services["avoirly-api"]["environment"].items()
            if key
            in [
                "AVOIRLY_WEB_ORIGIN",
                "AVOIRLY_API_ORIGIN",
                "SUPABASE_URL",
                "SUPABASE_SECRET_KEY",
            ]
        }
        probe_env["SUPABASE_PUBLISHABLE_KEY"] = services["avoirly-web"]["environment"][
            "SUPABASE_PUBLISHABLE_KEY"
        ]
        probe_env["SSL_CERT_FILE"] = "/verify/tls/cert.pem"
        probe_file = environment_file(temporary / "probe.env", probe_env)
        run(
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--network",
            prefix,
            "--env-file",
            probe_file,
            "-v",
            str(temporary) + ":/verify",
            "-v",
            str(source / "scripts/probe-recovered-services.py") + ":/operator.py:ro",
            image,
            "python",
            "/operator.py",
        )
        report = json.loads((temporary / "service-report.json").read_text())
        inspect = json.loads(run("docker", "inspect", *containers))
        if any(item["HostConfig"].get("PortBindings") for item in inspect):
            raise ValueError("Recovery exposed a host port")
        net = json.loads(run("docker", "network", "inspect", prefix))[0]
        if net["Internal"] is not True:
            raise ValueError("Recovery network has outbound access")
        report.update(
            {
                "off_server_ciphertext_used": True,
                "isolated_internal_network": True,
                "published_ports": 0,
                "database_image": manifest["database_image"],
                "application_release": manifest["application_release"],
                "snapshot_files_verified": len(manifest["files"]),
                "production_cutover": False,
                "nested_application_archives_excluded": excluded.exists(),
            }
        )
        destination = root / "recovery-exports/restore-report.json"
        destination.write_text(json.dumps(report, indent=2))
        account = pwd.getpwnam("ubuntu")
        os.chown(destination, account.pw_uid, account.pw_gid)
        destination.chmod(0o600)
        print(json.dumps(report))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"recovery_drill_failed": type(exc).__name__, "stage": stage}))
        if (
            isinstance(exc, subprocess.CalledProcessError)
            and stage == "isolated-service-probe"
        ):
            try:
                failure = json.loads(exc.stdout)
                if "recovered_service_probe_failed" in failure and set(failure) <= {
                    "recovered_service_probe_failed",
                    "probe_stage",
                    "http_status",
                }:
                    print(json.dumps(failure))
            except (ValueError, TypeError):
                pass
        # Keep diagnostics private; callers must not publish raw container logs.
        diagnostics = root / "recovery-drill.private.log"
        with diagnostics.open("wb") as log:
            for name in containers:
                subprocess.run(
                    ["docker", "logs", "--tail", "30", name],
                    stdout=log,
                    stderr=log,
                    check=False,
                )
        diagnostics.chmod(0o600)
        raise SystemExit(1) from None
    finally:
        for name in reversed(containers):
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, check=False
            )
        if network:
            subprocess.run(
                ["docker", "network", "rm", prefix], capture_output=True, check=False
            )
        resolved = temporary.resolve()
        if resolved.parent == parent.resolve() and resolved.name.startswith("verify-"):
            shutil.rmtree(resolved)


if __name__ == "__main__":
    main()
