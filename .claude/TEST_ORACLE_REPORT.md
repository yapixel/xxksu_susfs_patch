# Test-oracle correction and consolidation

## Correction phase

Starting commit: f83efeb5ca7b9ec3ce34eb17aa2b91975004e453.
The first two commits changed only tests, source-contract/reference fixtures and this report. The subsequent authorized no-op fix changes pipeline publication control, as documented below. Generators and published patch bytes remain unchanged.

The lifecycle harness executes generated mnt_free_id rather than providing a guarded replacement. It executes native nameidata setup, restoration and nested filename lookup; the generated open/retry and pagemap caller paths remain covered. GKI page-size emulation is exercised separately. The rollup harness uses native iterator wrappers and requires iterator invalidation before lock release. Low-level allocator, page walker and scheduling primitives remain bounded mocks: these tests do not prove full kernel concurrency correctness.

Target contracts come from the authenticated repository source bundles and pinned header excerpts, not a shared fictional API. These preserve Sultan/GKI add_to_pagemap, security_setprocattr, and vfs_tmpfile differences, plus nameidata, VMA/walker, smaps and mount helper signatures. The r38 archive used for header extraction was SHA-256 verified before reading it. Excerpt provenance and complete header hashes are recorded in target-api-contracts.json.

V27 now invokes production overlap validation and physically removes golden access. V28 required declaration absence is rejected by the combined required-symbol gate; the optional ABI validator alone does not promise presence. V29 asserts FAIL/NoOwner and verifies the actual symbol/ABI stages preceding ownership rejection. The reference comparison reads pinned upstream Midori commit bytes from the repository fixture. Dashboard no-change/failure tests compare exact bytes and state.

## Validation

| Phase | Methods | Seconds | Failures/errors/skips |
|---|---:|---:|---|
| Original baseline | 333 | 367.288 | 0 / 0 / 0 |
| Corrected oracles | 335 | 376.927 | 0 / 0 / 0 |
| Consolidated, final fresh process | 237 | 64.229 | 0 / 0 / 0 |

Timing uses unittest's run duration; the final discovery-plus-run wall time was 64.391s. On this same local WSL host, the final suite was 5.72 times faster than the original (82.5% less run time). These are single-run measurements, not a benchmark guarantee. A preceding consolidated discovery also passed all 237 methods in 65.059s.

The dashboard byte-comparison and native iterator lock assertions also passed their complete module reruns after final tightening (21 and 9 methods).

## Historical mutation gate

Before consolidation, each mutation below caused a relevant current test assertion or C compile failure, with no unittest errors:
- Sultan two-argument append call.
- Missing nd->name restoration.
- Clone allocation-state re-evaluation.
- Missing generated mount free guard, tested independently for GKI and Sultan.
- Missing smaps hidden-VMA guard.
- Bypassed pagemap caller integration.
- Split generated C character literal, both production targets.

The disposable experiment wraps actual transform outputs (and the actual candidate for the literal mutation), substitutes one defect at a time, runs the unchanged relevant tests, and restores the original callables in a finally block. Mutation site uniqueness is asserted. No mutation framework or mutation hooks were added to production.

## Consolidation ownership ledger

Correction commit: 2d4ee0302b6106d25f91471fbbdf83bdc5cf7f6e (unsigned by explicit user request).

The second phase removes 98 method boundaries from the corrected 335-method suite, retaining 237. This is 96 fewer than the original 333 because the correction phase added two useful methods. Parameterized/grouped cases remain cases; a lower method count is not itself evidence of stronger coverage. All lifecycle and caller-integration tests from the first commit remain unchanged. No generic mutation framework was added.

The largest runtime saving is removal of repeated V29 incomplete-source compositions. Related negative cases retain their concrete exception and state checks under named subtests. Stateful delivery tests now share one initial-no-op, promotion, byte/manifest verification, and rerun scenario. The counts below describe method consolidation, not deleted behavioral cases.

| Module | Before correction | Corrected | Consolidated |
|---|---:|---:|---:|
| test_baseline.py | 20 | 20 | 11 |
| test_dashboard.py | 21 | 21 | 13 |
| test_delivery.py | 14 | 14 | 9 |
| test_diff.py | 16 | 16 | 15 |
| test_generator_regression.py | 8 | 9 | 7 |
| test_lifecycle.py | 8 | 9 | 9 |
| test_lifecycle_gate.py | 3 | 3 | 3 |
| test_mail_diffstat.py | 3 | 3 | 3 |
| test_normalizer.py | 7 | 7 | 7 |
| test_patch_apply.py | 6 | 6 | 5 |
| test_patch_manifest.py | 9 | 9 | 3 |
| test_pipeline.py | 7 | 7 | 2 |
| test_reference_cross_check.py | 8 | 8 | 7 |
| test_semantic_gate.py | 5 | 5 | 3 |
| test_v22.py | 16 | 16 | 13 |
| test_v23.py | 21 | 21 | 17 |
| test_v24.py | 17 | 17 | 17 |
| test_v25.py | 21 | 21 | 19 |
| test_v26.py | 12 | 12 | 8 |
| test_v27.py | 26 | 26 | 19 |
| test_v28.py | 29 | 29 | 15 |
| test_v29.py | 38 | 38 | 15 |
| test_watch.py | 18 | 18 | 17 |

Every removed or consolidated group follows. Names are exact method names in the named module. Each consolidation retains the meaningful original assertions, unless a stronger retained owner is explicitly identified. The deletion risk is loss of redundant diagnostics; negative contracts, native target distinctions and historical mutation signals are retained. External kernel semantic review remains necessary.

### test_baseline.py — consolidate

Previous methods (4):

- test_all_baseline_files_exist
- test_sultan_baseline_record_validates
- test_gki_baseline_record_validates
- test_xxksu_baseline_record_validates

Retained owner: test_pinned_baseline_records.

One matrix preserves all pinned fields and existence checks.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_baseline.py — consolidate

Previous methods (3):

- test_gki_authoritative_bundle_loads
- test_sultan_authoritative_bundle_loads
- test_xxksu_authoritative_bundle_loads

Retained owner: test_authoritative_bundles.

One matrix preserves all target-specific bundle contracts.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_baseline.py — consolidate

Previous methods (2):

- test_gki_internal_patch_51_retired
- test_gki_r38_production_patch_51

Retained owner: test_gki_public_r38_and_retired_internal_patch.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_baseline.py — consolidate

Previous methods (2):

- test_xxksu_patch_11_deterministic_generation
- test_xxksu_patch_11_strict_application_succeeds

Retained owner: test_xxksu_generated_patch_matches_applied_postimage.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_baseline.py — remove

Previous methods (2):

- test_sultan_patch_51_strict_application_succeeds
- test_sultan_both_profiles_validate_positive

Retained owner: test_sultan_profiles_consume_authoritative_patch_11.

Real composition already applies Patch 51 and validates both modes with authoritative Patch 11.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_dashboard.py — consolidate

Previous methods (5):

- test_04_all_authoritative_no_change_is_healthy
- test_05_safe_regen_candidate_is_update_available
- test_06_reference_only_real_drift_is_review_required
- test_07_authoritative_drift_is_action_required
- test_08_authoritative_status_precedence_over_reference_status

Retained owner: test_status_and_precedence.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_dashboard.py — consolidate

Previous methods (2):

- test_10_maximum_5_displayed_escalations
- test_11_maximum_10_recent_events

Retained owner: test_display_caps.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_dashboard.py — consolidate

Previous methods (2):

- test_13_repeated_watcher_runs_do_not_cause_unbounded_body_growth
- test_15_rendered_body_stays_below_30_kib

Retained owner: test_repeated_render_bytes_and_size_limit.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_dashboard.py — consolidate

Previous methods (2):

- test_14_commit_rebase_only_midori_with_identical_normalized_content_remains_no_change
- test_19_reference_patch_primary_identity_is_normalized_content

Retained owner: test_reference_content_identity.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_dashboard.py — remove

Previous methods (1):

- test_16_deterministic_rendering_for_identical_state

Retained owner: test_repeated_render_bytes_and_size_limit.

Repeated rendering now compares exact bytes and event state.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_diff.py — remove

Previous methods (1):

- test_legacy_malformed_51_fails_closed

Retained owner: DiffParserNegativeTests.test_invalid_prefix_and_count_mismatch.

Historical malformed hunk duplicates the parser's explicit malformed-count/prefix matrix.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_generator_regression.py — remove

Previous methods (2):

- test_reproduce_re_sub_template_corrupts_escaped_newline_literal
- test_safe_replacement_preserves_character_literal

Retained owner: test_generated_patch51_literals_both_targets.

Python re.sub demonstrations do not call production generation; new generated-source regression does.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_patch_apply.py — remove

Previous methods (1):

- test_output_is_deterministic

Retained owner: test_baseline.test_xxksu_generated_patch_matches_applied_postimage.

Same byte/hash property is checked on actual generated and independently applied source.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_patch_manifest.py — consolidate

Previous methods (7):

- test_manifest_file_exists_and_valid_json
- test_manifest_schema_and_entries_count
- test_required_fields_in_each_entry
- test_every_manifest_path_exists_on_disk
- test_every_manifest_sha256_matches
- test_manifest_deterministic_match_with_generator
- test_verify_patch_manifest_function_passes

Retained owner: test_manifest_integrity_and_canonical_bytes.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_pipeline.py — remove

Previous methods (5):

- test_2_failed_candidate_never_changes_patches
- test_3_successful_candidate_promoted_to_patches
- test_4_promoted_file_equals_validated_candidate_byte_for_byte
- test_5_manifest_sha_equals_promoted_file
- test_6_rerunning_identical_inputs_is_noop

Retained owner: test_delivery.test_delivery_bytes_manifest_and_noop / test_1_failed_candidate_no_commit_or_push; early no-op ownership is restored by test_pipeline.TestPipelineArchitecture.test_unchanged_candidate_never_enters_promotion_or_writeback.

Retain the stronger real Git delivery boundary, including failure byte snapshots.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_reference_cross_check.py — remove

Previous methods (1):

- test_07_reference_comparison_cannot_authorize_production_changes

Retained owner: test_delivery.test_7_reference_only_midori_does_not_trigger_write_back.

Delivery exercises actual no-commit/no-push boundary rather than write_back=False alone.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_semantic_gate.py — consolidate

Previous methods (2):

- test_1_direct_promote_with_unknown_semantics_blocked
- test_2_patches_and_metadata_remain_unchanged_on_block

Retained owner: test_unknown_semantics_block_without_writes.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_semantic_gate.py — remove

Previous methods (1):

- test_5_normal_already_approved_regeneration_is_noop

Retained owner: test_pipeline.TestPipelineArchitecture.test_unchanged_candidate_never_enters_promotion_or_writeback (early no-op), plus test_delivery.test_delivery_bytes_manifest_and_noop (Git delivery).

Duplicate invariant; retained owner exercises the same production boundary.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v22.py — consolidate

Previous methods (2):

- test_all_four_profiles_validate_independently
- test_shared_11_and_transport_neutral_51

Retained owner: test_profile_manifest_matrix.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v22.py — consolidate

Previous methods (2):

- test_offline_prepare_is_reproducible_and_never_fetches
- test_offline_prepare_does_not_call_fetch

Retained owner: test_offline_prepare_reproducible_without_fetch.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v22.py — remove

Previous methods (1):

- test_repository_fixtures_are_hashable

Retained owner: test_baseline.test_authoritative_bundles.

Merely hashing arbitrary fixtures does not authenticate their provenance; authoritative loader does.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v23.py — consolidate

Previous methods (2):

- test_ids_and_fingerprints_are_stable_and_path_independent
- test_evidence_and_relationship_serialization

Retained owner: test_semantic_identity_and_serialization.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v23.py — consolidate

Previous methods (2):

- test_real_patches_and_fixtures_are_structurally_inventoryable
- test_real_51_bounded_sample_is_inventoryable

Retained owner: test_real_patch_inventory.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v23.py — remove

Previous methods (1):

- test_three_target_families_and_confidence_are_representable

Retained owner: test_v22.test_profile_manifest_matrix.

Retired third target representability is not a supported production contract.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v23.py — consolidate

Previous methods (2):

- test_transport_terminology_is_not_collapsed
- test_official_only_config_and_abi_evidence_are_preserved

Retained owner: test_transport_config_and_abi_roles.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v25.py — consolidate

Previous methods (2):

- test_source_bundle_deterministic_identity
- test_source_bundle_json_roundtrip

Retained owner: test_source_bundle_identity_and_roundtrip.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v25.py — remove

Previous methods (1):

- test_target_anchor_difference_gki_vs_sultan_namespace

Retained owner: test_lifecycle.test_native_target_contracts / test_target_anchor_difference_6_1_vs_6_12_stat.

Fake namespace fragment encoded no actual target difference; real contracts and genuine stat anchor difference remain.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v26.py — consolidate

Previous methods (5):

- test_expected_13_operations_total_on_gki_6_1
- test_adaptation_model_on_gki_6_12
- test_adaptation_model_on_sultan_6_1
- test_adaptation_is_deterministic
- test_individual_fixture_adaptation

Retained owner: test_target_fixture_adaptation_matrix.

Replace stale GKI-6.1 alias and repeated counts with both native targets and individual fixture subsets.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v27.py — remove

Previous methods (6):

- test_adapter_registry_lookup
- test_build_adaptation_plan_all_12_operations
- test_deterministic_patch11_regeneration
- test_golden_patch11_parity
- test_apply_to_bundle_produces_valid_mutated_bundle
- test_bundle_tampering_size_or_hash_mismatch_fails_closed

Retained owner: test_baseline.test_xxksu_generated_patch_matches_applied_postimage / test_v25.test_source_bundle_corrupted_file_detected / test_adapter_factory_and_identification.

Adapter factory, authoritative generated/applied equality and bundle integrity already own these checks.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v27.py — consolidate

Previous methods (2):

- test_generate_patch11_does_not_read_golden_file
- test_generate_patch11_succeeds_when_golden_patch_unavailable

Retained owner: test_generate_patch11_independent_of_golden.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v28.py — consolidate

Previous methods (4):

- test_1_mutated_bundle_passes_symbol_validation
- test_2_generated_patch11_zero_official_leaks
- test_3_all_required_replacement_symbols_present
- test_9_repeated_validate_all_identical

Retained owner: test_generated_symbol_report_and_determinism.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v28.py — consolidate

Previous methods (2):

- test_4_valid_manual_ownership_model_passes
- test_5_valid_lsm_bl_ownership_model_passes

Retained owner: test_ownership_modes.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v28.py — remove

Previous methods (2):

- test_7_validation_result_canonical_json_deterministic
- test_8_validation_report_digest_deterministic

Retained owner: test_generated_symbol_report_and_determinism.

Actual repeated validate_all checks both digest and serialized result equality.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v28.py — consolidate

Previous methods (4):

- test_1_inject_ksu_handle_execveat_sucompat_fails_closed
- test_2_inject_ksu_handle_vfs_fstat_fails_closed
- test_3_inject_ksu_handle_sys_read_fails_closed
- test_4_inject_ksu_handle_input_handle_event_fails_closed

Retained owner: test_banned_symbol_matrix.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v28.py — consolidate

Previous methods (4):

- test_9_abi_argument_count_mismatch_fails
- test_10_abi_pointer_type_mismatch_fails
- test_11_abi_return_type_mismatch_fails
- test_12_static_global_linkage_mismatch_fails

Retained owner: test_abi_mismatch_matrix.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v28.py — remove

Previous methods (1):

- test_15_corrupted_source_bundle_integrity_fails

Retained owner: test_v25.test_source_bundle_corrupted_file_detected.

Duplicate invariant; retained owner exercises the same production boundary.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v28.py — consolidate

Previous methods (2):

- test_16_incomplete_ledger_fails
- test_17_unknown_ledger_disposition_fails

Retained owner: test_invalid_ledger.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — remove

Previous methods (9):

- test_3_manual_composition_rejects_missing_owners
- test_4_lsm_composition_rejects_missing_owners
- test_5_failed_composition_has_no_successful_report
- test_10_incomplete_sources_are_rejected_by_ownership_validation
- test_11_symbol_validation_precedes_missing_owner_rejection
- test_12_abi_validation_precedes_missing_owner_rejection
- test_14_incomplete_sources_block_deterministically
- test_15_repeated_incomplete_composition_remains_blocked
- test_16_incomplete_source_permutations_remain_blocked

Retained owner: test_2_incomplete_synthetic_sources_are_blocked / test_v25.test_source_bundle_identity_and_roundtrip.

All called the same helper on the same incomplete input. Four-profile helper retains exact FAIL/NoOwner state, validation-stage calls, and raised exception; source order canonicalization is owned by bundle tests.

Risk: Duplicate/model-only signal is removed; retain the named production-boundary or negative-contract owner.

### test_v29.py — consolidate

Previous methods (4):

- test_1_all_four_canonical_profile_ids_resolve
- test_6_all_four_use_identical_shared_patch_11_identity
- test_7_target_patch_51_differs_only_by_target_never_by_mode
- test_13_manifests_are_byte_deterministic

Retained owner: test_profile_identity_matrix.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — consolidate

Previous methods (2):

- test_8_manual_config_validates
- test_9_lsm_bl_config_validates

Retained owner: test_valid_config_modes.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — consolidate

Previous methods (4):

- test_neg_3_manual_missing_scope_min_fixture
- test_neg_4_manual_missing_manual_security_fixture
- test_neg_5_manual_extra_fixture
- test_neg_6_lsm_bl_containing_either_manual_fixture

Retained owner: test_invalid_fixture_sets.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — consolidate

Previous methods (2):

- test_neg_7_missing_patch_11
- test_neg_8_missing_patch_51

Retained owner: test_missing_patch_inputs.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — consolidate

Previous methods (4):

- test_neg_10_manual_lsm_y_fails
- test_neg_11_manual_bl_y_fails
- test_neg_12_lsm_bl_lsm_n_fails
- test_neg_13_lsm_bl_bl_n_fails

Retained owner: test_wrong_mode_config.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — consolidate

Previous methods (2):

- test_neg_16_lsm_bl_missing_arm64_fails
- test_neg_17_lsm_bl_missing_kallsyms_fails

Retained owner: test_missing_lsm_prerequisites.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_v29.py — consolidate

Previous methods (3):

- test_neg_19_duplicate_transport_owner_fails
- test_neg_20_banned_official_symbol_injected_fails
- test_neg_21_handler_abi_mutated_fails

Retained owner: test_composition_validation_failures.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_watch.py — consolidate

Previous methods (2):

- test_all_classifications_present
- test_escalation_predicate

Retained owner: test_classification_escalation_contract.

Consolidate related cases under one responsibility; preserve their assertions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_delivery.py — consolidate

Previous methods (5):

- test_2_unchanged_candidate_no_commit
- test_3_changed_candidate_one_promotion_commit
- test_4_committed_patches_bytes_equals_validated_candidate
- test_5_manifest_sha_equals_committed_public_patch
- test_6_rerun_after_promotion_clean_noop

Retained owner: test_delivery_bytes_manifest_and_noop.

One real Git scenario proves initial no-op, exactly one change commit, local/origin bytes, manifest, and rerun no-op without five duplicated promotions.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

### test_delivery.py — consolidate

Previous methods (2):

- test_9_sultan_patch51_verified_write_back
- test_10_gki_r38_patch51_verified_write_back

Retained owner: test_patch51_target_delivery.

Same delivery invariant, explicit target-specific inputs in one matrix; no common kernel API.

Risk: Cases remain as named subtests or an explicit target matrix; failure reporting moves to the shared method.

## Mutation results after consolidation

| Mutation | Before consolidation | After consolidation | Retained test |
|---|---|---|---|
| sultan-arity | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_pagemap_vma_boundaries_both_targets |
| nameidata-restoration | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_nameidata_retries_and_local_lookup_ownership |
| mount-reevaluation | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_mount_provenance_transition_inheritance_and_early_failure |
| gki-real-free-guard | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_mount_provenance_transition_inheritance_and_early_failure |
| sultan-real-free-guard | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_mount_provenance_transition_inheritance_and_early_failure |
| smaps-guard | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_smaps_actual_rollup_reacquire_branches |
| pagemap-callsite | DETECTED | DETECTED | test_lifecycle.LifecycleTests.test_pagemap_actual_read_lengths_offsets_and_partial_vmas |
| generated-literal | DETECTED | DETECTED | test_generator_regression.GeneratorEscapeRegressionTests.test_generated_patch51_literals_both_targets |

Seven required historical classes were tested; the generated free-guard class was tested separately for both targets. The literal mutation produced failing subtests for both targets. These are actual assertion/C-compile failures, not skipped tests or import/setup errors. All replacements were restored after each run.

## Production scope verification

Through the first two commits, no production generator, policy, workflow, baseline, manifest or published patch was changed. The authorized follow-up changes only pipeline publication control on the production side. These production patch SHA-256 values match the starting commit byte for byte:

- patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch: 9422b190e17145ee13cab48311110de5d76b1dc4a1518c9314dff8b16002e326
- patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch: 3aae69eb0d4e4311276f128332a57d6a8a858b0e3ec9a5aaf28a2eb32e41fc4f
- patches/xxksu/11_enable_susfs_for_ksu.patch: a0419c3ae48dbf93013cc56e0deb8330649b3089efb3bc711ccc7f6b772b020d

Task-owned scratch root: /tmp/xxksu-oracle-correction-nMKMSUEt. The permanent working repository is /home/ezhang/xxksu_susfs_patch and is not disposable. Final cleanup and unsigned-commit bookkeeping are recorded in HANDOFF.md and the completion response.


## Authorized full-state no-op fix

The pre-push audit disproved the original no-op consolidation ownership claim.
Forcing identical candidates through promotion passed all 237 consolidated
methods, while the removed non-delivery pipeline test failed. The new direct
publication-boundary test then exposed an existing production defect:
setting is_noop=True did not skip baseline/state/manifest processing or delivery.

The fix preserves the existing order: semantic/source gate, deterministic
candidate generation, candidate syntax and required exact-target validation,
independent reference check, then read-only publication planning. Equality is
never used to bypass any of those gates. Optional existing-delivery/raw-byte
verification is still read-only and retained when requested.

Metadata review found a legitimate update independent of patch bytes:
the existing writer advances xxKSU upstream.resolved_commit or a kernel target's
susfs.resolved_commit, and the corresponding authoritative upstream-state
commit. Manifest lineage derives from those baselines. The new planner preserves
these fields and GKI's compatibility-patch hash; it does not invent archive,
tree, bundle or pin changes, or replace upstream acceptance policy.

- FULL_STATE_NOOP: candidate bytes and applicable baseline/provenance fields are
  current and the existing manifest verifies. Return successfully before any
  publication writer or delivery call. Candidate/validation artifacts may still
  be written before that decision.
- METADATA_ONLY_PROMOTION: validated patch bytes match, but planned provenance,
  baseline or manifest state differs. Write only required metadata, preserve patch
  bytes, and perform one delivery transaction when write-back is requested.
- PATCH_PROMOTION: patch bytes differ. Write only changed targets, synchronize
  required metadata/shared manifest, and publish once.

Single-candidate PipelineResult exposes publication_state. The multi-candidate
API retains its tuple shape; its first boolean denotes any publication state
change, including metadata-only promotion. Both paths share read-only metadata
planning and the actual metadata publication boundary. Unchanged targets do not
independently trigger baseline rewrites. Multi-candidate accepted upstream commits
now synchronize upstream-state as well as baseline lineage. Malformed state JSON
with a supplied identity fails before publication rather than being silently
ignored.

The single-candidate early no-op regression is retained, strengthened with exact
protected-file snapshots and fail-fast sentinels at the real metadata publisher,
delivery, and production-file writes. The old writer helpers were replaced by a
read-only planner and shared publisher; the regression instruments that actual
publisher, not unused compatibility helpers.

Additional focused coverage:
- Equal bytes cannot bypass semantic/source, determinism, syntax, exact-target,
  or reference validation failures.
- Existing multi-no-op test traps metadata, file writes, and Git delivery.
- Existing mixed-target test now exercises both Sultan-changed/GKI-unchanged and
  GKI-changed/Sultan-unchanged. It verifies one commit, the exact changed-file set,
  and no writes to the unchanged target's patch or baseline.
- Existing both-changed test verifies one shared metadata publication.
- One metadata-only test covers real temporary Git delivery for the single path
  and multi path, then repeats the accepted state through FULL_STATE_NOOP.
  It verifies baseline/manifest/state-only commits and traps patch rewrites.
  These are publication tests; they do not replace upstream/kernel acceptance.

Final discovery: 240 methods, 70.609s, 0 failures, 0 errors, 0 skips.
The increase from 237 is the retained boundary regression, one gate-order test,
and one metadata-only publication test. No useful test was removed for count.

Mutation rerun, each restored afterward:
- DETECTED: Sultan append arity — test_lifecycle.LifecycleTests.test_pagemap_vma_boundaries_both_targets
- DETECTED: nd name restoration — test_lifecycle.LifecycleTests.test_nameidata_retries_and_local_lookup_ownership
- DETECTED: mount provenance reevaluation — test_lifecycle.LifecycleTests.test_mount_provenance_transition_inheritance_and_early_failure
- DETECTED: Sultan free guard — test_lifecycle.LifecycleTests.test_mount_provenance_transition_inheritance_and_early_failure
- DETECTED: GKI free guard — test_lifecycle.LifecycleTests.test_mount_provenance_transition_inheritance_and_early_failure
- DETECTED: smaps hidden guard — test_lifecycle.LifecycleTests.test_smaps_actual_rollup_reacquire_branches
- DETECTED: pagemap caller bypass — test_lifecycle.LifecycleTests.test_pagemap_actual_read_lengths_offsets_and_partial_vmas
- DETECTED: split generated literal — test_generator_regression.GeneratorEscapeRegressionTests.test_generated_patch51_literals_both_targets
- DETECTED: single full-noop fallthrough — test_pipeline.TestPipelineArchitecture.test_unchanged_candidate_never_enters_promotion_or_writeback
- DETECTED: multi full-noop fallthrough — test_delivery.TestPipelineDelivery.test_13_multi_candidate_both_unchanged_noop
- DETECTED: ignore legitimate metadata advancement — test_delivery.TestPipelineDelivery.test_metadata_only_promotion_then_full_noop

The last three mutations bypass single FULL_STATE_NOOP, bypass multi
FULL_STATE_NOOP, and incorrectly suppress a legitimate metadata advancement.
No permanent mutation framework was added.

Pre-push scope: production changes are limited to v2/pipeline.py. Generators,
semantic policy/gates, exact validators and Actions workflows are unchanged.
Patch 11, both Patch 51s, all BASELINE files, manifest and upstream-state remain
byte-identical to 0515823 and f83efeb. The source change does not regenerate or
publish kernel patches.
