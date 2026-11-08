"""SCRUM-73: password hashing and the proposed password rules."""

from app.security import hash_password, password_rule_failures, verify_password


def test_passwords_are_hashed_not_stored_plain():
    hashed = hash_password("Password123")
    assert "Password123" not in hashed
    assert hashed.startswith("$argon2")


def test_verify_accepts_right_password_and_rejects_wrong_one():
    hashed = hash_password("Password123")
    assert verify_password("Password123", hashed)
    assert not verify_password("password123", hashed)


def test_verify_with_no_hash_is_always_false():
    assert not verify_password("anything", None)


def test_good_password_passes_all_rules():
    assert password_rule_failures("Password123") == []


def test_each_broken_rule_is_reported():
    assert password_rule_failures("abc1") == ["Use at least 8 characters."]
    assert password_rule_failures("12345678") == ["Include at least one letter."]
    assert password_rule_failures("abcdefgh") == ["Include at least one number."]
    assert len(password_rule_failures("")) == 3
