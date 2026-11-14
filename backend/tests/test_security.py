"""认证与工具函数单测。"""
from __future__ import annotations

from src.utils.csv_export import to_csv
from src.utils.pagination import page_params
from src.utils.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_roundtrip():
    hashed = hash_password("Demo@2026")
    assert hashed != "Demo@2026"
    assert verify_password("Demo@2026", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip_and_tamper():
    token, expires = create_access_token("analyst@pricelift.io", "analyst")
    assert expires > 0
    payload = decode_access_token(token)
    assert payload["sub"] == "analyst@pricelift.io"
    assert payload["role"] == "analyst"
    assert decode_access_token(token + "x") is None


def test_csv_has_bom_and_crlf():
    content = to_csv(["编号", "名称"], [[1, "酸奶 950ml"]])
    assert content.startswith("\ufeff".encode("utf-8"))
    assert b"\r\n" in content


def test_page_params_clamped():
    page = page_params(1000, -5)
    assert page.limit == 200
    assert page.offset == 0
