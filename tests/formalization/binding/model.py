"""model.py — SOMA Binding Contract v0 Formal Model.

Defines the minimal, decidable, finite representation for expressible bindings
without requiring full dependent types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class TermKind(Enum):
    VALUE_REF = "ValueRef"
    ARTIFACT_IDENTITY = "ArtifactIdentity"
    STABLE_DIGEST = "StableDigest"
    STATE_REF = "StateRef"
    LITERAL = "Literal"
    TRUSTED_OPAQUE_REF = "TrustedOpaqueRef"


@dataclass(frozen=True)
class BindingTerm:
    kind: TermKind
    val_type: str
    identity_key: str
    digest: Optional[str] = None
    algorithm: Optional[str] = None
    lineage_ids: frozenset[str] = field(default_factory=frozenset)
    domain: Optional[str] = None

    @staticmethod
    def value_ref(name: str, val_type: str, lineage_ids: Optional[Set[str]] = None, digest: Optional[str] = None) -> BindingTerm:
        return BindingTerm(
            kind=TermKind.VALUE_REF,
            val_type=val_type,
            identity_key=name,
            digest=digest,
            lineage_ids=frozenset(lineage_ids or set()),
        )

    @staticmethod
    def stable_digest(algorithm: str, hex_hash: str, val_type: str = "Artifact") -> BindingTerm:
        return BindingTerm(
            kind=TermKind.STABLE_DIGEST,
            val_type=val_type,
            identity_key=f"{algorithm}:{hex_hash}",
            digest=hex_hash,
            algorithm=algorithm,
        )

    @staticmethod
    def artifact_identity(kind_name: str, uri: str, digest: Optional[str] = None) -> BindingTerm:
        return BindingTerm(
            kind=TermKind.ARTIFACT_IDENTITY,
            val_type="Artifact",
            identity_key=f"{kind_name}::{uri}",
            digest=digest,
        )

    @staticmethod
    def state_ref(domain: str, resource_id: str) -> BindingTerm:
        return BindingTerm(
            kind=TermKind.STATE_REF,
            val_type="State",
            identity_key=f"{domain}::{resource_id}",
            domain=domain,
        )

    @staticmethod
    def literal(val: Any, val_type: str) -> BindingTerm:
        return BindingTerm(
            kind=TermKind.LITERAL,
            val_type=val_type,
            identity_key=repr(val),
        )

    @staticmethod
    def opaque_ref(origin: str, token: str, val_type: str = "Unknown") -> BindingTerm:
        return BindingTerm(
            kind=TermKind.TRUSTED_OPAQUE_REF,
            val_type=val_type,
            identity_key=f"opaque::{origin}::{token}",
        )


def has_concrete_contradiction(a: BindingTerm, b: BindingTerm) -> bool:
    """R1 / R4: Check if two terms possess explicit contradictory concrete evidence."""
    # 1. Stable digest algorithm mismatch
    if a.kind == TermKind.STABLE_DIGEST and b.kind == TermKind.STABLE_DIGEST:
        if a.algorithm != b.algorithm or a.digest != b.digest:
            return True

    # 2. Concrete digest contradiction across artifacts or value refs
    if a.digest is not None and b.digest is not None and a.digest != b.digest:
        return True

    # 3. Literal value mismatch
    if a.kind == TermKind.LITERAL and b.kind == TermKind.LITERAL:
        if a.identity_key != b.identity_key:
            return True

    return False


@dataclass(frozen=True)
class BindingRequirement:
    predicate: str
    subject: BindingTerm
    base: Optional[BindingTerm] = None
    scope: Optional[BindingTerm] = None
    validity: Optional[BindingTerm] = None


@dataclass(frozen=True)
class BindingEvidence:
    predicate: str
    subject_binding: BindingTerm
    base_binding: Optional[BindingTerm] = None
    scope_binding: Optional[BindingTerm] = None
    validity_binding: Optional[BindingTerm] = None
    provenance: str = "Concrete"  # "Concrete" | "Delegated" | "External" | "Merged"
    currentness_witness: Optional[bool] = None  # None = unknown, True = current, False = stale
    validity_witness: Optional[bool] = None     # None = unknown, True = valid, False = expired/invalid


@dataclass(frozen=True)
class DynamicCheck:
    check_type: str
    required_term: Optional[BindingTerm]
    evidence_term: Optional[BindingTerm]
    details: str


@dataclass(frozen=True)
class SymbolicMatch:
    is_proved: bool = False
    is_refuted: bool = False
    refute_reason: Optional[str] = None
    deferred_checks: tuple[DynamicCheck, ...] = field(default_factory=tuple)

    @staticmethod
    def proved() -> SymbolicMatch:
        return SymbolicMatch(is_proved=True)

    @staticmethod
    def refuted(reason: str) -> SymbolicMatch:
        return SymbolicMatch(is_refuted=True, refute_reason=reason)

    @staticmethod
    def deferred(checks: List[DynamicCheck]) -> SymbolicMatch:
        return SymbolicMatch(deferred_checks=tuple(checks))


@dataclass
class PathFactContext:
    known_aliases: dict[str, str] = field(default_factory=dict)
    known_equal_digests: set[tuple[str, str]] = field(default_factory=set)

    def are_equal(self, a: BindingTerm, b: BindingTerm, mutations: Optional[dict[str, bool]] = None) -> bool:
        muts = mutations or {}

        # R1 / R4: Concrete contradiction strictly dominates aliases and lexical shortcuts
        if has_concrete_contradiction(a, b):
            if not muts.get("m3_alias_overrides_contradiction", False):
                return False

        if a == b:
            return True

        # Lexical identity key match
        if a.identity_key == b.identity_key:
            if a.kind == b.kind:
                # R1: Same URI with contradictory digests cannot be equal
                if a.digest is not None and b.digest is not None and a.digest != b.digest:
                    return False
                return True

        # Digest match
        if a.digest and b.digest and a.digest == b.digest:
            if a.algorithm and b.algorithm and a.algorithm != b.algorithm:
                return False
            return True

        # Aliases in PathFactContext
        if self.known_aliases.get(a.identity_key) == b.identity_key:
            return True
        if self.known_aliases.get(b.identity_key) == a.identity_key:
            return True

        if a.digest and b.digest:
            if (a.digest, b.digest) in self.known_equal_digests or (b.digest, a.digest) in self.known_equal_digests:
                return True

        return False


def match_term(
    req: BindingTerm,
    ev: BindingTerm,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
) -> SymbolicMatch:
    muts = mutations or {}

    # Mutation M1: type equality => subject equality shortcut (FAIL B1)
    if muts.get("m1_type_equality_shortcut", False):
        if req.val_type == ev.val_type:
            return SymbolicMatch.proved()

    # Mutation M2: lineage overlap => subject equality shortcut (FAIL B2)
    if muts.get("m2_lineage_overlap_shortcut", False):
        if req.lineage_ids and ev.lineage_ids and (req.lineage_ids & ev.lineage_ids):
            return SymbolicMatch.proved()

    # R1 / R4: Concrete contradiction check
    if has_concrete_contradiction(req, ev):
        if not muts.get("m3_alias_overrides_contradiction", False):
            if muts.get("m3_concrete_mismatch_deferred", False):
                return SymbolicMatch.deferred([
                    DynamicCheck("CheckSubjectIdentity", req, ev, "Mutant deferred concrete mismatch")
                ])
            return SymbolicMatch.refuted(f"ContradictoryIdentity: {req.identity_key} != {ev.identity_key}")

    # Direct / proven equality
    if ctx.are_equal(req, ev, muts):
        return SymbolicMatch.proved()

    # Concrete known digests or literals that mismatch -> Refuted (B3)
    both_concrete = (
        (req.kind in (TermKind.STABLE_DIGEST, TermKind.LITERAL, TermKind.ARTIFACT_IDENTITY)
         or (req.kind == TermKind.VALUE_REF and req.digest is not None))
        and
        (ev.kind in (TermKind.STABLE_DIGEST, TermKind.LITERAL, TermKind.ARTIFACT_IDENTITY)
         or (ev.kind == TermKind.VALUE_REF and ev.digest is not None))
    )

    if both_concrete:
        if muts.get("m3_concrete_mismatch_deferred", False):
            return SymbolicMatch.deferred([
                DynamicCheck("CheckSubjectIdentity", req, ev, "Mutant deferred concrete mismatch")
            ])
        return SymbolicMatch.refuted(f"ConcreteMismatch: {req.identity_key} != {ev.identity_key}")

    # Either is opaque or unverified ValueRef without digest -> Deferred (B4)
    if muts.get("m4_opaque_unknown_refuted", False):
        return SymbolicMatch.refuted("MutantRefutedOpaque")

    return SymbolicMatch.deferred([
        DynamicCheck("CheckSubjectIdentity", req, ev, f"Dynamic identity verification needed between {req.identity_key} and {ev.identity_key}")
    ])


def match_binding(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
) -> SymbolicMatch:
    muts = mutations or {}

    # 1. Predicate check (B11)
    if not muts.get("m9_predicate_mismatch_ignored", False):
        if req.predicate != ev.predicate:
            return SymbolicMatch.refuted(f"PredicateMismatch: expected {req.predicate}, got {ev.predicate}")

    all_checks: List[DynamicCheck] = []

    # 2. Subject check
    subj_match = match_term(req.subject, ev.subject_binding, ctx, muts)
    if subj_match.is_refuted and not muts.get("m8_deferred_overrides_refuted", False):
        return subj_match
    all_checks.extend(subj_match.deferred_checks)

    # 3. Base state check (B5, B6)
    if req.base is not None and not muts.get("m5_ignore_base_binding", False):
        if ev.base_binding is None:
            return SymbolicMatch.refuted("MissingBaseBinding: requirement specified base state but evidence has none")
        
        base_match = match_term(req.base, ev.base_binding, ctx, muts)
        if base_match.is_refuted and not muts.get("m8_deferred_overrides_refuted", False):
            return base_match
        all_checks.extend(base_match.deferred_checks)

        # Currentness verification (B6)
        if req.base.kind == TermKind.STATE_REF:
            if not muts.get("m6_lexical_state_current_shortcut", False):
                if ev.currentness_witness is False:
                    if not muts.get("m8_deferred_overrides_refuted", False):
                        return SymbolicMatch.refuted("StaleBaseState: witness reported stale base state")
                elif ev.currentness_witness is None:
                    all_checks.append(
                        DynamicCheck("CheckCurrentBase", req.base, ev.base_binding, "Dynamic currentness witness required")
                    )

    # 4. Scope check
    if req.scope is not None:
        if ev.scope_binding is None:
            return SymbolicMatch.refuted("MissingScopeBinding")
        scope_match = match_term(req.scope, ev.scope_binding, ctx, muts)
        if scope_match.is_refuted and not muts.get("m8_deferred_overrides_refuted", False):
            return scope_match
        all_checks.extend(scope_match.deferred_checks)

    # 5. Validity check (R2: Bounded validity/freshness rule)
    if req.validity is not None:
        if ev.validity_witness is False:
            if not muts.get("m8_deferred_overrides_refuted", False):
                return SymbolicMatch.refuted("ExpiredValidity: validity witness reported expired/invalid")
        elif ev.validity_witness is True:
            pass  # Proved statically valid
        elif ev.validity_witness is None:
            all_checks.append(
                DynamicCheck("CheckValidity", req.validity, ev.validity_binding, "Dynamic validity witness required")
            )

    # Mutation M7: drop deferred checks (FAIL B7 / B9)
    if muts.get("m7_drop_deferred_checks", False):
        all_checks.clear()

    # Mutation M8: Deferred overrides Refuted (FAIL B8)
    if muts.get("m8_deferred_overrides_refuted", False) and all_checks:
        return SymbolicMatch.deferred(all_checks)

    if subj_match.is_refuted:
        return subj_match

    # Decision aggregation (B7, B8, B9)
    if not all_checks:
        return SymbolicMatch.proved()
    
    return SymbolicMatch.deferred(all_checks)


def dynamic_gate_resolve(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    witness_proofs: Dict[str, bool],
    mutations: Optional[dict[str, Any]] = None,
) -> Tuple[SymbolicMatch, BindingEvidence]:
    """R3: Minimal executable dynamic gate resolution operation for Deferred checks (B10).
    
    Proves that dynamic resolution validates the original binding without rebinding or widening.
    """
    muts = mutations or {}

    match_res = match_binding(req, ev, ctx, muts)
    if match_res.is_refuted:
        return match_res, ev

    # Check all dynamic obligations against provided witness proofs
    for check in match_res.deferred_checks:
        if not witness_proofs.get(check.check_type, False):
            return SymbolicMatch.refuted(f"DynamicCheckFailed: {check.check_type}"), ev

    # Mutation M11: dynamic resolution rebinds subject (FAIL B10)
    if muts.get("m11_dynamic_resolution_rebinds_subject", False):
        widened_subj = muts.get("widened_subject", ev.subject_binding)
        mutated_ev = BindingEvidence(
            predicate=ev.predicate,
            subject_binding=widened_subj,
            base_binding=ev.base_binding,
            scope_binding=ev.scope_binding,
            validity_binding=ev.validity_binding,
            provenance="DynamicGateWidened",
            currentness_witness=True,
            validity_witness=True,
        )
        return SymbolicMatch.proved(), mutated_ev

    # Sound dynamic resolution: validates the EXACT original binding
    resolved_ev = BindingEvidence(
        predicate=ev.predicate,
        subject_binding=ev.subject_binding,
        base_binding=ev.base_binding,
        scope_binding=ev.scope_binding,
        validity_binding=ev.validity_binding,
        provenance=ev.provenance,
        currentness_witness=True,
        validity_witness=True,
    )
    return SymbolicMatch.proved(), resolved_ev


def conservative_cfg_join(
    path_a: BindingEvidence,
    path_b: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
) -> Optional[BindingEvidence]:
    """Conservative merge of bindings from divergent CFG branches (B12)."""
    muts = mutations or {}

    # Mutation M10: conflicting CFG join picks one branch (FAIL B12)
    if muts.get("m10_cfg_join_picks_branch", False):
        return path_a

    if path_a.predicate != path_b.predicate:
        return None

    # Merge subject
    if ctx.are_equal(path_a.subject_binding, path_b.subject_binding, muts):
        merged_subject = path_a.subject_binding
    else:
        return None

    # Merge base
    if path_a.base_binding == path_b.base_binding:
        merged_base = path_a.base_binding
    else:
        merged_base = None

    merged_witness = path_a.currentness_witness if path_a.currentness_witness == path_b.currentness_witness else None
    merged_validity = path_a.validity_witness if path_a.validity_witness == path_b.validity_witness else None

    return BindingEvidence(
        predicate=path_a.predicate,
        subject_binding=merged_subject,
        base_binding=merged_base,
        scope_binding=path_a.scope_binding if path_a.scope_binding == path_b.scope_binding else None,
        validity_binding=path_a.validity_binding if path_a.validity_binding == path_b.validity_binding else None,
        provenance="Merged",
        currentness_witness=merged_witness,
        validity_witness=merged_validity,
    )
