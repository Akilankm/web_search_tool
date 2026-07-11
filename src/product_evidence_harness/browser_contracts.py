from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class AcquisitionMethod(str, Enum):
    DIRECT_HTTP_DOWNLOAD = "DIRECT_HTTP_DOWNLOAD"
    BROWSER_CONTEXT_DOWNLOAD = "BROWSER_CONTEXT_DOWNLOAD"
    NETWORK_RESPONSE_CAPTURE = "NETWORK_RESPONSE_CAPTURE"
    BROWSER_ELEMENT_SCREENSHOT = "BROWSER_ELEMENT_SCREENSHOT"
    BROWSER_SECTION_SCREENSHOT = "BROWSER_SECTION_SCREENSHOT"
    BROWSER_VIEWPORT_SCREENSHOT = "BROWSER_VIEWPORT_SCREENSHOT"
    BROWSER_FULL_PAGE_SCREENSHOT = "BROWSER_FULL_PAGE_SCREENSHOT"


class BrowserEvidenceStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    ACCESS_BLOCKED = "ACCESS_BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProductIdentityPayload:
    row_id: str
    main_text: str
    country_code: str
    retailer_name: str | None = None
    ean: str | None = None
    language_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvidenceIntent:
    verify_rendered_product: bool = True
    expand_product_sections: bool = True
    collect_gallery: bool = True
    download_images: bool = True
    capture_screenshot_fallbacks: bool = True
    capture_full_page_audit: bool = False
    maximum_images: int = 10
    maximum_screenshots: int = 8
    maximum_actions: int = 30
    requested_evidence_categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "maximum_images", max(0, min(int(self.maximum_images), 30)))
        object.__setattr__(self, "maximum_screenshots", max(0, min(int(self.maximum_screenshots), 20)))
        object.__setattr__(self, "maximum_actions", max(1, min(int(self.maximum_actions), 100)))
        object.__setattr__(
            self,
            "requested_evidence_categories",
            tuple(dict.fromkeys(str(item).strip() for item in self.requested_evidence_categories if str(item).strip())),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BrowserEvidenceRequest:
    job_id: str
    candidate_id: str
    url: str
    product_identity: ProductIdentityPayload
    intent: EvidenceIntent = field(default_factory=EvidenceIntent)

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("url must be an absolute HTTP(S) URL")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "candidate_id": self.candidate_id,
            "url": self.url,
            "product_identity": self.product_identity.to_dict(),
            "intent": self.intent.to_dict(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BrowserEvidenceRequest":
        return cls(
            job_id=str(value.get("job_id") or ""),
            candidate_id=str(value.get("candidate_id") or ""),
            url=str(value.get("url") or ""),
            product_identity=ProductIdentityPayload(**dict(value.get("product_identity") or {})),
            intent=EvidenceIntent(**dict(value.get("intent") or {})),
        )


@dataclass(frozen=True, slots=True)
class BrowserActionRecord:
    step: int
    action: str
    target: str = ""
    result: str = "SUCCESS"
    detail: str = ""
    url_before: str = ""
    url_after: str = ""
    evidence_created: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VisualAsset:
    asset_id: str
    source_page_url: str
    local_path: str
    acquisition_method: AcquisitionMethod
    source_image_url: str | None = None
    browser_action: str = ""
    element_description: str = ""
    mime_type: str = ""
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    sha256: str = ""
    validated: bool = False
    vision_ready: bool = False
    notes: tuple[str, ...] = ()

    @property
    def path(self) -> Path:
        return Path(self.local_path)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["acquisition_method"] = self.acquisition_method.value
        return data

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VisualAsset":
        payload = dict(value)
        payload["acquisition_method"] = AcquisitionMethod(payload["acquisition_method"])
        payload["notes"] = tuple(payload.get("notes") or ())
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class BrowserEvidenceBundle:
    status: BrowserEvidenceStatus
    job_id: str
    candidate_id: str
    requested_url: str
    final_url: str | None
    browser_openable: bool
    rendered_product_verified: bool
    text_scrapable: bool
    gallery_discovered: bool
    direct_images_downloaded: int
    screenshots_captured: int
    multimodal_scrapable: bool
    page_title: str = ""
    visible_product_name: str = ""
    rendered_text: str = ""
    rendered_text_path: str | None = None
    final_html_path: str | None = None
    action_trace_path: str | None = None
    visual_manifest_path: str | None = None
    visual_assets: tuple[VisualAsset, ...] = ()
    actions: tuple[BrowserActionRecord, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "job_id": self.job_id,
            "candidate_id": self.candidate_id,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "browser_openable": self.browser_openable,
            "rendered_product_verified": self.rendered_product_verified,
            "text_scrapable": self.text_scrapable,
            "gallery_discovered": self.gallery_discovered,
            "direct_images_downloaded": self.direct_images_downloaded,
            "screenshots_captured": self.screenshots_captured,
            "multimodal_scrapable": self.multimodal_scrapable,
            "page_title": self.page_title,
            "visible_product_name": self.visible_product_name,
            "rendered_text": self.rendered_text,
            "rendered_text_path": self.rendered_text_path,
            "final_html_path": self.final_html_path,
            "action_trace_path": self.action_trace_path,
            "visual_manifest_path": self.visual_manifest_path,
            "visual_assets": [asset.to_dict() for asset in self.visual_assets],
            "actions": [action.to_dict() for action in self.actions],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "error": self.error,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BrowserEvidenceBundle":
        return cls(
            status=BrowserEvidenceStatus(str(value.get("status") or BrowserEvidenceStatus.FAILED.value)),
            job_id=str(value.get("job_id") or ""),
            candidate_id=str(value.get("candidate_id") or ""),
            requested_url=str(value.get("requested_url") or ""),
            final_url=value.get("final_url"),
            browser_openable=bool(value.get("browser_openable")),
            rendered_product_verified=bool(value.get("rendered_product_verified")),
            text_scrapable=bool(value.get("text_scrapable")),
            gallery_discovered=bool(value.get("gallery_discovered")),
            direct_images_downloaded=int(value.get("direct_images_downloaded") or 0),
            screenshots_captured=int(value.get("screenshots_captured") or 0),
            multimodal_scrapable=bool(value.get("multimodal_scrapable")),
            page_title=str(value.get("page_title") or ""),
            visible_product_name=str(value.get("visible_product_name") or ""),
            rendered_text=str(value.get("rendered_text") or ""),
            rendered_text_path=value.get("rendered_text_path"),
            final_html_path=value.get("final_html_path"),
            action_trace_path=value.get("action_trace_path"),
            visual_manifest_path=value.get("visual_manifest_path"),
            visual_assets=tuple(VisualAsset.from_mapping(item) for item in value.get("visual_assets") or ()),
            actions=tuple(BrowserActionRecord(**dict(item)) for item in value.get("actions") or ()),
            blockers=tuple(value.get("blockers") or ()),
            warnings=tuple(value.get("warnings") or ()),
            error=value.get("error"),
        )
