"""Typed JSON conversion. No type tags, pickle, or data-directed imports."""

import base64
from dataclasses import fields, is_dataclass
from pathlib import Path
import types
from typing import Any, Union, get_args, get_origin, get_type_hints

from ..contracts.codec import check_json_tree
from ..contracts.errors import ControlError


def to_wire(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_wire(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, dict):
        return {str(k): to_wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, frozenset, set)):
        return [to_wire(v) for v in value]
    check_json_tree(value)
    return value


def from_wire(value, expected):
    def invalid():
        raise ControlError("SCHEMA_INVALID", "plugin value does not match its declared type")
    if expected is Any:
        check_json_tree(value)
        return value
    origin, arguments = get_origin(expected), get_args(expected)
    if origin in (Union, types.UnionType):
        for candidate in arguments:
            try:
                return from_wire(value, candidate)
            except ControlError:
                pass
        invalid()
    if expected is type(None):
        if value is not None:
            invalid()
        return None
    if expected is Path:
        if not isinstance(value, str) or "\x00" in value:
            invalid()
        return Path(value)
    if expected is bytes:
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, TypeError):
            invalid()
    if is_dataclass(expected):
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(expected)}:
            invalid()
        hints = get_type_hints(expected)
        try:
            return expected(**{key: from_wire(item, hints[key]) for key, item in value.items()})
        except TypeError:
            invalid()
    if origin in (list, tuple, set, frozenset):
        if not isinstance(value, list):
            invalid()
        item_type = arguments[0] if arguments else Any
        items = [from_wire(item, item_type) for item in value]
        return (origin(items) if origin is not tuple else tuple(items))
    if origin is dict:
        if not isinstance(value, dict):
            invalid()
        key_type, item_type = arguments
        result = {}
        for key, item in value.items():
            if key_type is int and isinstance(key, str) and key.isdecimal():
                key = int(key)
            else:
                key = from_wire(key, key_type)
            result[key] = from_wire(item, item_type)
        return result
    if expected in (str, int, bool, float):
        if type(value) is not expected:
            invalid()
        check_json_tree(value)
        return value
    invalid()
