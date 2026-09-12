"""Evaluate the local review pipeline against the fictional corpus."""

from __future__ import annotations

import argparse
import platform
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import cast

from check_document_types import (
    SampleDocument,
    load_manifest,
    normalized_document,
    source_metadata,
)
from pydantic import TypeAdapter, ValidationError

from app.accounting.catalog import get_northstar_gl_catalog, validate_gl_selection
from app.accounting.models import GLAccount, GLSuggestionResult
from app.config import Settings
from app.document_review.models import (
    CurrencyCode,
    DocumentClassificationResult,
    DocumentIssue,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    NormalizedFinancialDocument,
    PrimaryExtractionResult,
    ReviewState,
    VatId,
    VLMExtractionResult,
)
from app.invoices.repository import InvoiceReviewRepository, ReviewSnapshot
from app.invoices.service import InvoiceReviewService
from app.invoices.storage import LocalFileStorage
from app.invoices.validation import approval_allowed
from app.providers.paddleocr import PaddleOCRParser
from app.providers.qwen import QwenVLMProvider

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows.
    resource = None

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "samples/generated"
EXPECTED_DOCUMENTS = 13
EXPECTED_PAGES = 14
WARNING_ISSUE_CODES = {"purchase_order_missing"}
DOCUMENT_ADAPTER = TypeAdapter(NormalizedFinancialDocument)


class CountingPrimaryParser:
    """Count logical parser calls while delegating to the real adapter."""

    def __init__(self, delegate: PaddleOCRParser, calls: Counter[str]) -> None:
        self._delegate = delegate
        self._calls = calls

    def parse(self, **kwargs: object) -> PrimaryExtractionResult:
        self._calls["primary.parse"] += 1
        return self._delegate.parse(**kwargs)


class CountingVLMProvider:
    """Count logical VLM operations while delegating to the real provider."""

    def __init__(self, delegate: QwenVLMProvider, calls: Counter[str]) -> None:
        self._delegate = delegate
        self._calls = calls

    def classify_document(self, **kwargs: object) -> DocumentClassificationResult:
        self._calls["vlm.classify_document"] += 1
        return self._delegate.classify_document(**kwargs)

    def review_document(self, **kwargs: object) -> VLMExtractionResult:
        self._calls["vlm.review_document"] += 1
        return self._delegate.review_document(**kwargs)

    def suggest_gl(self, **kwargs: object) -> GLSuggestionResult:
        self._calls["vlm.suggest_gl"] += 1
        return self._delegate.suggest_gl(**kwargs)


@dataclass
class EvaluationResult:
    filename: str
    state: str
    duration_ms: int
    passed: bool
    classification: str | None
    classification_confidence: str | None
    classification_outcome: str
    page_count: int | None
    field_matches: int
    field_total: int
    field_mismatches: list[str]
    actual_issue_codes: list[str]
    expected_issue_codes: list[str]
    blocking_count: int
    warning_count: int
    approval_with_valid_gl: bool | None
    provenance_counts: Counter[str]
    minimum_primary_confidence: str | None
    provenance_errors: list[str]
    gl_account_id: str | None
    gl_account_valid: bool | None
    calls: dict[str, int]
    provider_metadata: list[str]
    failures: list[str]


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _counter_delta(before: Counter[str], after: Counter[str]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {key: after[key] - before[key] for key in sorted(keys) if after[key] != before[key]}


def _parse_issues(snapshot: ReviewSnapshot) -> list[DocumentIssue]:
    raw_issues = snapshot.issues
    if not isinstance(raw_issues, list):
        return []
    return [DocumentIssue.model_validate(issue) for issue in raw_issues]


def _parse_document(snapshot: ReviewSnapshot) -> NormalizedFinancialDocument | None:
    if snapshot.normalized is None:
        return None
    return DOCUMENT_ADAPTER.validate_python(snapshot.normalized)


def _compare_document(
    expected: NormalizedFinancialDocument,
    actual: NormalizedFinancialDocument | None,
) -> tuple[int, int, list[str]]:
    expected_fields = _normalized_field_values(expected)
    if actual is None:
        return 0, len(expected_fields), sorted(expected_fields)

    actual_fields = _normalized_field_values(actual)
    field_names = set(expected_fields) | set(actual_fields)
    mismatches = sorted(
        name for name in field_names if expected_fields.get(name) != actual_fields.get(name)
    )
    matches = len(expected_fields) - len([name for name in mismatches if name in expected_fields])
    return matches, len(expected_fields), mismatches


def _normalized_field_values(document: NormalizedFinancialDocument) -> dict[str, object]:
    values: dict[str, object] = {}
    for name in type(document.fields).model_fields:
        value = getattr(document.fields, name)
        if isinstance(value, CurrencyCode):
            values[name] = value.code
        elif isinstance(value, VatId):
            values[name] = value.normalized
        elif isinstance(value, date):
            values[name] = value.isoformat()
        elif isinstance(value, Decimal):
            values[name] = str(value)
        else:
            values[name] = value
    return values


def _classification_report(
    snapshot: ReviewSnapshot,
    actual: NormalizedFinancialDocument | None,
) -> tuple[str | None, str | None, str, list[str]]:
    failures: list[str] = []
    runs = _as_mapping(snapshot.provider_runs)
    classification_run = _as_mapping(runs.get("classification"))
    classification = _as_mapping(classification_run.get("classification"))
    document_type = classification.get("document_type")
    confidence = classification.get("confidence")
    classification_type = document_type if isinstance(document_type, str) else None
    confidence_text = str(confidence) if confidence is not None else None
    outcome = "missing"

    if classification_type is not None:
        outcome = "reported"
        if confidence is None:
            failures.append("classification confidence is missing")
        else:
            try:
                confidence_value = Decimal(str(confidence))
            except (InvalidOperation, ValueError):
                failures.append("classification confidence is not decimal")
            else:
                if not Decimal("0") <= confidence_value <= Decimal("1"):
                    failures.append("classification confidence is outside 0..1")

        if actual is not None and classification_type != actual.document_type:
            outcome = "disagreement"
            failures.append("classification disagrees with primary/normalized type")

    return classification_type, confidence_text, outcome, failures


def _provenance_report(
    raw_evidence: object,
    expected_field_names: set[str],
) -> tuple[Counter[str], list[str], list[str]]:
    counts: Counter[str] = Counter()
    confidence_values: list[str] = []
    failures: list[str] = []
    evidence = _as_mapping(raw_evidence)
    if not evidence:
        return counts, confidence_values, ["evidence is missing"]
    missing_fields = sorted(expected_field_names - set(evidence))
    if missing_fields:
        failures.append(f"evidence is missing for: {', '.join(missing_fields)}")

    for field_name, raw_field in evidence.items():
        try:
            field = FieldEvidence[object].model_validate(raw_field)
        except ValidationError:
            failures.append(f"invalid evidence for {field_name}")
            continue
        counts[field.status.value] += 1
        if field.source is EvidenceSource.PRIMARY and field.confidence is not None:
            confidence_values.append(str(field.confidence))
        if field.status is EvidenceStatus.CONFLICT and (
            field.primary_value is None or field.vlm_value is None
        ):
            failures.append(f"conflict evidence is incomplete for {field_name}")

    return counts, confidence_values, failures


def _provider_metadata(raw_runs: object) -> list[str]:
    metadata_lines: list[str] = []
    for stage, raw_run in _as_mapping(raw_runs).items():
        run = _as_mapping(raw_run)
        metadata = _as_mapping(run.get("provider_run")) if "provider_run" in run else run
        if not metadata.get("provider"):
            continue
        details = ", ".join(
            f"{name}={metadata[name]}"
            for name in (
                "provider",
                "model_name",
                "model_version",
                "runtime",
                "prompt_version",
                "schema_version",
                "duration_ms",
            )
            if metadata.get(name) is not None
        )
        metadata_lines.append(f"{stage}: {details}")
    return metadata_lines


def _gl_report(
    snapshot: ReviewSnapshot,
    catalog: tuple[GLAccount, ...],
) -> tuple[str | None, bool | None, list[str]]:
    failures: list[str] = []
    review = _as_mapping(snapshot.gl_review)
    suggestion = _as_mapping(review.get("suggestion"))
    account_id = suggestion.get("account_id")
    if not isinstance(account_id, str):
        return None, None, failures
    valid = account_id in {account.account_id for account in catalog}
    if not valid:
        failures.append("GL suggestion is not in the Northstar catalog")
    return account_id, valid, failures


def _evaluate_snapshot(
    sample: SampleDocument,
    snapshot: ReviewSnapshot,
    calls: dict[str, int],
    catalog: tuple[GLAccount, ...],
    duration_ms: int,
) -> EvaluationResult:
    failures: list[str] = []
    expected_document = normalized_document(sample)
    if snapshot.failure_message:
        failures.append(f"service failure: {snapshot.failure_message}")
    actual_document: NormalizedFinancialDocument | None = None
    try:
        actual_document = _parse_document(snapshot)
    except ValidationError:
        failures.append("normalized document is invalid")

    classification, classification_confidence, classification_outcome, classification_failures = (
        _classification_report(snapshot, actual_document)
    )
    failures.extend(classification_failures)
    if classification is None:
        failures.append("classification is missing")
    elif classification != sample.document_type.value:
        failures.append("classification does not match manifest")

    field_matches, field_total, field_mismatches = _compare_document(
        expected_document,
        actual_document,
    )
    if field_mismatches:
        failures.append(f"normalized field mismatch: {', '.join(field_mismatches)}")

    expected_page_count = sample.pages
    page_count = (
        actual_document.source.page_count
        if actual_document is not None
        else snapshot.page_count
    )
    if page_count != expected_page_count:
        failures.append(f"page count {page_count!r} != manifest {expected_page_count}")

    issues = _parse_issues(snapshot)
    actual_issue_codes = sorted(issue.code for issue in issues)
    expected_issue_codes = sorted(sample.expected_issue_codes)
    if actual_issue_codes != expected_issue_codes:
        failures.append(
            f"issue codes {actual_issue_codes!r} != manifest {expected_issue_codes!r}"
        )
    blocking_count = sum(issue.severity.value == "error" for issue in issues)
    warning_count = sum(issue.severity.value == "warning" for issue in issues)
    expected_blocking = bool(set(expected_issue_codes) - WARNING_ISSUE_CODES)
    if bool(blocking_count) != expected_blocking:
        failures.append("blocking outcome does not match manifest")

    approval_with_valid_gl: bool | None = None
    if snapshot.state is ReviewState.READY_FOR_REVIEW:
        approval_with_valid_gl = approval_allowed(
            issues,
            validate_gl_selection(catalog[0].account_id),
        )
        if approval_with_valid_gl != (not expected_blocking):
            failures.append("approval gate outcome does not match policy issues")
    else:
        failures.append(f"state is {snapshot.state.value}, expected ready_for_review")

    provenance_counts, primary_confidences, provenance_errors = _provenance_report(
        snapshot.evidence,
        set(type(expected_document.fields).model_fields),
    )
    failures.extend(provenance_errors)
    if primary_confidences:
        try:
            min_primary_confidence = min(Decimal(value) for value in primary_confidences)
        except InvalidOperation:
            failures.append("primary confidence is not decimal")
        else:
            if min_primary_confidence < Decimal("0") or min_primary_confidence > Decimal("1"):
                failures.append("primary confidence is outside 0..1")
    else:
        min_primary_confidence = None

    gl_account_id, gl_account_valid, gl_failures = _gl_report(snapshot, catalog)
    failures.extend(gl_failures)

    return EvaluationResult(
        filename=sample.filename,
        state=snapshot.state.value,
        duration_ms=duration_ms,
        passed=not failures,
        classification=classification,
        classification_confidence=classification_confidence,
        classification_outcome=classification_outcome,
        page_count=page_count,
        field_matches=field_matches,
        field_total=field_total,
        field_mismatches=field_mismatches,
        actual_issue_codes=actual_issue_codes,
        expected_issue_codes=expected_issue_codes,
        blocking_count=blocking_count,
        warning_count=warning_count,
        approval_with_valid_gl=approval_with_valid_gl,
        provenance_counts=provenance_counts,
        minimum_primary_confidence=(
            str(min_primary_confidence) if min_primary_confidence is not None else None
        ),
        provenance_errors=provenance_errors,
        gl_account_id=gl_account_id,
        gl_account_valid=gl_account_valid,
        calls=calls,
        provider_metadata=_provider_metadata(snapshot.provider_runs),
        failures=failures,
    )


def _failed_result(
    sample: SampleDocument,
    error: Exception,
    calls: dict[str, int],
    duration_ms: int,
) -> EvaluationResult:
    return EvaluationResult(
        filename=sample.filename,
        state="evaluator_error",
        duration_ms=duration_ms,
        passed=False,
        classification=None,
        classification_confidence=None,
        classification_outcome="unavailable",
        page_count=None,
        field_matches=0,
        field_total=len(type(normalized_document(sample).fields).model_fields),
        field_mismatches=[],
        actual_issue_codes=[],
        expected_issue_codes=sorted(sample.expected_issue_codes),
        blocking_count=0,
        warning_count=0,
        approval_with_valid_gl=None,
        provenance_counts=Counter(),
        minimum_primary_confidence=None,
        provenance_errors=[],
        gl_account_id=None,
        gl_account_valid=None,
        calls=calls,
        provider_metadata=[],
        failures=[f"provider/evaluator exception: {type(error).__name__}"],
    )


def _print_result(result: EvaluationResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    confidence = result.classification_confidence or "-"
    issue_codes = ",".join(result.actual_issue_codes) or "none"
    provenance = ",".join(
        f"{name}={result.provenance_counts[name]}"
        for name in ("primary", "vlm_fallback", "merged", "missing", "conflict")
        if result.provenance_counts[name]
    ) or "none"
    calls = ",".join(f"{name}={count}" for name, count in result.calls.items()) or "none"
    gl = result.gl_account_id or "none"
    gl_valid = "n/a" if result.gl_account_valid is None else str(result.gl_account_valid).lower()
    expected_issues = ",".join(result.expected_issue_codes) or "none"
    print(
        f"{status} {result.filename}: state={result.state}; "
        f"duration_ms={result.duration_ms}; "
        f"classification={result.classification or 'none'} "
        f"({confidence}, {result.classification_outcome}); "
        f"fields={result.field_matches}/{result.field_total}; pages={result.page_count!r}; "
        f"issues={issue_codes} (expected={expected_issues}); "
        f"blocking={result.blocking_count}; warnings={result.warning_count}; "
        f"approval_with_valid_gl={result.approval_with_valid_gl!r}; provenance={provenance}; "
        f"primary_confidence_min={result.minimum_primary_confidence or 'none'}; "
        f"gl={gl} valid={gl_valid}; calls={calls}"
    )
    for metadata in result.provider_metadata:
        print(f"  provider: {metadata}")
    if result.failures:
        print(f"  problems: {'; '.join(result.failures)}")


def _metadata_values(results: list[EvaluationResult], name: str) -> list[str]:
    prefix = f"{name}="
    values = {
        item.removeprefix(prefix)
        for result in results
        for metadata in result.provider_metadata
        for item in metadata.split(", ")
        if item.startswith(prefix)
    }
    return sorted(values)


def _peak_rss_mb() -> float | None:
    if resource is None:
        return None
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (AttributeError, OSError):
        return None
    if sys.platform == "darwin":
        return round(value / (1024 * 1024), 1)
    return round(value / 1024, 1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        dest="filenames",
        metavar="FILENAME",
        help="evaluate only this manifest filename; repeat for multiple documents",
    )
    return parser


def _selected_documents(
    parser: argparse.ArgumentParser,
    filenames: list[str] | None,
) -> list[SampleDocument]:
    documents = load_manifest()
    total_pages = sum(document.pages for document in documents)
    if len(documents) != EXPECTED_DOCUMENTS or total_pages != EXPECTED_PAGES:
        parser.error(
            f"manifest must contain {EXPECTED_DOCUMENTS} documents and {EXPECTED_PAGES} pages"
        )
    for document in documents:
        source_metadata(document)

    if not filenames:
        return documents
    known = {document.filename for document in documents}
    unknown = sorted(set(filenames) - known)
    if unknown:
        parser.error(f"unknown manifest filename(s): {', '.join(unknown)}")
    requested = set(filenames)
    return [document for document in documents if document.filename in requested]


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    documents = _selected_documents(parser, args.filenames)
    total_pages = sum(document.pages for document in documents)
    started = perf_counter()
    calls: Counter[str] = Counter()
    catalog = get_northstar_gl_catalog()

    print(
        f"Corpus evaluation: {len(documents)} document(s), {total_pages} page(s); "
        f"machine={platform.platform()}; arch={platform.machine()}"
    )

    with tempfile.TemporaryDirectory(prefix="invoice-review-eval-") as temp_dir:
        settings = Settings(invoice_review_data_dir=Path(temp_dir))
        repository = InvoiceReviewRepository(settings.database_path)
        repository.initialize()
        storage = LocalFileStorage(settings.uploads_dir)
        primary: CountingPrimaryParser | None = None
        vlm: CountingVLMProvider | None = None

        def primary_factory() -> PaddleOCRParser:
            nonlocal primary
            if primary is None:
                primary = CountingPrimaryParser(PaddleOCRParser(settings), calls)
            return cast(PaddleOCRParser, primary)

        def vlm_factory() -> QwenVLMProvider:
            nonlocal vlm
            if vlm is None:
                vlm = CountingVLMProvider(QwenVLMProvider(settings), calls)
            return cast(QwenVLMProvider, vlm)

        service = InvoiceReviewService(
            repository=repository,
            storage=storage,
            primary_parser_factory=primary_factory,
            vlm_provider_factory=vlm_factory,
        )
        print(
            f"Configuration: paddle_device={settings.paddleocr_device}; "
            f"vlm_runtime={settings.local_vlm_runtime}; vlm_model={settings.local_vlm_model}"
        )

        results: list[EvaluationResult] = []
        try:
            for sample in documents:
                before = calls.copy()
                document_started = perf_counter()
                try:
                    path = SAMPLE_DIR / sample.filename
                    content = path.read_bytes()
                    metadata = source_metadata(sample)
                    uploaded = service.upload_document(
                        original_filename=sample.filename,
                        media_type=metadata.media_type,
                        content=content,
                        uploaded_at=datetime.now(UTC),
                    )
                    snapshot = service.process_review(uploaded.review_id)
                    result = _evaluate_snapshot(
                        sample,
                        snapshot,
                        _counter_delta(before, calls),
                        catalog,
                        0,
                    )
                    result.duration_ms = int((perf_counter() - document_started) * 1000)
                except Exception as error:
                    result = _failed_result(
                        sample,
                        error,
                        _counter_delta(before, calls),
                        int((perf_counter() - document_started) * 1000),
                    )
                results.append(result)
                _print_result(result)
        finally:
            repository.close()

    passed = sum(result.passed for result in results)
    matched_fields = sum(result.field_matches for result in results)
    total_fields = sum(result.field_total for result in results)
    elapsed_ms = int((perf_counter() - started) * 1000)
    print(
        f"Summary: {passed}/{len(results)} passed; fields={matched_fields}/{total_fields}; "
        f"machine={platform.platform()}; arch={platform.machine()}; "
        f"device={settings.paddleocr_device}; runtime={settings.local_vlm_runtime}; "
        f"model={settings.local_vlm_model}; "
        f"prompt_versions={_metadata_values(results, 'prompt_version')}; "
        f"schema_versions={_metadata_values(results, 'schema_version')}; "
        f"total_duration_ms={elapsed_ms}; peak_rss_mb={_peak_rss_mb()!r}; "
        f"logical_provider_calls={dict(calls)}"
    )
    return 0 if results and passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
