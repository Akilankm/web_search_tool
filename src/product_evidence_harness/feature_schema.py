from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class FeatureCriticality(str, Enum):
    CRITICAL = "critical"
    REQUIRED = "required"
    OPTIONAL = "optional"
    CONDITIONAL = "conditional"


class FeatureEvidenceStatus(str, Enum):
    STRUCTURED_FOUND = "STRUCTURED_FOUND"
    EXPLICITLY_FOUND = "EXPLICITLY_FOUND"
    LLM_FOUND = "LLM_FOUND"
    NOT_FOUND = "NOT_FOUND"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_id: str
    feature_name: str
    value_type: str = "text"
    criticality: FeatureCriticality = FeatureCriticality.REQUIRED
    allowed_values: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    preferred_sources: tuple[str, ...] = (
        "structured_data",
        "specification_table",
        "description",
    )
    description: str = ""

    def __post_init__(self) -> None:
        feature_id = str(self.feature_id or "").strip()
        feature_name = str(self.feature_name or "").strip()
        if not feature_id:
            raise ValueError("feature_id is required")
        if not feature_name:
            raise ValueError("feature_name is required")
        object.__setattr__(self, "feature_id", feature_id)
        object.__setattr__(self, "feature_name", feature_name)
        object.__setattr__(self, "allowed_values", tuple(str(v).strip() for v in self.allowed_values if str(v).strip()))
        aliases = [feature_name, *self.aliases]
        object.__setattr__(self, "aliases", tuple(dict.fromkeys(str(v).strip() for v in aliases if str(v).strip())))

    @classmethod
    def from_mapping(cls, record: Mapping[str, Any]) -> "FeatureDefinition":
        criticality_raw = str(record.get("criticality") or FeatureCriticality.REQUIRED.value).strip().lower()
        try:
            criticality = FeatureCriticality(criticality_raw)
        except ValueError:
            criticality = FeatureCriticality.REQUIRED

        def _tuple(value: Any) -> tuple[str, ...]:
            if value is None:
                return ()
            if isinstance(value, str):
                separator = "|" if "|" in value else ","
                return tuple(part.strip() for part in value.split(separator) if part.strip())
            if isinstance(value, Sequence):
                return tuple(str(part).strip() for part in value if str(part).strip())
            return (str(value).strip(),) if str(value).strip() else ()

        return cls(
            feature_id=str(record.get("feature_id") or record.get("id") or ""),
            feature_name=str(record.get("feature_name") or record.get("name") or ""),
            value_type=str(record.get("value_type") or "text"),
            criticality=criticality,
            allowed_values=_tuple(record.get("allowed_values")),
            aliases=_tuple(record.get("aliases") or record.get("search_terms")),
            preferred_sources=_tuple(record.get("preferred_sources")) or cls.__dataclass_fields__["preferred_sources"].default,
            description=str(record.get("description") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["criticality"] = self.criticality.value
        return data


@dataclass(frozen=True, slots=True)
class FeatureSchema:
    schema_id: str
    features: tuple[FeatureDefinition, ...]
    pg_name: str = ""
    required_coverage_threshold: float = 0.80

    def __post_init__(self) -> None:
        if not self.schema_id.strip():
            raise ValueError("schema_id is required")
        if not self.features:
            raise ValueError("feature schema must contain at least one feature")
        ids = [feature.feature_id for feature in self.features]
        if len(ids) != len(set(ids)):
            raise ValueError("feature_id values must be unique")
        threshold = max(0.0, min(1.0, float(self.required_coverage_threshold)))
        object.__setattr__(self, "required_coverage_threshold", threshold)

    @classmethod
    def from_records(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        schema_id: str,
        pg_name: str = "",
        required_coverage_threshold: float = 0.80,
    ) -> "FeatureSchema":
        return cls(
            schema_id=schema_id,
            pg_name=pg_name,
            required_coverage_threshold=required_coverage_threshold,
            features=tuple(FeatureDefinition.from_mapping(record) for record in records),
        )

    @property
    def critical_features(self) -> tuple[FeatureDefinition, ...]:
        return tuple(feature for feature in self.features if feature.criticality == FeatureCriticality.CRITICAL)

    @property
    def required_features(self) -> tuple[FeatureDefinition, ...]:
        return tuple(
            feature
            for feature in self.features
            if feature.criticality in {FeatureCriticality.CRITICAL, FeatureCriticality.REQUIRED}
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "pg_name": self.pg_name,
            "required_coverage_threshold": self.required_coverage_threshold,
            "features": [feature.to_dict() for feature in self.features],
        }


@dataclass(frozen=True, slots=True)
class FeatureEvidence:
    feature_id: str
    feature_name: str
    source_url: str
    value: Any = None
    status: FeatureEvidenceStatus = FeatureEvidenceStatus.NOT_FOUND
    confidence: float = 0.0
    evidence_text: str = ""
    evidence_location: str = ""
    extraction_method: str = ""
    notes: tuple[str, ...] = ()

    @property
    def supported(self) -> bool:
        return self.status in {
            FeatureEvidenceStatus.STRUCTURED_FOUND,
            FeatureEvidenceStatus.EXPLICITLY_FOUND,
            FeatureEvidenceStatus.LLM_FOUND,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True, slots=True)
class URLFeatureAssessment:
    url: str
    identity_accepted: bool
    identity_status: str
    source_role: str
    evidence: tuple[FeatureEvidence, ...]
    coverage: float
    required_coverage: float
    critical_coverage: float
    missing_features: tuple[str, ...] = ()
    conflicting_features: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    @property
    def supported_feature_ids(self) -> frozenset[str]:
        return frozenset(item.feature_id for item in self.evidence if item.supported)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "identity_accepted": self.identity_accepted,
            "identity_status": self.identity_status,
            "source_role": self.source_role,
            "coverage": self.coverage,
            "required_coverage": self.required_coverage,
            "critical_coverage": self.critical_coverage,
            "missing_features": list(self.missing_features),
            "conflicting_features": list(self.conflicting_features),
            "rejection_reasons": list(self.rejection_reasons),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class EvidenceSetDecision:
    primary_url: str | None
    supplementary_urls: tuple[str, ...]
    selected_urls: tuple[str, ...]
    coding_ready: bool
    status: str
    total_coverage: float
    required_coverage: float
    critical_coverage: float
    covered_features: tuple[str, ...]
    missing_features: tuple[str, ...]
    conflicting_features: tuple[str, ...]
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
