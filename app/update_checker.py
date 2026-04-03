#!/usr/bin/env python3
"""Docker image update checker and container updater."""

import json
import os
import subprocess
import urllib.request
import urllib.parse
import re


class UpdateChecker:
    def __init__(self, config):
        self.config = config
        self.debug_log = []

    def _debug(self, msg):
        print(msg)
        if self.config.debug:
            self.debug_log.append(msg)

    def get_running_containers(self):
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Image}}"],
            capture_output=True, text=True
        )
        # Get own container name to exclude self
        hostname = os.environ.get("HOSTNAME", "")
        own_name = None
        if hostname:
            own_result = subprocess.run(
                ["docker", "inspect", "--format", "{{.Name}}", hostname],
                capture_output=True, text=True
            )
            if own_result.returncode == 0:
                own_name = own_result.stdout.strip().lstrip("/")

        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            name, image = line.split("|", 1)
            # Skip self
            if own_name and name == own_name:
                self._debug(f"  Skipped (self): {name}")
                continue
            # Skip images referenced by ID (no tag)
            if re.match(r'^[0-9a-f]{12,}$', image):
                self._debug(f"  Skipped (image ID): {name} ({image})")
                continue
            if name not in self.config.exclude_containers:
                containers.append({"name": name, "image": image})
            else:
                self._debug(f"  Skipped (excluded): {name}")
        return containers

    def _parse_image(self, image):
        """Parse image reference into registry, repository, tag."""
        tag = "latest"
        if ":" in image and not image.endswith(":"):
            parts = image.rsplit(":", 1)
            if "/" not in parts[1]:
                image, tag = parts

        if image.startswith("sha256:"):
            return None, None, None

        # Determine registry
        if "/" not in image:
            return "registry-1.docker.io", f"library/{image}", tag

        first_part = image.split("/")[0]
        if "." in first_part or ":" in first_part or first_part == "localhost":
            registry = first_part
            repository = "/".join(image.split("/")[1:])
        else:
            registry = "registry-1.docker.io"
            repository = image

        return registry, repository, tag

    def _get_auth_token(self, registry, repository):
        """Get authentication token for registry API."""
        try:
            # Docker Hub
            if "docker.io" in registry:
                docker_config = os.environ.get("DOCKER_CONFIG", "/.docker")
                config_file = os.path.join(docker_config, "config.json")
                auth_header = None
                if os.path.exists(config_file):
                    with open(config_file) as f:
                        cfg = json.load(f)
                    for key in cfg.get("auths", {}):
                        if "docker.io" in key:
                            auth_header = cfg["auths"][key].get("auth")
                            break
                    self._debug(f"  Auth: {'credentials found' if auth_header else 'no credentials'}")

                url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repository}:pull"
                req = urllib.request.Request(url)
                if auth_header:
                    req.add_header("Authorization", f"Basic {auth_header}")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read()).get("token")

            # GitHub Container Registry
            if "ghcr.io" in registry:
                url = f"https://ghcr.io/token?scope=repository:{repository}:pull"
                with urllib.request.urlopen(url, timeout=15) as resp:
                    return json.loads(resp.read()).get("token")

        except Exception as e:
            self._debug(f"  Auth error: {e}")
        return None

    def _get_remote_digest(self, registry, repository, tag, token):
        """Get remote image digest via registry API HEAD request."""
        if "docker.io" in registry:
            url = f"https://registry-1.docker.io/v2/{repository}/manifests/{tag}"
        elif "ghcr.io" in registry:
            url = f"https://ghcr.io/v2/{repository}/manifests/{tag}"
        else:
            url = f"https://{registry}/v2/{repository}/manifests/{tag}"

        req = urllib.request.Request(url, method="HEAD")
        req.add_header("Accept", ", ".join([
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
        ]))
        if token:
            req.add_header("Authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                digest = resp.headers.get("Docker-Content-Digest", "")
                return digest
        except Exception as e:
            self._debug(f"  Registry error: {e}")
            return None

    def _get_local_digest(self, image):
        """Get local image digest from RepoDigests."""
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image],
            capture_output=True, text=True
        )
        if result.returncode == 0 and "@" in result.stdout:
            return result.stdout.strip().split("@")[1]
        return None

    def check_all(self, bot=None):
        self.debug_log = []
        containers = self.get_running_containers()
        self._debug(f"Checking {len(containers)} containers for updates...")
        updates = []

        for c in containers:
            image = c["image"]
            registry, repository, tag = self._parse_image(image)
            if not registry:
                self._debug(f"  Skipped (unparseable): {c['name']} ({image})")
                continue

            self._debug(f"  Checking: {c['name']} ({registry}/{repository}:{tag})")

            local_digest = self._get_local_digest(image)
            if not local_digest:
                self._debug(f"  Skipped (no local digest): {c['name']}")
                continue

            token = self._get_auth_token(registry, repository)
            remote_digest = self._get_remote_digest(registry, repository, tag, token)

            self._debug(f"  Local:  {local_digest[:30]}...")
            self._debug(f"  Remote: {(remote_digest or 'FAILED')[:30]}...")

            if remote_digest and local_digest != remote_digest:
                self._debug(f"  → UPDATE AVAILABLE")
                updates.append(c)
            else:
                self._debug(f"  → Up to date")

        # Save pending updates
        with open(self.config.pending_file, "w") as f:
            json.dump(updates, f)
        self._debug(f"Found {len(updates)} updates.")

        # Send debug log via Telegram
        if self.config.debug and bot and self.debug_log:
            log_text = "\n".join(self.debug_log)
            # Split into chunks if too long
            while log_text:
                chunk = log_text[:3500]
                log_text = log_text[3500:]
                bot.send_message(f"```\n{chunk}\n```")

        return updates

    def update_container(self, name, image):
        self._debug(f"Updating: {name} ({image})...")

        # Pull new image
        result = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            if "toomanyrequests" in result.stderr:
                return False, "Rate limit erreicht. `docker login` auf dem Host ausführen und Credentials mounten."
            return False, f"Pull failed: {result.stderr[:200]}"

        self._debug(f"  Pull OK: {name}")

        # Find compose project directory
        inspect = subprocess.run(
            ["docker", "inspect", name, "--format",
             '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'],
            capture_output=True, text=True
        )
        compose_dir = inspect.stdout.strip()
        self._debug(f"  Compose dir: {compose_dir or 'none'}")

        if not compose_dir:
            return True, "Image pulled. No compose project found."

        # Get service name
        service = subprocess.run(
            ["docker", "inspect", name, "--format",
             '{{index .Config.Labels "com.docker.compose.service"}}'],
            capture_output=True, text=True
        )
        service_name = service.stdout.strip()
        self._debug(f"  Service: {service_name or 'none'}")

        if not service_name:
            return True, "Image pulled. Service name not found."

        # Restart via docker compose
        try:
            result = subprocess.run(
                ["docker", "compose", "-p",
                 name.rsplit("-", 1)[0] if "-" in name else name,
                 "-f", os.path.join(compose_dir, "docker-compose.yml"),
                 "up", "-d", service_name],
                capture_output=True, text=True, timeout=300
            )
            self._debug(f"  Compose result: rc={result.returncode}")
            if result.returncode != 0:
                self._debug(f"  Compose stderr: {result.stderr[:200]}")
                # Fallback: try with compose_dir as cwd
                result = subprocess.run(
                    ["docker", "compose", "up", "-d", service_name],
                    capture_output=True, text=True, cwd=compose_dir, timeout=300
                )
                self._debug(f"  Fallback result: rc={result.returncode}")
                if result.returncode != 0:
                    self._debug(f"  Fallback stderr: {result.stderr[:200]}")
                    return False, f"Compose error: {result.stderr[:200]}"
        except FileNotFoundError:
            return True, "Image pulled. Compose dir not accessible."
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"

        return True, "OK"
