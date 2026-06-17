import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = ROOT / ".github" / "scripts" / "contract_governance_gate.py"


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("contract_governance_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_contract_matrix_validation_fails_when_section_missing():
    gate = _load_gate_module()
    result = gate.GateResult(errors=[], warnings=[])

    gate.validate_lexicon_contract_matrix(
        result,
        "# Error-Code Referenz\n\n## 13a. Intent-Outcome Contract Codes (String-based)\n",
    )

    assert result.errors
    assert "Pflichtsektion" in result.errors[0]


def test_new_contract_code_requires_lexicon_entry():
    gate = _load_gate_module()
    result = gate.GateResult(errors=[], warnings=[])

    gate.validate_new_contract_codes_covered(
        result,
        added_lines=[
            (
                "El Servador/god_kaiser_server/src/services/example_contract.py",
                'code = "CONTRACT_NEW_CASE"',
            )
        ],
        lexicon_content="# Error-Code Referenz\n",
    )

    assert result.errors
    assert "CONTRACT_NEW_CASE" in result.errors[0]
