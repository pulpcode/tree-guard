from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from treeguard import adapt_tree_document
from treeguard.ai_review import (
    AIReviewDraft,
    AIReviewValidationError,
    BailianAIReviewProvider,
    BailianConfig,
    BailianProviderError,
)
from treeguard.business_review import mine_business_version_pair
from treeguard.evidence import build_business_review_evidence_pack
from treeguard.hashing import canonical_digest
from treeguard.http_utils import build_isolated_opener


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "ai-review-draft.v1.schema.json"
MODEL_OUTPUT_CONTRACT_PATH = (
    PROJECT_ROOT / "contracts" / "ai-review-model-output.v1.schema.json"
)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def find_source_node(document: dict, node_id: str) -> dict:
    def walk(wrapper: dict) -> dict | None:
        if wrapper["metadata"]["node_id"] == node_id:
            return wrapper
        for child in wrapper.get("subnodes", {}).values():
            found = walk(child)
            if found is not None:
                return found
        return None

    for root in document["map_topology"].values():
        found = walk(root)
        if found is not None:
            return found
    raise AssertionError(f"fixture node not found: {node_id}")


def canonical_version(document: dict, version: str, record_id: str):
    source = copy.deepcopy(document)
    source["metadata"]["version"] = version
    source["metadata"]["id"] = record_id
    result = adapt_tree_document(source)
    if result.tree is None:
        raise AssertionError(
            f"fixture failed canonicalization: {[issue.code for issue in result.issues]}"
        )
    return result.tree


def evidence_pack():
    before_document = load_fixture()
    after_document = copy.deepcopy(before_document)
    find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
        "Revised display height"
    )
    before = canonical_version(before_document, "V1", "record-v1")
    after = canonical_version(after_document, "V2", "record-v2")
    run = mine_business_version_pair(
        before,
        after,
        base_position=0,
        target_position=1,
    )
    return build_business_review_evidence_pack(run, before, after)


def valid_draft_payload(pack) -> dict:
    candidate_assessments = []
    if pack.candidate_refs:
        candidate_ref = sorted(pack.candidate_refs)[0]
        candidate_assessments.append(
            {
                "candidate_ref": candidate_ref,
                "relation": "RELATED",
                "reason": "The candidate shares local catalog context.",
            }
        )
    return {
        "schema_version": "ai-review-model-output.v1",
        "change_summary": "One property name changed between business versions.",
        "observations": [
            {
                "statement": "The focus property has a name change.",
                "evidence_refs": ["F001"],
            }
        ],
        "hypotheses": [
            {
                "statement": "The change may clarify display semantics.",
                "evidence_refs": ["F001"],
            }
        ],
        "candidate_assessments": candidate_assessments,
        "placement_assessment": {
            "status": "NEED_EVIDENCE",
            "reason": "A name change alone does not prove placement correctness.",
            "evidence_refs": ["F001"],
        },
        "suggested_disposition": "NEED_EVIDENCE",
        "questions_for_expert": ["Was the name changed to clarify business meaning?"],
        "uncertainties": ["The original version description is unavailable."],
    }


class AIReviewTests(unittest.TestCase):
    def test_isolated_opener_builds_explicit_tls_context_without_proxy(self) -> None:
        with (
            patch("treeguard.http_utils.ssl.create_default_context") as context,
            patch("treeguard.http_utils.urllib.request.build_opener") as opener,
        ):
            build_isolated_opener(cafile="/fictional/ca.pem")

        context.assert_called_once_with(cafile="/fictional/ca.pem")
        handlers = opener.call_args.args
        self.assertTrue(
            any(
                isinstance(handler, urllib.request.ProxyHandler)
                and handler.proxies == {}
                for handler in handlers
            )
        )
        self.assertTrue(
            any(
                isinstance(handler, urllib.request.HTTPRedirectHandler)
                for handler in handlers
            )
        )
        self.assertTrue(
            any(
                isinstance(handler, urllib.request.HTTPSHandler)
                for handler in handlers
            )
        )

    def test_valid_draft_matches_contract_fields(self) -> None:
        pack = evidence_pack()
        payload = valid_draft_payload(pack)

        draft = AIReviewDraft.from_model_dict(payload, pack)
        schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        model_schema = json.loads(
            MODEL_OUTPUT_CONTRACT_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(set(schema["required"]), set(draft.to_dict()))
        self.assertEqual(set(model_schema["required"]), set(payload))
        self.assertEqual(draft.case_id, pack.case_id)
        self.assertEqual(draft.source_pack_hash, pack.pack_hash)
        self.assertEqual(
            AIReviewDraft.from_dict(draft.to_dict(), pack),
            draft,
        )

    def test_unknown_fields_and_references_are_rejected(self) -> None:
        pack = evidence_pack()
        payload = valid_draft_payload(pack)
        payload["unexpected"] = True
        with self.assertRaises(AIReviewValidationError) as fields_error:
            AIReviewDraft.from_model_dict(payload, pack)
        self.assertEqual(fields_error.exception.code, "AI_REVIEW_FIELDS_INVALID")

        payload = valid_draft_payload(pack)
        payload["observations"][0]["evidence_refs"] = ["F999"]
        with self.assertRaises(AIReviewValidationError) as ref_error:
            AIReviewDraft.from_model_dict(payload, pack)
        self.assertEqual(
            ref_error.exception.code,
            "AI_REVIEW_EVIDENCE_REF_INVALID",
        )

        payload = valid_draft_payload(pack)
        payload["observations"][0]["evidence_refs"] = []
        with self.assertRaises(AIReviewValidationError) as empty_ref_error:
            AIReviewDraft.from_model_dict(payload, pack)
        self.assertEqual(
            empty_ref_error.exception.code,
            "AI_REVIEW_EVIDENCE_REF_INVALID",
        )

        stored = AIReviewDraft.from_model_dict(
            valid_draft_payload(pack),
            pack,
        ).to_dict()
        stored["source_pack_hash"] = "0" * 64
        with self.assertRaises(AIReviewValidationError) as pack_error:
            AIReviewDraft.from_dict(stored, pack)
        self.assertEqual(pack_error.exception.code, "AI_REVIEW_PACK_MISMATCH")

        stored = AIReviewDraft.from_model_dict(
            valid_draft_payload(pack),
            pack,
        ).to_dict()
        stored["schema_version"] = "tampered-schema"
        with self.assertRaises(AIReviewValidationError) as schema_error:
            AIReviewDraft.from_dict(stored, pack)
        self.assertEqual(
            schema_error.exception.code,
            "AI_REVIEW_SCHEMA_UNSUPPORTED",
        )

        object.__setattr__(pack, "pack_hash", "0" * 64)
        with self.assertRaises(AIReviewValidationError) as integrity_error:
            AIReviewDraft.from_model_dict(valid_draft_payload(pack), pack)
        self.assertEqual(
            integrity_error.exception.code,
            "AI_REVIEW_EVIDENCE_INVALID",
        )

        pack = evidence_pack()
        payload = valid_draft_payload(pack)
        payload["suggested_disposition"] = {}
        with self.assertRaises(AIReviewValidationError) as enum_error:
            AIReviewDraft.from_model_dict(payload, pack)
        self.assertEqual(
            enum_error.exception.code,
            "AI_REVIEW_DISPOSITION_INVALID",
        )

        payload = valid_draft_payload(pack)
        payload["placement_assessment"]["status"] = {}
        with self.assertRaises(AIReviewValidationError) as placement_error:
            AIReviewDraft.from_model_dict(payload, pack)
        self.assertEqual(
            placement_error.exception.code,
            "AI_REVIEW_PLACEMENT_INVALID",
        )

    def test_provider_uses_json_mode_retries_and_never_sends_node_ids(self) -> None:
        pack = evidence_pack()
        valid_response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            valid_draft_payload(pack),
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

        class RecordingProvider(BailianAIReviewProvider):
            def __init__(self, config):
                super().__init__(config)
                self.requests = []

            def _post_json(self, body):
                self.requests.append(body)
                if len(self.requests) == 1:
                    return {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": "not-json"},
                            }
                        ]
                    }
                return valid_response

        provider = RecordingProvider(BailianConfig(api_key="test-secret"))
        draft = provider.review(pack)
        encoded_request = json.dumps(
            provider.requests,
            ensure_ascii=False,
            sort_keys=True,
        )

        self.assertEqual(draft.case_id, pack.case_id)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(
            provider.requests[0]["response_format"],
            {"type": "json_object"},
        )
        self.assertFalse(provider.requests[0]["enable_thinking"])
        user_payload = json.loads(provider.requests[0]["messages"][1]["content"])
        self.assertEqual(
            user_payload["output_contract"]["schema_version"],
            "ai-review-model-output.v1",
        )
        self.assertNotIn("node-008", encoded_request)
        self.assertNotIn(pack.case_id, encoded_request)
        self.assertNotIn(pack.source_run_hash, encoded_request)
        self.assertNotIn(pack.pack_hash, encoded_request)
        self.assertNotIn("test-secret", encoded_request)

    def test_provider_fails_closed_after_invalid_outputs(self) -> None:
        pack = evidence_pack()

        class InvalidProvider(BailianAIReviewProvider):
            def _post_json(self, body):
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "{}"},
                        }
                    ]
                }

        with self.assertRaises(BailianProviderError) as error:
            InvalidProvider(BailianConfig(api_key="test-secret")).review(pack)
        self.assertEqual(error.exception.code, "AI_REVIEW_FIELDS_INVALID")
        self.assertNotIn("test-secret", str(error.exception))

    def test_strict_json_rejects_nonfinite_and_oversized_numbers(self) -> None:
        pack = evidence_pack()
        invalid_json_values = (
            '{"x":NaN}',
            '{"x":' + ("9" * 5_000) + "}",
        )

        class FakeResponse:
            def __init__(self, raw: bytes) -> None:
                self.raw = raw

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, limit):
                return self.raw

        class StaticOpener:
            def __init__(self, raw: bytes) -> None:
                self.raw = raw

            def open(self, request, timeout):
                return FakeResponse(self.raw)

        for invalid_json in invalid_json_values:
            with self.subTest(layer="envelope", prefix=invalid_json[:12]):
                provider = BailianAIReviewProvider(
                    BailianConfig(api_key="test-secret", max_attempts=1)
                )
                provider._opener = StaticOpener(invalid_json.encode("utf-8"))
                with self.assertRaises(BailianProviderError) as error:
                    provider._post_json({"model": "fixture"})
                self.assertEqual(
                    error.exception.code,
                    "BAILIAN_RESPONSE_NOT_JSON",
                )

            class InvalidContentProvider(BailianAIReviewProvider):
                def _post_json(self, body):
                    return {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": invalid_json},
                            }
                        ]
                    }

            with self.subTest(layer="content", prefix=invalid_json[:12]):
                with self.assertRaises(BailianProviderError) as error:
                    InvalidContentProvider(
                        BailianConfig(
                            api_key="test-secret",
                            max_attempts=1,
                        )
                    ).review(pack)
                self.assertEqual(
                    error.exception.code,
                    "AI_REVIEW_RESPONSE_INVALID",
                )

    def test_http_transport_keeps_key_in_authorization_header_only(self) -> None:
        pack = evidence_pack()
        response_body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(valid_draft_payload(pack))
                        }
                    }
                ]
            }
        ).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, limit):
                return response_body

        class RecordingOpener:
            def __init__(self):
                self.request = None
                self.timeout = None

            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        provider = BailianAIReviewProvider(
            BailianConfig(api_key="transport-secret")
        )
        opener = RecordingOpener()
        provider._opener = opener

        draft = provider.review(pack)

        self.assertEqual(draft.source_pack_hash, pack.pack_hash)
        self.assertEqual(
            opener.request.full_url,
            (
                "https://dashscope.aliyuncs.com/compatible-mode/v1/"
                "chat/completions"
            ),
        )
        self.assertEqual(
            opener.request.get_header("Authorization"),
            "Bearer transport-secret",
        )
        self.assertNotIn(b"transport-secret", opener.request.data)
        self.assertEqual(opener.timeout, 90.0)

    def test_truncated_and_cross_field_invalid_outputs_are_rejected(self) -> None:
        pack = evidence_pack()
        truncated = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "content": json.dumps(valid_draft_payload(pack))
                    },
                }
            ]
        }

        class TruncatedProvider(BailianAIReviewProvider):
            def _post_json(self, body):
                return truncated

        with self.assertRaises(BailianProviderError) as truncated_error:
            TruncatedProvider(
                BailianConfig(api_key="test-secret", max_attempts=1)
            ).review(pack)
        self.assertEqual(
            truncated_error.exception.code,
            "AI_REVIEW_RESPONSE_INVALID",
        )

        payload = valid_draft_payload(pack)
        payload["suggested_disposition"] = "POSSIBLE_DUPLICATE"
        payload["candidate_assessments"] = []
        with self.assertRaises(AIReviewValidationError) as policy_error:
            AIReviewDraft.from_model_dict(payload, pack)
        self.assertEqual(
            policy_error.exception.code,
            "AI_REVIEW_POLICY_INVALID",
        )

        blocked_payload = pack.to_dict()
        blocked_payload.pop("pack_hash")
        blocked_payload["gate_status"] = "BLOCKED"
        blocked_pack = replace(
            pack,
            gate_status="BLOCKED",
            pack_hash=canonical_digest(blocked_payload),
        )
        payload = valid_draft_payload(blocked_pack)
        payload["suggested_disposition"] = "ACCEPT_AS_PATTERN"
        with self.assertRaises(AIReviewValidationError) as blocked_error:
            AIReviewDraft.from_model_dict(payload, blocked_pack)
        self.assertEqual(
            blocked_error.exception.code,
            "AI_REVIEW_POLICY_INVALID",
        )

    def test_public_bailian_provider_uses_explicit_certifi_ca_bundle(self) -> None:
        with (
            patch(
                "treeguard.ai_review.certifi.where",
                return_value="/fictional/ca.pem",
            ),
            patch("treeguard.ai_review.build_isolated_opener") as opener,
        ):
            BailianAIReviewProvider(BailianConfig(api_key="fictional-key"))

        opener.assert_called_once_with(cafile="/fictional/ca.pem")

    def test_config_reads_environment_without_exposing_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BAILIAN_API_KEY": "secret-from-environment",
                "TREEGUARD_LLM_MODEL": "qwen3.6-35b-a3b",
            },
            clear=True,
        ):
            config = BailianConfig.from_env()

        self.assertEqual(config.model, "qwen3.6-35b-a3b")
        self.assertNotIn("secret-from-environment", repr(config))
        with self.assertRaises(BailianProviderError) as invalid_key_error:
            BailianConfig(api_key="secret-that-must-not-leak\nInjected: value")
        self.assertEqual(
            invalid_key_error.exception.code,
            "BAILIAN_API_KEY_INVALID",
        )
        self.assertNotIn(
            "secret-that-must-not-leak",
            str(invalid_key_error.exception),
        )
        with self.assertRaises(BailianProviderError) as invalid_model_error:
            BailianConfig(
                api_key="secret",
                model="bad-model\nInjected: value",
            )
        self.assertEqual(
            invalid_model_error.exception.code,
            "BAILIAN_MODEL_INVALID",
        )
        for value in (-1, 2, True):
            with self.subTest(max_transport_retries=value):
                with self.assertRaises(BailianProviderError) as retry_error:
                    BailianConfig(
                        api_key="secret",
                        max_transport_retries=value,
                    )
                self.assertEqual(
                    retry_error.exception.code,
                    "BAILIAN_TRANSPORT_RETRIES_INVALID",
                )
        with self.assertRaises(BailianProviderError):
            BailianConfig(
                api_key="secret",
                base_url="http://example.com/compatible-mode/v1",
            )
        with self.assertRaises(BailianProviderError):
            BailianConfig(
                api_key="secret",
                base_url=(
                    "https://tenant.oss-cn-beijing.aliyuncs.com/"
                    "compatible-mode/v1"
                ),
            )
        workspace_config = BailianConfig(
            api_key="secret",
            base_url=(
                "https://workspace-123.ap-southeast-1.maas.aliyuncs.com/"
                "compatible-mode/v1"
            ),
        )
        with patch(
            "urllib.request.getproxies",
            return_value={"https": "http://untrusted-proxy.invalid"},
        ) as getproxies:
            provider = BailianAIReviewProvider(workspace_config)
        getproxies.assert_not_called()
        proxy_handlers = [
            handler
            for handler in provider._opener.handlers
            if isinstance(handler, urllib.request.ProxyHandler)
        ]
        self.assertTrue(
            not proxy_handlers
            or all(handler.proxies == {} for handler in proxy_handlers)
        )
        redirect_handlers = [
            handler
            for handler in provider._opener.handlers
            if isinstance(handler, urllib.request.HTTPRedirectHandler)
        ]
        self.assertEqual(len(redirect_handlers), 1)
        self.assertIsNone(
            redirect_handlers[0].redirect_request(
                urllib.request.Request(
                    "https://dashscope.aliyuncs.com/compatible-mode/v1"
                ),
                None,
                302,
                "Found",
                {},
                "https://example.com/",
            )
        )
        with tempfile.TemporaryDirectory() as directory_name:
            previous_directory = Path.cwd()
            os.chdir(directory_name)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    with self.assertRaises(BailianProviderError) as error:
                        BailianConfig.from_env()
            finally:
                os.chdir(previous_directory)
        self.assertEqual(error.exception.code, "BAILIAN_API_KEY_MISSING")

    def test_private_local_dotenv_is_loaded_and_environment_wins(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            env_path = directory / ".env"
            env_path.write_text(
                "\n".join(
                    (
                        "BAILIAN_API_KEY=file-only-fictional-key",
                        (
                            "TREEGUARD_LLM_BASE_URL="
                            "https://dashscope.aliyuncs.com/"
                            "compatible-mode/v1"
                        ),
                        "TREEGUARD_LLM_MODEL=qwen3.6-35b-a3b",
                    )
                ),
                encoding="utf-8",
            )
            env_path.chmod(0o600)
            previous_directory = Path.cwd()
            os.chdir(directory)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    file_config = BailianConfig.from_env()
                    approval_config = BailianConfig.from_env(
                        api_key_override="approval-plan-fictional-key"
                    )
                    self.assertNotIn("BAILIAN_API_KEY", os.environ)
                with patch.dict(
                    os.environ,
                    {"BAILIAN_API_KEY": "process-fictional-key"},
                    clear=True,
                ):
                    process_config = BailianConfig.from_env()
                with patch.dict(
                    os.environ,
                    {"DASHSCOPE_API_KEY": "alias-fictional-key"},
                    clear=True,
                ):
                    alias_config = BailianConfig.from_env()
                with patch.dict(
                    os.environ,
                    {"BAILIAN_API_KEY": ""},
                    clear=True,
                ):
                    with self.assertRaises(
                        BailianProviderError
                    ) as cleared_error:
                        BailianConfig.from_env()
            finally:
                os.chdir(previous_directory)

        self.assertEqual(file_config.api_key, "file-only-fictional-key")
        self.assertEqual(
            approval_config.api_key,
            "approval-plan-fictional-key",
        )
        self.assertEqual(approval_config.base_url, file_config.base_url)
        self.assertEqual(approval_config.model, file_config.model)
        self.assertEqual(process_config.api_key, "process-fictional-key")
        self.assertEqual(alias_config.api_key, "alias-fictional-key")
        self.assertEqual(
            cleared_error.exception.code,
            "BAILIAN_API_KEY_MISSING",
        )
        self.assertNotIn(file_config.api_key, repr(file_config))
        self.assertNotIn(process_config.api_key, repr(process_config))

    def test_local_dotenv_rejects_public_mode_and_malformed_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            env_path = directory / ".env"
            env_path.write_text(
                "BAILIAN_API_KEY=fictional-key\n",
                encoding="utf-8",
            )
            env_path.chmod(0o644)
            previous_directory = Path.cwd()
            os.chdir(directory)
            try:
                with (
                    patch.dict(os.environ, {}, clear=True),
                    self.assertRaises(BailianProviderError) as mode_error,
                ):
                    BailianConfig.from_env()
                env_path.chmod(0o600)
                env_path.write_text(
                    (
                        "BAILIAN_API_KEY=fictional-key\n"
                        "UNSUPPORTED_SECRET=must-not-load\n"
                    ),
                    encoding="utf-8",
                )
                with (
                    patch.dict(os.environ, {}, clear=True),
                    self.assertRaises(BailianProviderError) as format_error,
                ):
                    BailianConfig.from_env()
            finally:
                os.chdir(previous_directory)

        self.assertEqual(
            mode_error.exception.code,
            "BAILIAN_ENV_FILE_UNSAFE",
        )
        self.assertEqual(
            format_error.exception.code,
            "BAILIAN_ENV_FILE_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
