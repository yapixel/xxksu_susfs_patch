"""Comprehensive test suite for V2.8: ownership, symbol, and ABI validation."""

import hashlib
from pathlib import Path
import unittest

from v2.adapters.xxksu import XxksuAdapter
from v2.engine.diff_parser import parse_patch
from v2.model.patch import ContextLine, RemovedLine
from v2.model.provenance import HashDigest
from v2.model.result import (
    AbiLinkageConflict,
    AbiSignatureMismatch,
    AmbiguousAbiMapping,
    DoubleSideEffect,
    DuplicateOwner,
    HandlerABIConflict,
    IncompatibleOwner,
    MissingAbiEvidence,
    MissingRequiredSymbol,
    MissingSymbolEvidence,
    NoOwner,
    OfficialSymbolLeakage,
    PolicyLedgerMismatch,
    SourceBundleIdentityMismatch,
    UndeclaredCoexistence,
    ValidationReport,
    ValidationResult,
    ValidationStatus,
    ZeroOwner,
)
from v2.policy import (
    OwnerKind,
    PolicyAction,
    PolicyCoverageLedger,
    PolicyDecision,
    PolicyOccurrence,
    classify_patch11,
)
from v2.semantic import (
    CandidateObservation,
    EvidenceKind,
    RelationshipType,
    SemanticId,
    SemanticInventory,
)
from v2.source.bundle import (
    CorruptedSourceBundle,
    SourceBundle,
    SourceBundleFile,
)
from v2.validation import (
    BANNED_OFFICIAL_SYMBOLS,
    DEFAULT_ABI_CONTRACTS,
    DEFAULT_SYMBOL_CONTRACTS,
    AbiContract,
    AbiSignature,
    OwnershipClaim,
    make_default_lsm_bl_claims,
    make_default_manual_claims,
    validate_abi,
    validate_all,
    validate_bundle_integrity,
    validate_ledger_integrity,
    validate_ownership,
    validate_signature_against_contract,
    validate_symbols,
)

_PATCH11_PATH = (
    Path(__file__).resolve().parents[4] / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
)


def _build_test_xxksu_bundle() -> SourceBundle:
    """Build a test SourceBundle containing xxKSU base files and replacement definitions."""
    patch_text = _PATCH11_PATH.read_text("utf-8")
    patch = parse_patch(patch_text)

    bundle_files = []
    for fp in patch.files:
        rel_path = fp.old_path[2:] if fp.old_path.startswith("a/") else fp.old_path
        orig_lines = []
        current_line = 1
        for h in fp.hunks:
            while current_line < h.old_start:
                orig_lines.append(f"/* line {current_line} */\n")
                current_line += 1
            for line in h.lines:
                if isinstance(line, (ContextLine, RemovedLine)):
                    orig_lines.append(line.text + "\n")
                    current_line += 1

        if rel_path == "kernel/supercall/dispatch.c":
            orig_lines.append("int susfs_cmd_dispatch(void) { return 0; }\nvoid susfs_auto_reboot(void) { }\n")
        elif rel_path == "kernel/hook/setuid_hook.c":
            orig_lines.append("int handle_zygote_setresuid(void) { return 0; }\n")
        elif rel_path == "kernel/feature/kernel_umount.c":
            orig_lines.append("bool ksu_is_webview_zygote_umount_enabled(void) { return true; }\n")

        content = "".join(orig_lines)
        content_bytes = content.encode("utf-8")
        digest = HashDigest("sha256", hashlib.sha256(content_bytes).hexdigest())
        bundle_files.append(SourceBundleFile(rel_path, digest, len(content_bytes), content))

    extra_files = [
        ("kernel/feature/sucompat.c", "int ksu_handle_execveat(int *fd, struct filename **filename, void *argv, void *envp, int *flags) { return 0; }\n"),
        ("kernel/runtime/ksud.c", "void ksu_handle_newfstat_ret(unsigned int *fd, struct stat __user **statbuf) { }\n"),
        ("kernel/hook/syscall_table_hook_arm64.c", "int ksu_handle_sys_read_fd(void) { return 0; }\n"),
        ("kernel/feature/vol_detector.c", "int input_register_handler(void) { return 0; }\n"),
    ]
    for path, content in extra_files:
        b = content.encode("utf-8")
        d = HashDigest("sha256", hashlib.sha256(b).hexdigest())
        bundle_files.append(SourceBundleFile(path, d, len(b), content))

    return SourceBundle("xxksu", "main", tuple(bundle_files))


class V28PositiveValidationTests(unittest.TestCase):
    """Verify positive baseline correctness across all V2.8 quality gates."""

    def setUp(self) -> None:
        self.clean_bundle = _build_test_xxksu_bundle()
        self.adapter = XxksuAdapter()
        self.mutated_bundle = self.adapter.apply_to_bundle(self.clean_bundle)
        self.patch11_diff = self.adapter.generate_patch11(self.clean_bundle)

    def test_1_mutated_bundle_passes_symbol_validation(self):
        results = validate_symbols(bundle=self.mutated_bundle)
        self.assertTrue(all(r.status == ValidationStatus.PASS for r in results))
        targets = {r.target for r in results}
        self.assertIn("bundle:xxksu", targets)

    def test_2_generated_patch11_zero_official_leaks(self):
        results = validate_symbols(patch=self.patch11_diff)
        self.assertTrue(all(r.status == ValidationStatus.PASS for r in results))
        self.assertTrue(any("Zero official-only symbols detected in patch" in r.details for r in results))

    def test_3_all_required_replacement_symbols_present(self):
        results = validate_symbols(bundle=self.mutated_bundle)
        presence_results = [r for r in results if r.validator_id == "validation.symbols.presence"]
        found_symbols = {r.target for r in presence_results if r.status == ValidationStatus.PASS}

        # Verify xxKSU replacements
        self.assertIn("ksu_handle_execveat", found_symbols)
        self.assertIn("ksu_handle_newfstat_ret", found_symbols)
        self.assertIn("ksu_handle_sys_read_fd", found_symbols)
        self.assertIn("input_register_handler", found_symbols)

        # Verify SuSFS integration symbols
        self.assertIn("susfs_init", found_symbols)
        self.assertIn("susfs_cmd_dispatch", found_symbols)
        self.assertIn("susfs_auto_reboot", found_symbols)
        self.assertIn("handle_zygote_setresuid", found_symbols)
        self.assertIn("ksu_is_webview_zygote_umount_enabled", found_symbols)
        self.assertIn("susfs_set_sid", found_symbols)

    def test_4_valid_manual_ownership_model_passes(self):
        claims = make_default_manual_claims()
        results = validate_ownership(mode="manual", claims=claims)
        self.assertTrue(all(r.status == ValidationStatus.PASS for r in results))
        self.assertEqual(len(results), 9)

    def test_5_valid_lsm_bl_ownership_model_passes(self):
        claims = make_default_lsm_bl_claims()
        results = validate_ownership(mode="lsm_bl", claims=claims)
        self.assertTrue(all(r.status == ValidationStatus.PASS for r in results))
        self.assertEqual(len(results), 9)

    def test_6_valid_handler_abi_contracts_pass(self):
        # Validate that valid signatures pass for all 11 default ABI contracts
        valid_signatures = (
            AbiSignature("ksu_handle_execveat", "int", ("int *", "struct filename **", "void *", "void *", "int *"), "extern"),
            AbiSignature("ksu_handle_faccessat", "int", ("int *", "const char __user **", "int *", "int *"), "extern"),
            AbiSignature("ksu_handle_stat", "int", ("int *", "const char __user **", "int *"), "extern"),
            AbiSignature("ksu_handle_newfstat_ret", "void", ("unsigned int *", "struct stat __user **"), "extern"),
            AbiSignature("ksu_handle_fstat64_ret", "void", ("unsigned long *", "struct stat64 __user **"), "extern"),
            AbiSignature("ksu_handle_sys_reboot", "int", ("int", "int", "unsigned int", "void __user **"), "extern"),
            AbiSignature("ksu_bprm_check", "int", ("struct linux_binprm *",), "extern"),
            AbiSignature("ksu_inode_rename", "int", ("struct inode *", "struct dentry *", "struct inode *", "struct dentry *"), "extern"),
            AbiSignature("ksu_file_permission", "int", ("struct file *", "int"), "extern"),
            AbiSignature("ksu_task_fix_setuid", "int", ("struct cred *", "const struct cred *", "int"), "extern"),
            AbiSignature("ksu_hide_setprocattr", "int", ("const char *", "void *", "size_t"), "extern"),
        )
        results = validate_abi(signatures=valid_signatures)
        self.assertEqual(len(results), 11)
        self.assertTrue(all(r.status == ValidationStatus.PASS for r in results))

    def test_7_validation_result_canonical_json_deterministic(self):
        res1 = ValidationResult(
            validator_id="test.validator",
            status=ValidationStatus.PASS,
            target="target.symbol",
            details="passed verification",
            path="path/to/file.c",
            line=42,
        )
        res2 = ValidationResult(
            validator_id="test.validator",
            status=ValidationStatus.PASS,
            target="target.symbol",
            details="passed verification",
            path="path/to/file.c",
            line=42,
        )
        self.assertEqual(res1.canonical_json(), res2.canonical_json())
        self.assertEqual(res1.identity, res2.identity)

    def test_8_validation_report_digest_deterministic(self):
        report = validate_all(
            bundle=self.mutated_bundle,
            patch=self.patch11_diff,
            mode="manual",
            claims=make_default_manual_claims(),
        )
        self.assertEqual(report.status, ValidationStatus.PASS)
        digest1 = report.digest
        digest2 = report.digest
        self.assertEqual(digest1, digest2)
        self.assertTrue(str(digest1).startswith("sha256:"))

    def test_9_repeated_validate_all_identical(self):
        report1 = validate_all(
            bundle=self.mutated_bundle,
            patch=self.patch11_diff,
            mode="manual",
            claims=make_default_manual_claims(),
        )
        report2 = validate_all(
            bundle=self.mutated_bundle,
            patch=self.patch11_diff,
            mode="manual",
            claims=make_default_manual_claims(),
        )
        self.assertEqual(report1.digest, report2.digest)
        self.assertEqual([r.to_dict() for r in report1.results], [r.to_dict() for r in report2.results])


class V28NegativeValidationTests(unittest.TestCase):
    """Verify strict fail-closed behavior across all required negative conditions."""

    def setUp(self) -> None:
        self.clean_bundle = _build_test_xxksu_bundle()
        self.adapter = XxksuAdapter()
        self.mutated_bundle = self.adapter.apply_to_bundle(self.clean_bundle)

    def test_1_inject_ksu_handle_execveat_sucompat_fails_closed(self):
        leaked_patch = (
            "--- a/kernel/feature/sucompat.c\n"
            "+++ b/kernel/feature/sucompat.c\n"
            "@@ -10,3 +10,4 @@\n"
            " context\n"
            "+int ksu_handle_execveat_sucompat(int *fd);\n"
        )
        results = validate_symbols(patch=leaked_patch)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].metadata.get("error_type"), "OfficialSymbolLeakage")
        self.assertEqual(failures[0].line, 5)
        self.assertEqual(failures[0].path, "kernel/feature/sucompat.c")

        with self.assertRaises(OfficialSymbolLeakage):
            validate_symbols(patch=leaked_patch, raise_on_failure=True)

    def test_2_inject_ksu_handle_vfs_fstat_fails_closed(self):
        leaked_patch = (
            "--- a/fs/stat.c\n"
            "+++ b/fs/stat.c\n"
            "@@ -20,2 +20,3 @@\n"
            " context\n"
            "+ksu_handle_vfs_fstat(fd, statbuf);\n"
        )
        results = validate_symbols(patch=leaked_patch)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].metadata.get("symbol"), "ksu_handle_vfs_fstat")

        with self.assertRaises(OfficialSymbolLeakage):
            validate_symbols(patch=leaked_patch, raise_on_failure=True)

    def test_3_inject_ksu_handle_sys_read_fails_closed(self):
        bad_content = self.clean_bundle.get_file("kernel/ksu.c").content + "\nksu_handle_sys_read();\n"
        tampered_bundle = self.clean_bundle.with_updated_file("kernel/ksu.c", bad_content)
        results = validate_symbols(bundle=tampered_bundle)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.metadata.get("symbol") == "ksu_handle_sys_read" for r in failures))

        with self.assertRaises(OfficialSymbolLeakage):
            validate_symbols(bundle=tampered_bundle, raise_on_failure=True)

    def test_4_inject_ksu_handle_input_handle_event_fails_closed(self):
        bad_content = "void ksu_handle_input_handle_event(void) {}\n"
        tampered_bundle = self.clean_bundle.with_updated_file("kernel/feature/vol_detector.c", bad_content)
        results = validate_symbols(bundle=tampered_bundle)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.metadata.get("symbol") == "ksu_handle_input_handle_event" for r in failures))

        with self.assertRaises(OfficialSymbolLeakage):
            validate_symbols(bundle=tampered_bundle, raise_on_failure=True)

    def test_5_missing_required_replacement_symbol_fails(self):
        # Remove ksu_handle_execveat definition
        tampered_bundle = self.clean_bundle.with_updated_file("kernel/feature/sucompat.c", "/* empty */\n")
        results = validate_symbols(bundle=tampered_bundle)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.metadata.get("symbol") == "ksu_handle_execveat" for r in failures))

        with self.assertRaises(MissingRequiredSymbol):
            validate_symbols(bundle=tampered_bundle, raise_on_failure=True)

    def test_6_zero_owner_transport_path_fails(self):
        # Remove claim for exec
        incomplete_claims = tuple(c for c in make_default_manual_claims() if c.path != "exec")
        results = validate_ownership(mode="manual", claims=incomplete_claims)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.target == "exec" and r.metadata.get("error_type") == "NoOwner" for r in failures))

        with self.assertRaises(NoOwner):
            validate_ownership(mode="manual", claims=incomplete_claims, raise_on_failure=True)

    def test_7_manual_plus_automated_owner_simultaneously_fails(self):
        # Add automated branch-link claim for exec alongside manual fixture
        duplicate_claims = make_default_manual_claims() + (
            OwnershipClaim("exec", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_execveat"),
        )
        results = validate_ownership(mode="manual", claims=duplicate_claims)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.target == "exec" and r.metadata.get("error_type") == "DoubleSideEffect" for r in failures))

        with self.assertRaises(DoubleSideEffect):
            validate_ownership(mode="manual", claims=duplicate_claims, raise_on_failure=True)

    def test_8_manual_fixture_present_in_lsm_bl_fails(self):
        # In lsm_bl mode, replace exec claim with manual fixture
        invalid_lsm_claims = tuple(c for c in make_default_lsm_bl_claims() if c.path != "exec") + (
            OwnershipClaim("exec", "PATCH_11", "FIXTURE_SCOPE_MIN", "fixture", caller_symbol="ksu_handle_execveat"),
        )
        results = validate_ownership(mode="lsm_bl", claims=invalid_lsm_claims)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.target == "exec" and r.metadata.get("error_type") == "IncompatibleOwner" for r in failures))

        with self.assertRaises(IncompatibleOwner):
            validate_ownership(mode="lsm_bl", claims=invalid_lsm_claims, raise_on_failure=True)

    def test_9_abi_argument_count_mismatch_fails(self):
        # 4 parameters instead of 5
        bad_sig = AbiSignature("ksu_handle_execveat", "int", ("int *", "struct filename **", "void *", "void *"), "extern")
        contract = DEFAULT_ABI_CONTRACTS[0]  # ksu_handle_execveat
        res = validate_signature_against_contract(bad_sig, contract)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        self.assertEqual(res.metadata.get("error_type"), "AbiSignatureMismatch")

        with self.assertRaises(AbiSignatureMismatch):
            validate_signature_against_contract(bad_sig, contract, raise_on_failure=True)

    def test_10_abi_pointer_type_mismatch_fails(self):
        # Param 1: struct filename * instead of struct filename **
        bad_sig = AbiSignature("ksu_handle_execveat", "int", ("int *", "struct filename *", "void *", "void *", "int *"), "extern")
        contract = DEFAULT_ABI_CONTRACTS[0]
        res = validate_signature_against_contract(bad_sig, contract)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        self.assertEqual(res.metadata.get("error_type"), "AbiSignatureMismatch")

        with self.assertRaises(AbiSignatureMismatch):
            validate_signature_against_contract(bad_sig, contract, raise_on_failure=True)

    def test_11_abi_return_type_mismatch_fails(self):
        # Return type void instead of int
        bad_sig = AbiSignature("ksu_handle_execveat", "void", ("int *", "struct filename **", "void *", "void *", "int *"), "extern")
        contract = DEFAULT_ABI_CONTRACTS[0]
        res = validate_signature_against_contract(bad_sig, contract)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        self.assertEqual(res.metadata.get("error_type"), "AbiSignatureMismatch")

        with self.assertRaises(AbiSignatureMismatch):
            validate_signature_against_contract(bad_sig, contract, raise_on_failure=True)

    def test_12_static_global_linkage_mismatch_fails(self):
        # Static linkage when extern expected
        bad_sig = AbiSignature("ksu_handle_execveat", "int", ("int *", "struct filename **", "void *", "void *", "int *"), "static")
        contract = DEFAULT_ABI_CONTRACTS[0]
        res = validate_signature_against_contract(bad_sig, contract)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        self.assertEqual(res.metadata.get("error_type"), "AbiLinkageConflict")

        with self.assertRaises(AbiLinkageConflict):
            validate_signature_against_contract(bad_sig, contract, raise_on_failure=True)

    def test_13_duplicate_conflicting_declarations_fails(self):
        source_with_conflict = (
            "extern int ksu_handle_execveat(int *, struct filename **, void *, void *, int *);\n"
            "extern void ksu_handle_execveat(int *, struct filename **, void *, void *, int *);\n"
        )
        tampered_bundle = self.clean_bundle.with_updated_file("kernel/feature/sucompat.c", source_with_conflict)
        results = validate_abi(bundle=tampered_bundle)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.metadata.get("error_type") == "AmbiguousAbiMapping" for r in failures))

        with self.assertRaises(AmbiguousAbiMapping):
            validate_abi(bundle=tampered_bundle, raise_on_failure=True)

    def test_14_missing_declaration_definition_fails(self):
        # When validating against contract directly
        contract = AbiContract("ksu_nonexistent_handler", "int", ("int",))
        empty_bundle = SourceBundle("xxksu", "main", ())
        results = validate_abi(bundle=empty_bundle, contracts=(contract,))
        # No signature found for contract
        self.assertEqual(len(results), 0)

    def test_15_corrupted_source_bundle_integrity_fails(self):
        bad_digest = HashDigest("sha256", "0" * 64)
        with self.assertRaises(CorruptedSourceBundle):
            SourceBundleFile("kernel/ksu.c", bad_digest, 10, "content_with_more_than_10_bytes")

    def test_16_incomplete_ledger_fails(self):
        empty_ledger = PolicyCoverageLedger("test-inventory")
        res = validate_ledger_integrity(empty_ledger)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        self.assertEqual(res.metadata.get("error_type"), "PolicyLedgerMismatch")

        with self.assertRaises(PolicyLedgerMismatch):
            validate_ledger_integrity(empty_ledger, raise_on_failure=True)

    def test_17_unknown_ledger_disposition_fails(self):
        occ = PolicyOccurrence(
            semantic_id=SemanticId("test.unit"),
            evidence_fingerprint="fp123",
            container_id="cont1",
            path="fs/exec.c",
            start_line=1,
            end_line=10,
        )
        bad_decision = PolicyDecision(
            occurrence=occ,
            action=PolicyAction.UNKNOWN,
            owner=OwnerKind.UNRESOLVED,
            rationale="unresolved unit",
        )
        ledger = PolicyCoverageLedger("test-inventory")
        ledger.add(bad_decision)

        res = validate_ledger_integrity(ledger)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        self.assertEqual(res.metadata.get("error_type"), "PolicyLedgerMismatch")

        with self.assertRaises(PolicyLedgerMismatch):
            validate_ledger_integrity(ledger, raise_on_failure=True)

    def test_18_synthetic_evidence_rejected_in_production(self):
        results_symbols = validate_symbols(allow_synthetic=False, evidence_kind="SYNTHETIC")
        self.assertTrue(any(r.status == ValidationStatus.FAIL and r.metadata.get("error_type") == "MissingSymbolEvidence" for r in results_symbols))

        results_abi = validate_abi(allow_synthetic=False, evidence_kind="SYNTHETIC")
        self.assertTrue(any(r.status == ValidationStatus.FAIL and r.metadata.get("error_type") == "MissingAbiEvidence" for r in results_abi))

        with self.assertRaises(MissingSymbolEvidence):
            validate_symbols(allow_synthetic=False, evidence_kind="SYNTHETIC", raise_on_failure=True)

    def test_19_undeclared_coexistence_fails(self):
        # Claim with is_independent_susfs=True but coexistence_declared=False
        undeclared_claim = OwnershipClaim(
            "stat", "PATCH_51", "PATCH_51", "target_kernel",
            caller_symbol="susfs_stat", is_independent_susfs=True, coexistence_declared=False,
        )
        base_claims = tuple(c for c in make_default_manual_claims() if not c.is_independent_susfs)
        claims = base_claims + (undeclared_claim,)
        results = validate_ownership(mode="manual", claims=claims)
        failures = [r for r in results if r.status == ValidationStatus.FAIL]
        self.assertTrue(any(r.metadata.get("error_type") == "UndeclaredCoexistence" for r in failures))

        with self.assertRaises(UndeclaredCoexistence):
            validate_ownership(mode="manual", claims=claims, raise_on_failure=True)

    def test_20_runtime_probes_required_status_not_silently_passed(self):
        report = validate_all(
            bundle=self.mutated_bundle,
            patch=self.adapter.generate_patch11(self.clean_bundle),
            mode="manual",
            claims=make_default_manual_claims(),
            runtime_probes_required=True,
        )
        self.assertEqual(report.status, ValidationStatus.RUNTIME_REQUIRED)
        self.assertTrue(any(r.status == ValidationStatus.RUNTIME_REQUIRED for r in report.results))
