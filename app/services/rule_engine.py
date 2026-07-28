from typing import Any


ALLOWED_OPERATORS = {
    "=": {"symbol": "=", "label": "Equals", "types": ["string", "number", "date"]},
    "!=": {"symbol": "!=", "label": "Not Equals", "types": ["string", "number", "date"]},
    ">": {"symbol": ">", "label": "Greater Than", "types": ["number", "date"]},
    "<": {"symbol": "<", "label": "Less Than", "types": ["number", "date"]},
    ">=": {"symbol": ">=", "label": "Greater or Equal", "types": ["number", "date"]},
    "<=": {"symbol": "<=", "label": "Less or Equal", "types": ["number", "date"]},
    "LIKE": {"symbol": "LIKE", "label": "Contains", "types": ["string"]},
    "NOT LIKE": {"symbol": "NOT LIKE", "label": "Does Not Contain", "types": ["string"]},
    "IN": {"symbol": "IN", "label": "In List", "types": ["string", "number"]},
    "NOT IN": {"symbol": "NOT IN", "label": "Not In List", "types": ["string", "number"]},
}


def validate_rules(rules: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []

    if not rules:
        errors.append("At least one rule is required")
        return errors

    open_groups = 0
    seen: set[tuple[Any, ...]] = set()

    for index, rule in enumerate(rules):
        position = index + 1
        rule_type = (rule.get("type") or "").strip()
        field = (rule.get("field") or "").strip()
        operator = (rule.get("operator") or "").strip()
        value = rule.get("value")
        next_operator = (rule.get("next_operator") or "AND").strip().upper()
        group_start = int(rule.get("group_start") or 0)
        group_end = int(rule.get("group_end") or 0)

        if not rule_type:
            errors.append(f"Rule {position}: type is required")
        if not field:
            errors.append(f"Rule {position}: field is required")
        if not operator:
            errors.append(f"Rule {position}: operator is required")
        elif operator not in ALLOWED_OPERATORS:
            errors.append(f"Rule {position}: invalid operator '{operator}'")

        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Rule {position}: value is required")

        if next_operator not in {"AND", "OR", "END"}:
            errors.append(f"Rule {position}: next operator must be AND, OR, or END")

        if group_start < 0 or group_end < 0:
            errors.append(f"Rule {position}: group markers cannot be negative")

        open_groups += group_start
        if group_end > open_groups:
            errors.append(f"Rule {position}: closing groups exceed open groups")
            open_groups = 0
        else:
            open_groups -= group_end

        signature = (rule_type, field, operator, str(value).strip().lower())
        if signature in seen:
            errors.append(f"Rule {position}: duplicate rule detected")
        seen.add(signature)

        if index < len(rules) - 1 and next_operator == "END":
            errors.append(f"Rule {position}: END is only allowed on the last rule")
        if index == len(rules) - 1 and next_operator not in {"AND", "OR", "END"}:
            errors.append(f"Rule {position}: invalid next operator")

    if open_groups != 0:
        errors.append("Unbalanced grouping brackets")

    return errors


def build_query_text(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return ""

    parts: list[str] = []
    for index, rule in enumerate(rules):
        start = "{" * int(rule.get("group_start") or 0)
        end = "}" * int(rule.get("group_end") or 0)
        value = rule.get("value")
        value_repr = f'"{value}"' if isinstance(value, str) else str(value)
        clause = (
            f"{start}{rule.get('field')} {rule.get('operator')} {value_repr}{end}"
        )
        parts.append(clause)
        if index < len(rules) - 1:
            next_op = (rule.get("next_operator") or "AND").upper()
            if next_op != "END":
                parts.append(next_op)

    return " ".join(parts)


def build_query_json(rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "group": [
            {
                "type": rule.get("type"),
                "field": rule.get("field"),
                "operator": rule.get("operator"),
                "value": rule.get("value"),
                "next": (rule.get("next_operator") or "AND").upper(),
                "group_start": int(rule.get("group_start") or 0),
                "group_end": int(rule.get("group_end") or 0),
            }
            for rule in rules
        ]
    }


def rules_to_dicts(rules: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for rule in rules:
        if hasattr(rule, "model_dump"):
            result.append(rule.model_dump())
        elif isinstance(rule, dict):
            result.append(rule)
        else:
            result.append(dict(rule))
    return result
