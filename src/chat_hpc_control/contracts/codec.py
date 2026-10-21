"""Strict JSON at every trust boundary, with packaged versioned schemas."""

import copy
from functools import lru_cache
from importlib.resources import files
import json
import math
from typing import Any

from jsonschema import Draft202012Validator

from .errors import ControlError
from .task import JsonObject, ResourceRequest, TaskSpec
from .tools import ToolResponse

MAX_SAFE_INTEGER = 2**53 - 1
MAX_JSON_BYTES = 8 * 1024 * 1024


def _invalid(message: str):
    raise ControlError("SCHEMA_INVALID", message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid("duplicate JSON object key")
        result[key] = value
    return result


def check_json_tree(value: Any, *, allow_float: bool = True):
    if isinstance(value, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            _invalid("unpaired Unicode surrogate")
    elif value is None or isinstance(value, bool):
        return
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            _invalid("integer exceeds safe range")
    elif isinstance(value, float):
        if not allow_float or not math.isfinite(value):
            _invalid("floating value is not permitted")
    elif isinstance(value, list):
        for item in value:
            check_json_tree(item, allow_float=allow_float)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _invalid("JSON keys must be strings")
            check_json_tree(key, allow_float=allow_float)
            check_json_tree(item, allow_float=allow_float)
    else:
        _invalid("not a JSON value")


def decode_json(raw: bytes) -> JsonObject:
    if len(raw) > MAX_JSON_BYTES:
        _invalid("JSON message exceeds byte limit")
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            _invalid("UTF-8 BOM is not accepted")
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                         parse_constant=lambda _: _invalid("nonfinite JSON number"))
        check_json_tree(obj)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ControlError("SCHEMA_INVALID", "invalid UTF-8 JSON document") from exc
    if not isinstance(obj, dict):
        _invalid("top-level JSON must be an object")
    return obj


@lru_cache(maxsize=16)
def schema_validator(name: str) -> Draft202012Validator:
    schema = json.loads(files("chat_hpc_control").joinpath("schemas", name + ".json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_schema(name: str, obj: JsonObject):
    check_json_tree(obj)
    error = next(schema_validator(name).iter_errors(obj), None)
    if error:
        path = "/".join(map(str, error.absolute_path)) or "/"
        _invalid(f"{name}: {path} violates {error.validator}")


def parse_task(raw: bytes) -> TaskSpec:
    obj = decode_json(raw)
    check_json_tree(obj, allow_float=False)
    validate_schema("task-v1", obj)
    contract = obj["expected_results"]
    if contract:
        ids = [r["record_id"] for r in contract["records"]]
        if len(ids) != len(set(ids)):
            _invalid("duplicate expected record ID")
    values = copy.deepcopy(obj)
    values["resources"] = ResourceRequest(**values["resources"])
    return TaskSpec(**values)


def encode_response(value: ToolResponse) -> bytes:
    obj = value.to_dict()
    validate_schema("tool-response-v1", obj)
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
