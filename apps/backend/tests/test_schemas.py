import pytest

from rpa_console.schemas import normalize_deployment, validate_inputs

SCHEMA = {"type": "object", "required": ["date"], "additionalProperties": False,
          "properties": {"date": {"type": "string", "format": "date"}}}


def test_declarations_fail_closed_and_old_deployments_remain_available():
    assert normalize_deployment({"app_id": "old"})["schema_status"] == "missing"
    assert normalize_deployment({"schema_status": "valid"})["schema_status"] == "invalid"
    assert normalize_deployment({"input_schema": {"type": "object", "$ref": "https://example.invalid"}})["schema_status"] == "invalid"
    invalid = normalize_deployment({"schema_status": "invalid", "input_schema": SCHEMA})
    assert "input_schema" not in invalid
    with pytest.raises(ValueError, match="损坏"):
        validate_inputs(invalid, {})
    validate_inputs({}, {"legacy": True})


def test_actual_dates_required_and_values_not_echoed():
    deployment = normalize_deployment({"form_schema": {"properties": {"inputs": SCHEMA}}})
    assert deployment["schema_status"] == "valid"
    validate_inputs(deployment, {"date": "2026-09-08"})
    for inputs in ({}, {"date": "2026-02-30"}, {"date": "SECRET"}, {"date": "2026-09-08", "extra": 1}):
        with pytest.raises(ValueError) as error:
            validate_inputs(deployment, inputs)
        assert "SECRET" not in str(error.value)
