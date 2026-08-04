#!/usr/bin/env python3
"""Run the pre-registered M5 retrieval-role model calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from fire_m5_retrieval_roles import (  # noqa: E402
    aggregate_annotation_report,
    build_silver_role_evidence,
)
from run_fire_m5_retrieval_ab import (  # noqa: E402
    EMPTY_COUNT,
    PROCEED_COUNT,
    TARGET_COUNT,
    build_view_sources,
    evaluate_model_role_views,
    load_experiment_sources,
    role_gate_failure_codes,
)
from treeguard.ai_review import (  # noqa: E402
    PROVIDER_NAME,
    RETRIEVAL_ROLE_PROMPT_VERSION,
    RETRIEVAL_ROLE_RETRY_CODES,
    BailianConfig,
    BailianProviderError,
    BailianRetrievalRoleProvider,
    build_retrieval_role_request_body,
)
from treeguard.retrieval_roles import RetrievalRoleEvidence  # noqa: E402


REPORT_VERSION = "fire-m5-retrieval-role-model-report.v1"
PURPOSE = "M5_EXPOSED_RETRIEVAL_ROLE_MODEL_CALIBRATION_ONLY"
FIXTURE_DIR = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow"
Transport = Callable[[dict[str, Any]], Any]


class RoleModelExperimentError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def wire_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _request_allowlist(request: Any, model: str) -> frozenset[str]:
    bodies = [build_retrieval_role_request_body(request, model)]
    bodies.extend(
        build_retrieval_role_request_body(request, model, retry_code=code)
        for code in sorted(RETRIEVAL_ROLE_RETRY_CODES)
    )
    return frozenset(
        hashlib.sha256(wire_bytes(body)).hexdigest() for body in bodies
    )


class PlannedRoleProvider(BailianRetrievalRoleProvider):
    """Reject unplanned or leaking request bytes before transport."""

    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: frozenset[str],
        forbidden_values: frozenset[str],
        audit: list[str],
        validation_codes: list[str],
        *,
        transport: Transport | None = None,
    ) -> None:
        super().__init__(config, trace_sink=self._capture_trace)
        self.allowed_hashes = allowed_hashes
        self.forbidden_values = forbidden_values
        self.audit = audit
        self.validation_codes = validation_codes
        self.transport = transport

    def _capture_trace(self, trace: Any) -> None:
        if (
            trace.validation_status == "FAILED"
            and isinstance(trace.validation_error_code, str)
        ):
            self.validation_codes.append(trace.validation_error_code)

    def _post_json(self, body: dict[str, Any]) -> Any:
        encoded = wire_bytes(body)
        text = encoded.decode("utf-8")
        if any(value and value in text for value in self.forbidden_values):
            raise RoleModelExperimentError("ROLE_MODEL_INPUT_LEAK")
        digest = hashlib.sha256(encoded).hexdigest()
        if digest not in self.allowed_hashes:
            raise RoleModelExperimentError("ROLE_MODEL_BODY_NOT_PLANNED")
        if len(self.audit) >= 2:
            raise RoleModelExperimentError("ROLE_MODEL_UNIT_CALL_LIMIT_EXCEEDED")
        self.audit.append(digest)
        if self.transport is not None:
            return self.transport(body)
        return super()._post_json(body)


def _validate_tls_trust() -> None:
    try:
        roots = ssl.create_default_context().get_ca_certs()
    except (OSError, ssl.SSLError):
        raise RoleModelExperimentError("ROLE_MODEL_TLS_TRUST_UNAVAILABLE") from None
    if not roots:
        raise RoleModelExperimentError("ROLE_MODEL_TLS_TRUST_UNAVAILABLE")


def _span_agreement(
    model_by_ref: dict[str, RetrievalRoleEvidence],
    silver_by_ref: dict[str, RetrievalRoleEvidence],
) -> dict[str, Any]:
    exact_case_count = 0
    model_span_count = 0
    silver_span_count = 0
    matching_span_count = 0
    missing_role_counts: Counter[str] = Counter()
    extra_role_counts: Counter[str] = Counter()
    difference_kind_counts: Counter[str] = Counter()
    case_difference_counts: Counter[str] = Counter()
    missing_target_case_count = 0
    for scenario_ref, silver in silver_by_ref.items():
        model = model_by_ref.get(scenario_ref)
        if model is None:
            silver_span_count += len(silver.spans)
            missing_role_counts.update(span.role for span in silver.spans)
            case_difference_counts["ONLY_MISSING"] += 1
            missing_target_case_count += any(
                span.role == "TARGET" for span in silver.spans
            )
            continue
        model_spans = {
            (span.role, span.text, span.start, span.end) for span in model.spans
        }
        silver_spans = {
            (span.role, span.text, span.start, span.end) for span in silver.spans
        }
        exact_case_count += model_spans == silver_spans
        model_span_count += len(model_spans)
        silver_span_count += len(silver_spans)
        matching_span_count += len(model_spans & silver_spans)
        missing = silver_spans - model_spans
        extra = model_spans - silver_spans
        missing_role_counts.update(item[0] for item in missing)
        extra_role_counts.update(item[0] for item in extra)
        missing_target_case_count += any(item[0] == "TARGET" for item in missing)
        if not missing and not extra:
            case_difference_counts["EXACT"] += 1
        elif missing and extra:
            case_difference_counts["MISSING_AND_EXTRA"] += 1
        elif missing:
            case_difference_counts["ONLY_MISSING"] += 1
        else:
            case_difference_counts["ONLY_EXTRA"] += 1
        for missing_span in missing:
            role, text, start, end = missing_span
            if any(
                other_text == text
                and other_start == start
                and other_end == end
                and other_role != role
                for other_role, other_text, other_start, other_end in extra
            ):
                difference_kind_counts["SAME_TEXT_WRONG_ROLE"] += 1
            elif any(
                other_role == role
                and other_start <= start
                and other_end >= end
                for other_role, _, other_start, other_end in extra
            ):
                difference_kind_counts["MODEL_SUPERSPAN"] += 1
            elif any(
                other_role == role
                and other_start >= start
                and other_end <= end
                for other_role, _, other_start, other_end in extra
            ):
                difference_kind_counts["MODEL_SUBSPAN"] += 1
            else:
                difference_kind_counts["OTHER_MISSING"] += 1
    return {
        "exact_case_count": exact_case_count,
        "model_span_count": model_span_count,
        "silver_span_count": silver_span_count,
        "matching_span_count": matching_span_count,
        "precision_scaled_1e6": (
            matching_span_count * 1_000_000 // model_span_count
            if model_span_count
            else 0
        ),
        "recall_scaled_1e6": (
            matching_span_count * 1_000_000 // silver_span_count
            if silver_span_count
            else 0
        ),
        "missing_target_case_count": missing_target_case_count,
        "missing_role_counts": dict(sorted(missing_role_counts.items())),
        "extra_role_counts": dict(sorted(extra_role_counts.items())),
        "case_difference_counts": dict(sorted(case_difference_counts.items())),
        "difference_kind_counts": dict(
            sorted(difference_kind_counts.items())
        ),
    }


def run_experiment(
    fixture_dir: Path,
    config: BailianConfig,
    *,
    transport: Transport | None = None,
    downstream_algorithm: str = "R1",
) -> dict[str, Any]:
    if downstream_algorithm not in {"R1", "R2"}:
        raise RoleModelExperimentError("ROLE_MODEL_DOWNSTREAM_ALGORITHM_INVALID")
    formal, oracle_by_ref, tree, branch_refs = load_experiment_sources(fixture_dir)
    forbidden_values = frozenset(node.node_id for node in tree.nodes)
    model_by_ref: dict[str, RetrievalRoleEvidence] = {}
    silver_by_ref: dict[str, RetrievalRoleEvidence] = {}
    validation_codes: list[str] = []
    final_failure_codes: list[str] = []
    actual_call_count = 0
    first_pass_count = 0
    transport_failure_count = 0
    for scenario in formal:
        scenario_ref = scenario["scenario_ref"]
        request, _, _ = build_view_sources(
            scenario,
            oracle_by_ref[scenario_ref],
            tree,
            branch_refs,
            "V_REQUIREMENT_ONLY",
        )
        silver_by_ref[scenario_ref] = build_silver_role_evidence(
            scenario, request
        )
        audit: list[str] = []
        provider = PlannedRoleProvider(
            config,
            _request_allowlist(request, config.model),
            forbidden_values,
            audit,
            validation_codes,
            transport=transport,
        )
        try:
            evidence = provider.extract_roles(request)
        except (BailianProviderError, RoleModelExperimentError) as exc:
            code = exc.code
            final_failure_codes.append(code)
            if not code.startswith("ROLE_MODEL_"):
                transport_failure_count += 1
        else:
            model_by_ref[scenario_ref] = evidence
            first_pass_count += len(audit) == 1
        actual_call_count += len(audit)

    contract_success_count = len(model_by_ref)
    failure_codes = []
    if contract_success_count != PROCEED_COUNT:
        failure_codes.append("ROLE_EXTRACTION_FINAL_CONTRACT_BELOW_MINIMUM")
    if first_pass_count < 16:
        failure_codes.append("ROLE_EXTRACTION_FIRST_PASS_BELOW_MINIMUM")
    if transport_failure_count:
        failure_codes.append("ROLE_EXTRACTION_TRANSPORT_FAILURE")
    if actual_call_count < PROCEED_COUNT or actual_call_count > 20:
        failure_codes.append("ROLE_EXTRACTION_CALL_BUDGET_INVALID")

    views: dict[str, dict[str, Any]] = {}
    downstream_status = "NOT_RUN"
    if contract_success_count == PROCEED_COUNT:
        views = evaluate_model_role_views(
            fixture_dir,
            model_by_ref,
            algorithm=downstream_algorithm,
        )
        downstream_status = "COMPLETED"
        failure_codes.extend(
            role_gate_failure_codes(
                views,
                prefix=f"RETRIEVAL_ROLE_MODEL_{downstream_algorithm}",
            )
        )

    return {
        "report_version": REPORT_VERSION,
        "purpose": PURPOSE,
        "status": "PASS" if not failure_codes else "FAIL",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "calibration_only": True,
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "production_qualification": False,
        "provider": PROVIDER_NAME,
        "model": config.model,
        "prompt_version": RETRIEVAL_ROLE_PROMPT_VERSION,
        "downstream_algorithm": downstream_algorithm,
        "llm_called": actual_call_count > 0,
        "execution_proceed_count": PROCEED_COUNT,
        "target_count": TARGET_COUNT,
        "empty_count": EMPTY_COUNT,
        "initial_request_count": PROCEED_COUNT,
        "maximum_actual_request_count": PROCEED_COUNT * 2,
        "possible_request_body_count": PROCEED_COUNT
        * (1 + len(RETRIEVAL_ROLE_RETRY_CODES)),
        "actual_call_count": actual_call_count,
        "first_pass_count": first_pass_count,
        "retry_success_count": contract_success_count - first_pass_count,
        "contract_success_count": contract_success_count,
        "run_failed_count": PROCEED_COUNT - contract_success_count,
        "transport_failure_count": transport_failure_count,
        "validation_error_code_counts": dict(
            sorted(Counter(validation_codes).items())
        ),
        "final_failure_code_counts": dict(
            sorted(Counter(final_failure_codes).items())
        ),
        "silver_agreement": _span_agreement(model_by_ref, silver_by_ref),
        "role_annotations": aggregate_annotation_report(formal),
        "downstream_status": downstream_status,
        "views": views,
        "failure_codes": sorted(set(failure_codes)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--downstream-algorithm",
        choices=("R1", "R2"),
        default="R1",
    )
    args = parser.parse_args(argv)
    if not args.live:
        print(
            json.dumps(
                {
                    "report_version": REPORT_VERSION,
                    "status": "ERROR",
                    "error_code": "ROLE_MODEL_LIVE_CONFIRMATION_REQUIRED",
                    "llm_called": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    try:
        _validate_tls_trust()
        report = run_experiment(
            args.fixture_dir,
            BailianConfig.from_env(),
            downstream_algorithm=args.downstream_algorithm,
        )
    except (
        BailianProviderError,
        KeyError,
        OSError,
        RoleModelExperimentError,
        TypeError,
        ValueError,
    ) as exc:
        code = getattr(exc, "code", "ROLE_MODEL_EXPERIMENT_FAILED")
        print(
            json.dumps(
                {
                    "report_version": REPORT_VERSION,
                    "status": "ERROR",
                    "error_code": code,
                    "llm_called": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
