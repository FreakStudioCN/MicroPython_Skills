#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic JSON Schema validator for toolchain intermediate files.
Usage:
  python validate_json.py --schema <schema.json> --json <target.json>
Exit codes:
  0 = valid
  1 = validation errors found
  2 = file not found / JSON parse error
"""

import argparse
import json
import sys
import os

try:
    import jsonschema
except ImportError:
    print("[FATAL] jsonschema not installed. Run: pip install jsonschema")
    sys.exit(2)


def load_json(path):
    """Load a JSON file. Returns (data, None) or (None, error_message)."""
    if not os.path.isfile(path):
        return None, "file not found: {}".format(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, "JSON parse error in {}: {}".format(path, e)
    except Exception as e:
        return None, "failed to read {}: {}".format(path, e)


def validate(schema_data, target_data, target_path):
    """Validate target_data against schema_data. Returns list of error strings."""
    errors = []
    validator_cls = None

    # Try strict validation first
    try:
        validator_cls = jsonschema.validators.validator_for(schema_data)
    except Exception:
        # Fall back to draft-07
        validator_cls = jsonschema.Draft7Validator

    try:
        validator = validator_cls(schema_data)
    except Exception as e:
        return ["schema is invalid: {}".format(e)]

    try:
        for err in validator.iter_errors(target_data):
            path_str = ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "(root)"
            errors.append("{}: {}".format(path_str, err.message))
    except Exception as e:
        errors.append("validation raised exception: {}".format(e))

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate JSON against schema")
    parser.add_argument("--schema", required=True, help="Path to JSON schema file")
    parser.add_argument("--json", required=True, help="Path to target JSON file")
    args = parser.parse_args()

    # Load schema
    schema_data, schema_err = load_json(args.schema)
    if schema_err:
        print("[FAIL] Schema: {}".format(schema_err))
        sys.exit(2)

    # Load target
    target_data, target_err = load_json(args.json)
    if target_err:
        print("[FAIL] Target: {}".format(target_err))
        sys.exit(2)

    # Validate
    errors = validate(schema_data, target_data, args.json)

    if errors:
        print("[FAIL] {} validation error(s) in {}:".format(len(errors), args.json))
        for e in errors:
            print("  - {}".format(e))
        sys.exit(1)

    print("[OK] {} is valid".format(args.json))
    sys.exit(0)


if __name__ == "__main__":
    main()
