"""Anypoint Exchange data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ApiAsset:
    """Represents an asset in Anypoint Exchange."""

    asset_id: str
    group_id: str
    name: str
    version: str
    asset_type: str
    status: str
    description: str
    exchange_url: str
    created_at: str
    updated_at: str
    files: list[dict] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_raw(cls, data: dict) -> "ApiAsset":
        asset_id = data.get("assetId") or data.get("id", "")
        group_id = data.get("groupId", "")
        name = data.get("name", "")
        version = data.get("version", "")
        asset_type = data.get("type") or data.get("classifier", "")
        status = data.get("status", "")
        description = (data.get("description") or "").strip()
        exchange_url = (
            data.get("url")
            or f"https://anypoint.mulesoft.com/exchange/{group_id}/{asset_id}/{version}/"
        )
        created_at = data.get("createdAt") or data.get("createdDate") or data.get("created", "")
        updated_at = data.get("updatedAt") or data.get("modifiedAt") or data.get("updatedDate") or data.get("updated", "")

        files = data.get("files", [])
        labels = data.get("labels") or data.get("tags", [])
        if isinstance(labels, list):
            labels = [str(l) for l in labels]
        else:
            labels = []

        return cls(
            asset_id=str(asset_id),
            group_id=str(group_id),
            name=str(name),
            version=str(version),
            asset_type=str(asset_type),
            status=str(status),
            description=str(description),
            exchange_url=str(exchange_url),
            created_at=str(created_at),
            updated_at=str(updated_at),
            files=files if isinstance(files, list) else [],
            labels=labels,
            raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "group_id": self.group_id,
            "name": self.name,
            "version": self.version,
            "type": self.asset_type,
            "status": self.status,
            "description": self.description,
            "exchange_url": self.exchange_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "labels": self.labels,
            "files": [
                {"classifier": f.get("classifier", ""), "packaging": f.get("packaging", ""), "url": f.get("externalLink") or f.get("url", "")}
                for f in self.files
            ],
        }


@dataclass(slots=True)
class PublishResult:
    """Result of a successful Exchange asset publish."""

    asset_id: str
    group_id: str
    version: str
    name: str
    exchange_url: str
    status: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_raw(cls, data: dict, group_id: str, asset_id: str, version: str) -> "PublishResult":
        name = data.get("name", asset_id)
        exchange_url = (
            data.get("url")
            or f"https://anypoint.mulesoft.com/exchange/{group_id}/{asset_id}/{version}/"
        )
        status = data.get("status", "published")
        return cls(
            asset_id=asset_id,
            group_id=group_id,
            version=version,
            name=name,
            exchange_url=exchange_url,
            status=status,
            raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "group_id": self.group_id,
            "version": self.version,
            "name": self.name,
            "exchange_url": self.exchange_url,
            "status": self.status,
        }
