from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


class AgenticBrowserActionType(str, Enum):
    CLICK = "click"
    SCROLL = "scroll"
    INSPECT_IMAGE = "inspect_image"
    CAPTURE_SCREENSHOT = "capture_screenshot"
    FINISH = "finish"


@dataclass(frozen=True, slots=True)
class AgenticBrowserElement:
    element_id: str
    role: str
    text: str
    tag: str
    href: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AgenticBrowserElement":
        return cls(
            element_id=str(value.get("element_id") or ""),
            role=str(value.get("role") or ""),
            text=str(value.get("text") or ""),
            tag=str(value.get("tag") or ""),
            href=value.get("href"),
        )


@dataclass(frozen=True, slots=True)
class AgenticBrowserImage:
    asset_id: str
    element_id: str
    alt: str
    src: str
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AgenticBrowserImage":
        return cls(
            asset_id=str(value.get("asset_id") or ""),
            element_id=str(value.get("element_id") or ""),
            alt=str(value.get("alt") or ""),
            src=str(value.get("src") or ""),
            width=int(value.get("width") or 0),
            height=int(value.get("height") or 0),
        )


@dataclass(frozen=True, slots=True)
class AgenticBrowserObservation:
    session_id: str
    candidate_id: str
    url: str
    title: str
    visible_product_name: str
    visible_text: str
    interactive_elements: tuple[AgenticBrowserElement, ...]
    images: tuple[AgenticBrowserImage, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    action_count: int
    maximum_actions: int
    screenshot_path: str | None = None
    terminal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "candidate_id": self.candidate_id,
            "url": self.url,
            "title": self.title,
            "visible_product_name": self.visible_product_name,
            "visible_text": self.visible_text,
            "interactive_elements": [item.to_dict() for item in self.interactive_elements],
            "images": [item.to_dict() for item in self.images],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "action_count": self.action_count,
            "maximum_actions": self.maximum_actions,
            "screenshot_path": self.screenshot_path,
            "terminal": self.terminal,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AgenticBrowserObservation":
        return cls(
            session_id=str(value.get("session_id") or ""),
            candidate_id=str(value.get("candidate_id") or ""),
            url=str(value.get("url") or ""),
            title=str(value.get("title") or ""),
            visible_product_name=str(value.get("visible_product_name") or ""),
            visible_text=str(value.get("visible_text") or ""),
            interactive_elements=tuple(
                AgenticBrowserElement.from_mapping(item)
                for item in value.get("interactive_elements") or ()
            ),
            images=tuple(
                AgenticBrowserImage.from_mapping(item)
                for item in value.get("images") or ()
            ),
            blockers=tuple(value.get("blockers") or ()),
            warnings=tuple(value.get("warnings") or ()),
            action_count=int(value.get("action_count") or 0),
            maximum_actions=int(value.get("maximum_actions") or 0),
            screenshot_path=value.get("screenshot_path"),
            terminal=bool(value.get("terminal")),
        )


@dataclass(frozen=True, slots=True)
class AgenticBrowserAction:
    session_id: str
    action: AgenticBrowserActionType
    element_id: str | None = None
    direction: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "action": self.action.value,
            "element_id": self.element_id,
            "direction": self.direction,
            "reason": self.reason,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AgenticBrowserAction":
        return cls(
            session_id=str(value.get("session_id") or ""),
            action=AgenticBrowserActionType(str(value.get("action") or "")),
            element_id=(str(value.get("element_id")) if value.get("element_id") else None),
            direction=(str(value.get("direction")) if value.get("direction") else None),
            reason=str(value.get("reason") or ""),
        )
