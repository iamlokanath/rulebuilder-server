from app.services.rule_engine import build_query_text, validate_rules


def test_validate_empty_rules():
    errors = validate_rules([])
    assert "At least one rule is required" in errors


def test_validate_balanced_groups():
    rules = [
        {
            "type": "contact",
            "field": "company",
            "operator": "=",
            "value": "INFOTREE",
            "next_operator": "AND",
            "group_start": 2,
            "group_end": 0,
        },
        {
            "type": "contact",
            "field": "industry",
            "operator": "=",
            "value": "Software",
            "next_operator": "AND",
            "group_start": 0,
            "group_end": 1,
        },
        {
            "type": "contact",
            "field": "language",
            "operator": "=",
            "value": "English",
            "next_operator": "END",
            "group_start": 0,
            "group_end": 1,
        },
    ]
    assert validate_rules(rules) == []


def test_validate_unbalanced_groups():
    rules = [
        {
            "type": "contact",
            "field": "company",
            "operator": "=",
            "value": "INFOTREE",
            "next_operator": "END",
            "group_start": 1,
            "group_end": 0,
        }
    ]
    errors = validate_rules(rules)
    assert "Unbalanced grouping brackets" in errors


def test_build_query_text():
    rules = [
        {
            "type": "contact",
            "field": "company",
            "operator": "=",
            "value": "INFOTREE",
            "next_operator": "AND",
            "group_start": 1,
            "group_end": 0,
        },
        {
            "type": "contact",
            "field": "industry",
            "operator": "=",
            "value": "Software",
            "next_operator": "END",
            "group_start": 0,
            "group_end": 1,
        },
    ]
    text = build_query_text(rules)
    assert 'company = "INFOTREE"' in text
    assert "AND" in text
    assert text.startswith("{")
    assert text.endswith("}")
