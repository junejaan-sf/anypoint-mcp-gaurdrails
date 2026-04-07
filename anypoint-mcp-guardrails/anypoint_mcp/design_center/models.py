"""Design Center data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DesignCenterProject:
    """Represents an Anypoint Design Center project."""

    project_id: str
    name: str
    project_type: str
    organization_id: str
    created_by: str
    default_branch: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_raw(cls, data: dict) -> "DesignCenterProject":
        return cls(
            project_id=data.get("id", ""),
            name=data.get("name", ""),
            project_type=data.get("type", "raml"),
            organization_id=data.get("organizationId", ""),
            created_by=data.get("createdBy", ""),
            default_branch=data.get("defaultBranch", "master"),
            raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "type": self.project_type,
            "organization_id": self.organization_id,
            "created_by": self.created_by,
            "default_branch": self.default_branch,
            "design_center_url": (
                f"https://anypoint.mulesoft.com/designcenter/api-designer/projects/{self.project_id}"
            ),
        }


@dataclass(slots=True)
class DesignCenterPublishResult:
    """Result of publishing from Design Center to Exchange."""

    asset_id: str
    group_id: str
    version: str
    name: str
    project_id: str
    exchange_url: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_raw(
        cls,
        data: dict,
        project_id: str,
        group_id: str,
        asset_id: str,
        version: str,
    ) -> "DesignCenterPublishResult":
        name = data.get("name") or data.get("metadata", {}).get("name", asset_id)
        exchange_url = f"https://anypoint.mulesoft.com/exchange/{group_id}/{asset_id}/{version}/"
        return cls(
            asset_id=asset_id,
            group_id=group_id,
            version=version,
            name=name,
            project_id=project_id,
            exchange_url=exchange_url,
            raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "group_id": self.group_id,
            "version": self.version,
            "name": self.name,
            "project_id": self.project_id,
            "exchange_url": self.exchange_url,
        }
