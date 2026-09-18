"""Handler ABI compatibility validation for V2.8."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ..model.result import (
    AbiLinkageConflict,
    AbiSignatureMismatch,
    AmbiguousAbiMapping,
    HandlerABIConflict,
    MissingAbiEvidence,
    ValidationResult,
    ValidationStatus,
)
from ..source.bundle import SourceBundle


KNOWN_C_BASE_TYPES = {
    "void", "int", "char", "long", "short", "unsigned", "signed",
    "float", "double", "size_t", "ssize_t", "uint32_t", "uint64_t", "u32", "u64", "bool",
}


def normalize_c_type(raw_type: str) -> str:
    """Normalize a C parameter or return type to canonical form, dropping parameter variable names."""
    t = re.sub(r"\s+", " ", raw_type).strip()
    if not t:
        return ""

    # If there is an asterisk, the type extends up to the last asterisk.
    if "*" in t:
        last_star = t.rfind("*")
        type_part = t[:last_star + 1].strip()
    else:
        words = t.split()
        if len(words) > 1 and words[-1] not in KNOWN_C_BASE_TYPES:
            type_part = " ".join(words[:-1])
        else:
            type_part = t

    # Normalize whitespace around asterisks
    type_part = re.sub(r"\s*\*\s*", "*", type_part)
    # Ensure space before asterisks
    type_part = re.sub(r"([^*])(\*+)", r"\1 \2", type_part)
    return type_part.strip()


@dataclass(frozen=True)
class AbiSignature:
    symbol: str
    return_type: str
    parameters: Tuple[str, ...]
    linkage: str = "extern"  # "extern" or "static"
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    raw_signature: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "return_type", normalize_c_type(self.return_type))
        object.__setattr__(self, "parameters", tuple(normalize_c_type(p) for p in self.parameters))


@dataclass(frozen=True)
class AbiContract:
    symbol: str
    return_type: str
    parameters: Tuple[str, ...]
    linkage: str = "extern"
    semantic_path: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "return_type", normalize_c_type(self.return_type))
        object.__setattr__(self, "parameters", tuple(normalize_c_type(p) for p in self.parameters))


DEFAULT_ABI_CONTRACTS: Tuple[AbiContract, ...] = (
    AbiContract(
        symbol="ksu_handle_execveat",
        return_type="int",
        parameters=("int *", "struct filename **", "void *", "void *", "int *"),
        linkage="extern",
        semantic_path="exec",
        description="xxKSU execveat handler interface",
    ),
    AbiContract(
        symbol="ksu_handle_faccessat",
        return_type="int",
        parameters=("int *", "const char __user **", "int *", "int *"),
        linkage="extern",
        semantic_path="access",
        description="xxKSU user-pointer faccessat handler interface",
    ),
    AbiContract(
        symbol="ksu_handle_stat",
        return_type="int",
        parameters=("int *", "const char __user **", "int *"),
        linkage="extern",
        semantic_path="stat",
        description="xxKSU user-pointer stat handler interface",
    ),
    AbiContract(
        symbol="ksu_handle_newfstat_ret",
        return_type="void",
        parameters=("unsigned int *", "struct stat __user **"),
        linkage="extern",
        semantic_path="fstat-return",
        description="xxKSU 64-bit newfstat return handler interface",
    ),
    AbiContract(
        symbol="ksu_handle_fstat64_ret",
        return_type="void",
        parameters=("unsigned long *", "struct stat64 __user **"),
        linkage="extern",
        semantic_path="fstat-return",
        description="xxKSU 32-bit fstat64 return handler interface",
    ),
    AbiContract(
        symbol="ksu_handle_sys_reboot",
        return_type="int",
        parameters=("int", "int", "unsigned int", "void __user **"),
        linkage="extern",
        semantic_path="reboot",
        description="xxKSU sys_reboot handler interface",
    ),
    AbiContract(
        symbol="ksu_bprm_check",
        return_type="int",
        parameters=("struct linux_binprm *",),
        linkage="extern",
        semantic_path="manual-security",
        description="Manual-security bprm check hook interface",
    ),
    AbiContract(
        symbol="ksu_inode_rename",
        return_type="int",
        parameters=("struct inode *", "struct dentry *", "struct inode *", "struct dentry *"),
        linkage="extern",
        semantic_path="manual-security",
        description="Manual-security inode rename hook interface",
    ),
    AbiContract(
        symbol="ksu_file_permission",
        return_type="int",
        parameters=("struct file *", "int"),
        linkage="extern",
        semantic_path="manual-security",
        description="Manual-security file permission hook interface",
    ),
    AbiContract(
        symbol="ksu_task_fix_setuid",
        return_type="int",
        parameters=("struct cred *", "const struct cred *", "int"),
        linkage="extern",
        semantic_path="manual-security",
        description="Manual-security task_fix_setuid hook interface",
    ),
    AbiContract(
        symbol="ksu_hide_setprocattr",
        return_type="int",
        parameters=("const char *", "void *", "size_t"),
        linkage="extern",
        semantic_path="manual-security",
        description="Manual-security setprocattr hiding hook interface",
    ),
)


def _strip_c_comments(code: str) -> str:
    """Replace block comments with newlines and strip line comments."""
    def replace_block(match: re.Match) -> str:
        return "\n" * match.group(0).count("\n")
    code = re.sub(r"/\*.*?\*/", replace_block, code, flags=re.DOTALL)
    code = re.sub(r"//[^\n]*", "", code)
    return code


def parse_c_signatures(
    content: str,
    symbol: str,
    source_file: Optional[str] = None,
) -> list[AbiSignature]:
    """Extract C declarations or definitions for symbol from C source code."""
    clean = _strip_c_comments(content)
    pattern = re.compile(
        r"(?P<preamble>[a-zA-Z0-9_* \t\n\r]+?)\b" + re.escape(symbol) + r"\s*\(\s*(?P<params>[^)]*?)\s*\)\s*(?P<tail>;|\{)?",
        re.MULTILINE,
    )
    results: list[AbiSignature] = []
    known_return_types = {"void", "int", "long", "unsigned int", "unsigned long", "bool", "size_t", "ssize_t"}

    for m in pattern.finditer(clean):
        preamble = m.group("preamble")
        params_str = m.group("params")

        # Find boundary after preceding statement/macro
        last_sep = max(
            preamble.rfind(";"), preamble.rfind("{"), preamble.rfind("}"),
            preamble.rfind("#"), preamble.rfind("\n"),
        )
        if last_sep != -1:
            chunk = preamble[last_sep + 1:].strip()
        else:
            chunk = preamble.strip()

        if not chunk:
            continue

        words = chunk.split()
        linkage = "extern"
        if "static" in words:
            linkage = "static"
            words = [w for w in words if w not in ("static", "inline", "__always_inline")]
        if "extern" in words:
            linkage = "extern"
            words = [w for w in words if w != "extern"]
        words = [w for w in words if w not in ("asmlinkage", "__visible")]

        if not words:
            continue
        ret_type = " ".join(words)
        if not (ret_type in known_return_types or ret_type.endswith("*")):
            continue

        if not params_str.strip() or params_str.strip() == "void":
            parsed_params = ()
        else:
            parsed_params = tuple(normalize_c_type(p) for p in params_str.split(","))

        line_no = clean[:m.start()].count("\n") + 1
        results.append(AbiSignature(
            symbol=symbol,
            return_type=ret_type,
            parameters=parsed_params,
            linkage=linkage,
            source_file=source_file,
            line_number=line_no,
            raw_signature=m.group(0).strip(),
        ))

    return results


def validate_signature_against_contract(
    sig: AbiSignature,
    contract: AbiContract,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate a parsed AbiSignature against an expected AbiContract."""
    if sig.symbol != contract.symbol:
        res = ValidationResult(
            validator_id="validation.abi.signature",
            status=ValidationStatus.FAIL,
            target=contract.symbol,
            details=f"Symbol name mismatch: signature has '{sig.symbol}', contract expected '{contract.symbol}'",
            path=sig.source_file,
            line=sig.line_number,
            context=sig.raw_signature,
            metadata={"error_type": "HandlerABIConflict"},
        )
        if raise_on_failure:
            raise HandlerABIConflict(res.details)
        return res

    # 1. Linkage check
    if sig.linkage != contract.linkage:
        res = ValidationResult(
            validator_id="validation.abi.linkage",
            status=ValidationStatus.FAIL,
            target=contract.symbol,
            details=(
                f"Linkage conflict for '{contract.symbol}': expected '{contract.linkage}', "
                f"got '{sig.linkage}'"
            ),
            path=sig.source_file,
            line=sig.line_number,
            context=sig.raw_signature,
            metadata={"error_type": "AbiLinkageConflict", "symbol": contract.symbol},
        )
        if raise_on_failure:
            raise AbiLinkageConflict(res.details)
        return res

    # 2. Argument count check
    if len(sig.parameters) != len(contract.parameters):
        res = ValidationResult(
            validator_id="validation.abi.signature",
            status=ValidationStatus.FAIL,
            target=contract.symbol,
            details=(
                f"Parameter count mismatch for '{contract.symbol}': expected {len(contract.parameters)}, "
                f"got {len(sig.parameters)} ({sig.parameters})"
            ),
            path=sig.source_file,
            line=sig.line_number,
            context=sig.raw_signature,
            metadata={"error_type": "AbiSignatureMismatch", "symbol": contract.symbol},
        )
        if raise_on_failure:
            raise AbiSignatureMismatch(res.details)
        return res

    # 3. Parameter types check
    for idx, (p_act, p_exp) in enumerate(zip(sig.parameters, contract.parameters)):
        if p_act != p_exp:
            res = ValidationResult(
                validator_id="validation.abi.signature",
                status=ValidationStatus.FAIL,
                target=contract.symbol,
                details=(
                    f"Parameter {idx} type mismatch for '{contract.symbol}': expected '{p_exp}', "
                    f"got '{p_act}'"
                ),
                path=sig.source_file,
                line=sig.line_number,
                context=sig.raw_signature,
                metadata={"error_type": "AbiSignatureMismatch", "symbol": contract.symbol},
            )
            if raise_on_failure:
                raise AbiSignatureMismatch(res.details)
            return res

    # 4. Return type check
    if sig.return_type != contract.return_type:
        res = ValidationResult(
            validator_id="validation.abi.signature",
            status=ValidationStatus.FAIL,
            target=contract.symbol,
            details=(
                f"Return type mismatch for '{contract.symbol}': expected '{contract.return_type}', "
                f"got '{sig.return_type}'"
            ),
            path=sig.source_file,
            line=sig.line_number,
            context=sig.raw_signature,
            metadata={"error_type": "AbiSignatureMismatch", "symbol": contract.symbol},
        )
        if raise_on_failure:
            raise AbiSignatureMismatch(res.details)
        return res

    return ValidationResult(
        validator_id="validation.abi.signature",
        status=ValidationStatus.PASS,
        target=contract.symbol,
        details=f"ABI signature matches contract: {contract.return_type} {contract.symbol}({', '.join(contract.parameters)})",
        path=sig.source_file,
        line=sig.line_number,
        context=sig.raw_signature,
        metadata={"symbol": contract.symbol},
    )


def validate_abi(
    *,
    bundle: Optional[SourceBundle] = None,
    signatures: Optional[Sequence[AbiSignature]] = None,
    contracts: Sequence[AbiContract] = DEFAULT_ABI_CONTRACTS,
    allow_synthetic: bool = False,
    evidence_kind: Optional[str] = None,
    raise_on_failure: bool = False,
) -> Tuple[ValidationResult, ...]:
    """Validate handler signatures against declared ABI contracts."""
    results: list[ValidationResult] = []

    if not allow_synthetic and evidence_kind in ("SYNTHETIC", "UNVERIFIED"):
        res = ValidationResult(
            validator_id="validation.abi.evidence",
            status=ValidationStatus.FAIL,
            target="abi_evidence",
            details=f"Synthetic or unverified ABI evidence '{evidence_kind}' rejected in production",
            metadata={"error_type": "MissingAbiEvidence"},
        )
        results.append(res)
        if raise_on_failure:
            raise MissingAbiEvidence(res.details)

    contracts_by_symbol = {c.symbol: c for c in contracts}

    # 1. Directly supplied signatures
    if signatures is not None:
        for sig in signatures:
            contract = contracts_by_symbol.get(sig.symbol)
            if contract is None:
                continue
            res = validate_signature_against_contract(sig, contract, raise_on_failure=raise_on_failure)
            results.append(res)

    # 2. Extract signatures from bundle if provided
    if bundle is not None:
        for contract in contracts:
            found_sigs: list[AbiSignature] = []
            for file_entry in bundle.files:
                parsed = parse_c_signatures(file_entry.content, contract.symbol, source_file=file_entry.path)
                found_sigs.extend(parsed)

            if not found_sigs:
                # If neither signatures nor bundle has this symbol, check if required
                continue

            # Check for multiple conflicting declarations
            first_sig = found_sigs[0]
            for other_sig in found_sigs[1:]:
                if (
                    other_sig.return_type != first_sig.return_type
                    or other_sig.parameters != first_sig.parameters
                    or other_sig.linkage != first_sig.linkage
                ):
                    res = ValidationResult(
                        validator_id="validation.abi.mapping",
                        status=ValidationStatus.FAIL,
                        target=contract.symbol,
                        details=(
                            f"Ambiguous conflicting ABI declarations found for '{contract.symbol}': "
                            f"{first_sig.return_type}({', '.join(first_sig.parameters)}) at {first_sig.source_file}:{first_sig.line_number} vs "
                            f"{other_sig.return_type}({', '.join(other_sig.parameters)}) at {other_sig.source_file}:{other_sig.line_number}"
                        ),
                        path=first_sig.source_file,
                        line=first_sig.line_number,
                        metadata={"error_type": "AmbiguousAbiMapping", "symbol": contract.symbol},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise AmbiguousAbiMapping(res.details)
                    break
            else:
                res = validate_signature_against_contract(first_sig, contract, raise_on_failure=raise_on_failure)
                results.append(res)

    return tuple(results)
