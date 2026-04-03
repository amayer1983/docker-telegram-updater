#!/usr/bin/env python3
"""Docker image update checker and container updater."""

import json
import os
import subprocess


class UpdateChecker:
    def __init__(self, config):
        self.config = config

    def get_running_containers(self):
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Image}}"],
            capture_output=True, text=True
        )
        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            name, image = line.split("|", 1)
            if name not in self.config.exclude_containers:
                containers.append({"name": name, "image": image})
        return containers

    def get_local_digest(self, image):
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            digest = result.stdout.strip()
            if "@sha256:" in digest:
                return digest.split("@sha256:")[1]
        return None

    def get_remote_digest(self, image):
        result = subprocess.run(
            ["docker", "manifest", "inspect", image],
            capture_output=True, text=True,
            env={**os.environ, "DOCKER_CLI_EXPERIMENTAL": "enabled"}
        )
        if result.returncode != 0:
            return None
        try:
            manifest = json.loads(result.stdout)
            if "manifests" in manifest:
                for m in manifest["manifests"]:
                    if m.get("platform", {}).get("architecture") == "amd64":
                        return m["digest"].replace("sha256:", "")
            return manifest.get("config", {}).get("digest", "").replace("sha256:", "")
        except (json.JSONDecodeError, KeyError):
            return None

    def check_all(self):
        containers = self.get_running_containers()
        print(f"Checking {len(containers)} containers for updates...")
        updates = []
        for c in containers:
            image = c["image"]
            if image.startswith("sha256:"):
                continue
            if ":" not in image:
                image = image + ":latest"
            local = self.get_local_digest(image)
            remote = self.get_remote_digest(image)
            if local and remote and local != remote:
                updates.append(c)
        # Save pending updates
        with open(self.config.pending_file, "w") as f:
            json.dump(updates, f)
        print(f"Found {len(updates)} updates.")
        return updates

    def update_container(self, name, image):
        print(f"Updating: {name} ({image})...")

        # Pull new image
        result = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            return False, f"Pull failed: {result.stderr[:200]}"

        # Find compose project directory
        inspect = subprocess.run(
            ["docker", "inspect", name, "--format",
             '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'],
            capture_output=True, text=True
        )
        compose_dir = inspect.stdout.strip()

        if not compose_dir or not os.path.isdir(compose_dir):
            return True, "Image pulled. Manual restart required (no compose dir)."

        # Get service name
        service = subprocess.run(
            ["docker", "inspect", name, "--format",
             '{{index .Config.Labels "com.docker.compose.service"}}'],
            capture_output=True, text=True
        )
        service_name = service.stdout.strip()

        if not service_name:
            return True, "Image pulled. Service name not found."

        # Restart via docker compose
        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d", service_name],
                capture_output=True, text=True, cwd=compose_dir, timeout=300
            )
            if result.returncode != 0:
                return False, f"Compose error: {result.stderr[:200]}"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"

        return True, "OK"
