from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape, unescape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from loguru import logger

from src.product_evidence_harness.contracts import ProductQuery
from src.product_evidence_harness.scraper import CrawlScraper


NETWORK_SCHEMES = {"http", "https"}


@dataclass(frozen=True)
class OfflineCaptureConfig:
    """Configuration for freezing a live product page into an offline artifact."""

    output_dir: Path = Path("outputs/offline_artifacts")
    request_timeout_seconds: int = 20
    max_assets: int = 120
    user_agent: str = "Mozilla/5.0 ProductEvidenceHarness/OfflineCapture"
    disable_scripts: bool = True
    disable_external_links: bool = True
    rewrite_stylesheet_urls: bool = True
    verify_no_network_bound_html: bool = True


@dataclass
class OfflineAssetRecord:
    source_url: str
    local_path: str
    rewritten_reference: str
    role: str
    content_type: str = ""
    status_code: Optional[int] = None
    byte_count: int = 0
    sha256: str = ""
    downloaded: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OfflineArtifactValidation:
    offline_html_exists: bool
    raw_html_exists: bool
    content_markdown_exists: bool
    structured_product_exists: bool
    asset_count: int
    downloaded_asset_count: int
    failed_asset_count: int
    network_bound_reference_count: int
    status: str
    reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "PRODUCTION_READY_OFFLINE_ARTIFACT"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ready"] = self.ready
        return data


@dataclass
class OfflineProductArtifact:
    source_url: str
    final_url: str
    artifact_dir: str
    offline_html_path: str
    raw_html_path: str
    clean_html_path: str
    content_markdown_path: str
    structured_product_path: str
    manifest_path: str
    asset_map_path: str
    validation_path: str
    status: str
    validation: OfflineArtifactValidation
    assets: list[OfflineAssetRecord] = field(default_factory=list)

    @property
    def offline_artifact_ready(self) -> bool:
        return self.validation.ready

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["offline_artifact_ready"] = self.offline_artifact_ready
        return data


class LivePageOfflineArtifactBuilder:
    """Freeze one validated product URL into a reproducible offline evidence artifact.

    The generated artifact is designed to become the downstream source of truth:
    product coding should consume the local files instead of revisiting the live
    retailer page.
    """

    _ASSET_ATTR_PATTERN = re.compile(
        r"(?P<prefix><(?P<tag>[a-zA-Z0-9:-]+)\b(?P<before>[^>]*?)\s(?P<attr>src|href|poster)=['\"])(?P<url>[^'\"]+)(?P<suffix>['\"])",
        flags=re.I | re.S,
    )
    _SRCSET_ATTR_PATTERN = re.compile(
        r"(?P<prefix><(?P<tag>[a-zA-Z0-9:-]+)\b(?P<before>[^>]*?)\ssrcset=['\"])(?P<srcset>[^'\"]+)(?P<suffix>['\"])",
        flags=re.I | re.S,
    )
    _CSS_URL_PATTERN = re.compile(r"url\((?P<quote>['\"]?)(?P<url>[^)'\"\s]+)(?P=quote)\)", flags=re.I)

    def __init__(self, config: OfflineCaptureConfig | None = None, session: requests.Session | None = None) -> None:
        self.config = config or OfflineCaptureConfig()
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})
        self._asset_records: dict[str, OfflineAssetRecord] = {}
        self._asset_counter = 0

    def capture_url(
        self,
        url: str,
        *,
        artifact_dir: str | Path | None = None,
        product: ProductQuery | None = None,
        row_id: str | None = None,
        rendered_html: str | None = None,
    ) -> OfflineProductArtifact:
        """Capture a live URL or supplied rendered HTML into an offline artifact.

        `rendered_html` is useful when a browser/crawl4ai stage has already
        produced the final DOM. When it is absent, this builder fetches the URL
        once with requests and freezes the returned HTML.
        """

        if not url:
            raise ValueError("url is required for offline capture")

        self._asset_records = {}
        self._asset_counter = 0

        artifact_root = self._resolve_artifact_dir(url=url, artifact_dir=artifact_dir, row_id=row_id or (product.row_id if product else None))
        live_dir = artifact_root / "live_capture"
        product_dir = artifact_root / "product_data"
        offline_dir = artifact_root / "offline"
        validation_dir = artifact_root / "validation"
        asset_dir = offline_dir / "assets"

        for directory in (live_dir, product_dir, offline_dir, validation_dir, asset_dir):
            directory.mkdir(parents=True, exist_ok=True)

        fetch_meta: dict[str, Any]
        if rendered_html is None:
            raw_html, final_url, fetch_meta = self._fetch_html(url)
        else:
            raw_html = rendered_html
            final_url = url
            fetch_meta = {
                "source": "provided_rendered_html",
                "status_code": None,
                "final_url": final_url,
                "headers": {},
            }

        (live_dir / "raw.html").write_text(raw_html, encoding="utf-8")
        (live_dir / "rendered.html").write_text(raw_html, encoding="utf-8")

        clean_html = self._remove_network_primitives(raw_html)
        offline_html = self._rewrite_html_to_offline(clean_html, base_url=final_url, offline_dir=offline_dir, asset_dir=asset_dir)
        offline_html = self._inject_offline_head(offline_html, source_url=url, final_url=final_url)

        clean_path = live_dir / "rendered_clean.html"
        offline_html_path = offline_dir / "offline_page.html"
        clean_path.write_text(clean_html, encoding="utf-8")
        offline_html_path.write_text(offline_html, encoding="utf-8")

        page_text = self._html_to_text(raw_html)
        (live_dir / "page_text.txt").write_text(page_text, encoding="utf-8")
        content_md_path = product_dir / "content.md"
        content_md_path.write_text(self._build_content_markdown(page_text, source_url=url, final_url=final_url), encoding="utf-8")

        structured_path = product_dir / "structured_product.json"
        structured_path.write_text(
            json.dumps(self._build_structured_product(url=url, final_url=final_url, html=raw_html, markdown=page_text, product=product), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        asset_map_path = offline_dir / "asset_map.json"
        assets = list(self._asset_records.values())
        asset_map_path.write_text(
            json.dumps({record.source_url: record.to_dict() for record in assets}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        validation = self._validate_artifact(
            artifact_root=artifact_root,
            offline_html_path=offline_html_path,
            raw_html_path=live_dir / "raw.html",
            content_markdown_path=content_md_path,
            structured_product_path=structured_path,
            assets=assets,
        )

        validation_path = validation_dir / "offline_artifact_validation.json"
        validation_path.write_text(json.dumps(validation.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        manifest_path = artifact_root / "offline_artifact_manifest.json"
        manifest = {
            "schema_version": "offline-product-artifact/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_url": url,
            "final_url": final_url,
            "artifact_dir": str(artifact_root),
            "status": validation.status,
            "offline_artifact_ready": validation.ready,
            "network_policy": {
                "scripts_disabled": self.config.disable_scripts,
                "external_links_disabled": self.config.disable_external_links,
                "content_security_policy": "connect-src 'none'; script-src 'none'",
            },
            "fetch": fetch_meta,
            "paths": {
                "raw_html": str(live_dir / "raw.html"),
                "rendered_html": str(live_dir / "rendered.html"),
                "clean_html": str(clean_path),
                "offline_html": str(offline_html_path),
                "content_markdown": str(content_md_path),
                "structured_product": str(structured_path),
                "asset_map": str(asset_map_path),
                "validation": str(validation_path),
            },
            "asset_count": len(assets),
            "downloaded_asset_count": sum(1 for asset in assets if asset.downloaded),
            "failed_asset_count": sum(1 for asset in assets if not asset.downloaded),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        return OfflineProductArtifact(
            source_url=url,
            final_url=final_url,
            artifact_dir=str(artifact_root),
            offline_html_path=str(offline_html_path),
            raw_html_path=str(live_dir / "raw.html"),
            clean_html_path=str(clean_path),
            content_markdown_path=str(content_md_path),
            structured_product_path=str(structured_path),
            manifest_path=str(manifest_path),
            asset_map_path=str(asset_map_path),
            validation_path=str(validation_path),
            status=validation.status,
            validation=validation,
            assets=assets,
        )

    def _resolve_artifact_dir(self, *, url: str, artifact_dir: str | Path | None, row_id: str | None) -> Path:
        if artifact_dir:
            return Path(artifact_dir)
        parsed = urlparse(url)
        safe_row = self._safe_name(row_id or parsed.netloc or "product")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return Path(self.config.output_dir) / safe_row / stamp

    def _fetch_html(self, url: str) -> tuple[str, str, dict[str, Any]]:
        logger.info("Capturing live page for offline artifact | url={}", url)
        response = self.session.get(url, timeout=self.config.request_timeout_seconds)
        response.raise_for_status()
        html = response.text or ""
        return html, response.url, {
            "source": "requests",
            "status_code": response.status_code,
            "final_url": response.url,
            "headers": dict(response.headers),
            "byte_count": len(response.content or b""),
        }

    def _remove_network_primitives(self, html: str) -> str:
        output = html or ""

        output = re.sub(
            r"(<form\b[^>]*?)\saction=['\"][^'\"]+['\"]",
            lambda m: f'{m.group(1)} data-offline-action-disabled="true"',
            output,
            flags=re.I | re.S,
        )

        if self.config.disable_scripts:
            output = re.sub(
                r"<script\b([^>]*)\bsrc=['\"]([^'\"]+)['\"]([^>]*)>\s*</script>",
                lambda m: (
                    f"<script type=\"application/json\" data-offline-disabled=\"external-script\" "
                    f"data-offline-src=\"{escape(m.group(2), quote=True)}\"></script>"
                ),
                output,
                flags=re.I | re.S,
            )
            output = re.sub(
                r"<script\b(?![^>]*application/ld\+json)([^>]*)>.*?</script>",
                r"<script type=\"application/json\" data-offline-disabled=\"inline-script\"></script>",
                output,
                flags=re.I | re.S,
            )

        return output

    def _rewrite_html_to_offline(self, html: str, *, base_url: str, offline_dir: Path, asset_dir: Path) -> str:
        html = self._rewrite_srcsets(html, base_url=base_url, offline_dir=offline_dir, asset_dir=asset_dir)
        return self._ASSET_ATTR_PATTERN.sub(
            lambda match: self._rewrite_asset_attribute(match, base_url=base_url, offline_dir=offline_dir, asset_dir=asset_dir),
            html,
        )

    def _rewrite_srcsets(self, html: str, *, base_url: str, offline_dir: Path, asset_dir: Path) -> str:
        def repl(match: re.Match[str]) -> str:
            tag = match.group("tag").lower()
            srcset = match.group("srcset") or ""
            rewritten_parts: list[str] = []
            for part in srcset.split(","):
                tokens = part.strip().split()
                if not tokens:
                    continue
                asset_url = tokens[0]
                suffix = " ".join(tokens[1:])
                local_ref = self._download_and_reference(asset_url, base_url=base_url, offline_dir=offline_dir, asset_dir=asset_dir, role=f"{tag}.srcset")
                rewritten_parts.append(" ".join(x for x in [local_ref or asset_url, suffix] if x))
            return f"{match.group('prefix')}{', '.join(rewritten_parts)}{match.group('suffix')}"
        return self._SRCSET_ATTR_PATTERN.sub(repl, html)

    def _rewrite_asset_attribute(self, match: re.Match[str], *, base_url: str, offline_dir: Path, asset_dir: Path) -> str:
        tag = match.group("tag").lower()
        before = match.group("before") or ""
        attr = match.group("attr").lower()
        raw_url = match.group("url")
        prefix = match.group("prefix")
        suffix = match.group("suffix")

        if tag == "a" and attr == "href" and self.config.disable_external_links:
            absolute = urljoin(base_url, raw_url)
            if self._is_network_url(absolute):
                return (
                    f"<{tag}{before} href=\"#offline-link-disabled\" "
                    f"data-offline-href=\"{escape(absolute, quote=True)}\""
                )

        should_download = self._should_download_tag_asset(tag=tag, attr=attr, before=before, url=raw_url)
        if not should_download:
            return match.group(0)

        local_ref = self._download_and_reference(raw_url, base_url=base_url, offline_dir=offline_dir, asset_dir=asset_dir, role=f"{tag}.{attr}")
        if not local_ref:
            return match.group(0)

        return f"{prefix}{local_ref}{suffix}"

    def _should_download_tag_asset(self, *, tag: str, attr: str, before: str, url: str) -> bool:
        if not url or url.startswith("#"):
            return False
        if tag == "link" and attr == "href":
            rel_text = before.lower()
            return any(key in rel_text for key in ["stylesheet", "icon", "preload", "apple-touch-icon"])
        if tag in {"img", "source", "picture", "video", "audio", "iframe", "embed", "object"}:
            return True
        if tag == "script" and not self.config.disable_scripts:
            return True
        return attr in {"src", "poster"}

    def _download_and_reference(self, raw_url: str, *, base_url: str, offline_dir: Path, asset_dir: Path, role: str) -> str:
        absolute_url = urljoin(base_url, raw_url)
        parsed = urlparse(absolute_url)
        if parsed.scheme and parsed.scheme.lower() not in NETWORK_SCHEMES:
            return raw_url
        if not parsed.netloc:
            return raw_url

        if absolute_url in self._asset_records:
            return self._asset_records[absolute_url].rewritten_reference

        if len(self._asset_records) >= self.config.max_assets:
            record = OfflineAssetRecord(
                source_url=absolute_url,
                local_path="",
                rewritten_reference=raw_url,
                role=role,
                downloaded=False,
                error="max_assets_reached",
            )
            self._asset_records[absolute_url] = record
            return raw_url

        self._asset_counter += 1
        extension_hint = Path(parsed.path).suffix[:12]
        asset_subdir = asset_dir / self._role_directory(role)
        asset_subdir.mkdir(parents=True, exist_ok=True)

        try:
            response = self.session.get(absolute_url, timeout=self.config.request_timeout_seconds)
            content = response.content or b""
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            ext = self._extension_for_asset(extension_hint, content_type, role)
            filename = f"asset_{self._asset_counter:04d}{ext}"
            local_path = asset_subdir / filename
            local_path.write_bytes(content)

            if self.config.rewrite_stylesheet_urls and self._is_css_asset(role, content_type, ext):
                css_text = content.decode(response.encoding or "utf-8", errors="replace")
                css_text = self._rewrite_css_urls(css_text, css_url=absolute_url, offline_dir=offline_dir, asset_dir=asset_dir, css_file_path=local_path)
                local_path.write_text(css_text, encoding="utf-8")

            rel_ref = self._relative_reference(offline_dir, local_path)
            record = OfflineAssetRecord(
                source_url=absolute_url,
                local_path=str(local_path),
                rewritten_reference=rel_ref,
                role=role,
                content_type=content_type,
                status_code=response.status_code,
                byte_count=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                downloaded=response.ok,
                error=None if response.ok else f"http_status_{response.status_code}",
            )
            self._asset_records[absolute_url] = record
            return rel_ref
        except Exception as exc:
            logger.warning("Failed to download offline asset | url={} | error={}", absolute_url, exc)
            record = OfflineAssetRecord(
                source_url=absolute_url,
                local_path="",
                rewritten_reference=raw_url,
                role=role,
                downloaded=False,
                error=str(exc),
            )
            self._asset_records[absolute_url] = record
            return raw_url

    def _rewrite_css_urls(self, css_text: str, *, css_url: str, offline_dir: Path, asset_dir: Path, css_file_path: Path) -> str:
        def repl(match: re.Match[str]) -> str:
            raw = match.group("url")
            if raw.startswith("data:") or raw.startswith("#"):
                return match.group(0)
            ref = self._download_and_reference(raw, base_url=css_url, offline_dir=offline_dir, asset_dir=asset_dir, role="css.url")
            if ref and not ref.startswith(("http://", "https://", "data:")):
                target = (offline_dir / ref).resolve()
                ref = self._relative_reference(css_file_path.parent, target)
            return f"url('{ref}')"
        return self._CSS_URL_PATTERN.sub(repl, css_text or "")

    def _validate_artifact(
        self,
        *,
        artifact_root: Path,
        offline_html_path: Path,
        raw_html_path: Path,
        content_markdown_path: Path,
        structured_product_path: Path,
        assets: list[OfflineAssetRecord],
    ) -> OfflineArtifactValidation:
        reasons: list[str] = []
        offline_exists = offline_html_path.exists() and offline_html_path.stat().st_size > 0
        raw_exists = raw_html_path.exists() and raw_html_path.stat().st_size > 0
        content_exists = content_markdown_path.exists() and content_markdown_path.stat().st_size > 0
        structured_exists = structured_product_path.exists() and structured_product_path.stat().st_size > 0
        network_refs = self._count_network_bound_references(offline_html_path)

        if not offline_exists:
            reasons.append("offline_page_missing_or_empty")
        if not raw_exists:
            reasons.append("raw_html_missing_or_empty")
        if not content_exists:
            reasons.append("content_markdown_missing_or_empty")
        if not structured_exists:
            reasons.append("structured_product_missing_or_empty")
        if self.config.verify_no_network_bound_html and network_refs:
            reasons.append(f"network_bound_references_remaining={network_refs}")

        failed_assets = sum(1 for asset in assets if not asset.downloaded)
        status = "PRODUCTION_READY_OFFLINE_ARTIFACT" if not reasons else "OFFLINE_ARTIFACT_NEEDS_REVIEW"

        return OfflineArtifactValidation(
            offline_html_exists=offline_exists,
            raw_html_exists=raw_exists,
            content_markdown_exists=content_exists,
            structured_product_exists=structured_exists,
            asset_count=len(assets),
            downloaded_asset_count=sum(1 for asset in assets if asset.downloaded),
            failed_asset_count=failed_assets,
            network_bound_reference_count=network_refs,
            status=status,
            reasons=reasons,
        )

    def _count_network_bound_references(self, html_path: Path) -> int:
        if not html_path.exists():
            return 0
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        count = 0
        attr_pattern = re.compile(r"(?<!data-offline-)\b(?:src|href|poster|action|srcset)=['\"]([^'\"]+)['\"]", flags=re.I)
        for match in attr_pattern.finditer(html):
            value = unescape(match.group(1)).strip()
            if value.startswith(("http://", "https://", "//")):
                count += 1
        count += len(re.findall(r"url\(['\"]?(?:https?:)?//", html, flags=re.I))
        return count

    def _build_structured_product(self, *, url: str, final_url: str, html: str, markdown: str, product: ProductQuery | None) -> dict[str, Any]:
        scraper = CrawlScraper(static_fetch_first=False)
        try:
            result = scraper._build_result(
                url=url,
                final_url=final_url,
                status_code=200,
                success=True,
                markdown=markdown,
                html=html,
                product=product,
                error=None,
            )
            data = result.to_dict()
        except Exception as exc:
            logger.warning("Structured product extraction from offline capture failed | url={} | error={}", url, exc)
            data = {"url": url, "final_url": final_url, "error": str(exc)}
        data["offline_source"] = True
        return data

    def _build_content_markdown(self, text: str, *, source_url: str, final_url: str) -> str:
        title = ""
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if lines:
            title = lines[0][:160]
        return "\n".join(
            [
                "# Offline Product Evidence",
                "",
                f"- Source URL: `{source_url}`",
                f"- Final URL: `{final_url}`",
                f"- Captured title/text signal: `{title}`",
                "",
                "## Page text",
                "",
                text[:30000],
                "",
            ]
        )

    def _inject_offline_head(self, html: str, *, source_url: str, final_url: str) -> str:
        csp = (
            "default-src 'self' data: blob:; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "script-src 'none'; "
            "connect-src 'none'; "
            "frame-src 'none'; "
            "form-action 'none';"
        )
        banner = (
            "<meta charset=\"utf-8\">"
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"{escape(csp, quote=True)}\">"
            "<style>"
            ".offline-capture-banner{position:sticky;top:0;z-index:2147483647;"
            "background:#fff3cd;border:1px solid #ffeeba;padding:8px 12px;"
            "font:14px Arial,sans-serif;color:#533f03}"
            "</style>"
            f"<div class=\"offline-capture-banner\">Offline product artifact. Source: "
            f"{escape(source_url)} | Final URL: {escape(final_url)}. "
            "Live scripts, forms, and external links are disabled.</div>"
        )
        if re.search(r"<head[^>]*>", html or "", flags=re.I):
            return re.sub(r"<head([^>]*)>", lambda m: f"<head{m.group(1)}>{banner}", html, count=1, flags=re.I)
        if re.search(r"<html[^>]*>", html or "", flags=re.I):
            return re.sub(r"<html([^>]*)>", lambda m: f"<html{m.group(1)}><head>{banner}</head>", html, count=1, flags=re.I)
        return f"<!doctype html><html><head>{banner}</head><body>{html or ''}</body></html>"

    def _extension_for_asset(self, extension_hint: str, content_type: str, role: str) -> str:
        if extension_hint and re.match(r"^\.[A-Za-z0-9]{1,8}$", extension_hint):
            return extension_hint
        guessed = mimetypes.guess_extension(content_type or "")
        if guessed:
            return guessed
        if "css" in role:
            return ".css"
        if "img" in role or "image" in role or "srcset" in role:
            return ".bin"
        return ".asset"

    def _role_directory(self, role: str) -> str:
        if "css" in role or "stylesheet" in role:
            return "css"
        if any(key in role for key in ["img", "image", "srcset", "poster", "source"]):
            return "images"
        if "icon" in role:
            return "images"
        if "font" in role:
            return "fonts"
        return "other"

    def _is_css_asset(self, role: str, content_type: str, ext: str) -> bool:
        return "css" in role or content_type == "text/css" or ext == ".css"

    def _relative_reference(self, from_dir: Path, to_path: Path) -> str:
        try:
            return Path(to_path).resolve().relative_to(Path(from_dir).resolve()).as_posix()
        except Exception:
            import os

            return os.path.relpath(str(to_path), start=str(from_dir)).replace("\\", "/")

    def _html_to_text(self, html: str) -> str:
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html or "", flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = unescape(text)
        return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()

    def _safe_name(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value or "artifact").strip("_")[:120] or "artifact"

    def _is_network_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme.lower() in NETWORK_SCHEMES or value.startswith("//")
