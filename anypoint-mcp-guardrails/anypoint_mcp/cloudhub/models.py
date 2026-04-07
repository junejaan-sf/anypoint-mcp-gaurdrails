"""CloudHub data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CloudHubApp:
    """Represents a CloudHub 2.0 deployed application."""

    name: str
    status: str
    runtime_version: str
    last_modified: str
    replicas: int
    domain: str
    env_id: str
    region: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_raw(cls, data: dict) -> "CloudHubApp":
        """Parse a CloudHub deployment record into a CloudHubApp."""
        # CloudHub 2.0 Application Manager API response shape
        app = data.get("application", data)
        target = data.get("target", {})
        deployment_settings = target.get("deploymentSettings", {})

        name = app.get("name") or data.get("name", "")
        status = data.get("status") or data.get("desiredStatus", "UNKNOWN")
        runtime_version = (
            target.get("runtimeVersion")
            or data.get("runtimeVersion", "")
        )
        last_modified = data.get("lastModifiedDate") or data.get("updatedAt", "")
        replicas = (
            deployment_settings.get("http", {}).get("inbound", {}).get("lastMileSecurity")
            or target.get("replicas")
            or data.get("workers", {}).get("amount", 1)
        )
        if not isinstance(replicas, int):
            replicas = 1

        domain = app.get("domain") or data.get("domain", "")
        env_id = data.get("environmentId") or data.get("targetId", "")
        region = target.get("provider", {}).get("region") or data.get("region", "")

        return cls(
            name=name,
            status=str(status),
            runtime_version=str(runtime_version),
            last_modified=str(last_modified),
            replicas=replicas,
            domain=str(domain),
            env_id=str(env_id),
            region=str(region),
            raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "runtime_version": self.runtime_version,
            "last_modified": self.last_modified,
            "replicas": self.replicas,
            "domain": self.domain,
            "env_id": self.env_id,
            "region": self.region,
        }
