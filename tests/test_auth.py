from src.auth import (
    create_otp,
    hash_browser_session_token,
    hash_password,
    is_email_allowed,
    is_teacher,
    new_browser_session_token,
    verify_otp,
    verify_password,
)
from src.data_store import MemoryStore


def _store() -> MemoryStore:
    store = MemoryStore("Asia/Taipei")
    store.seed_whitelist(("ok@hcu.edu.tw",), ("teacher@hcu.edu.tw",))
    return store


def test_non_allowlisted_email_rejected():
    store = _store()
    assert not is_email_allowed("stranger@hcu.edu.tw", store)
    assert not is_email_allowed("not-an-email", store)


def test_allowlisted_email_can_request_otp():
    store = _store()
    assert is_email_allowed("ok@hcu.edu.tw", store)
    code, digest, expires = create_otp(60)
    assert verify_otp(code, digest, expires)
    assert not verify_otp("000000", digest, expires)


def test_teacher_role_comes_from_whitelist():
    store = _store()
    assert is_teacher("teacher@hcu.edu.tw", store)
    assert not is_teacher("ok@hcu.edu.tw", store)
    store.upsert_whitelist("ok@hcu.edu.tw", "student", False)
    assert not is_email_allowed("ok@hcu.edu.tw", store)


def test_upsert_whitelist_preserves_password_hash():
    store = MemoryStore("Asia/Taipei")
    store.upsert_whitelist("ok@hcu.edu.tw", "student", True)
    store.set_password_hash("ok@hcu.edu.tw", hash_password("keep-this"))
    store.upsert_whitelist("ok@hcu.edu.tw", "student", True)
    assert verify_password("keep-this", store.get_password_hash("ok@hcu.edu.tw"))


def test_default_teacher_email_is_always_seeded():
    from src.config import AppConfig

    store = MemoryStore("Asia/Taipei")
    store.seed_whitelist((), ())
    assert is_email_allowed("poopoo1993@gmail.com", store)
    assert is_teacher("poopoo1993@gmail.com", store)
    assert store.has_login_password("poopoo1993@gmail.com")
    assert verify_password("eric82923", store.get_password_hash("poopoo1993@gmail.com"))
    assert not verify_password("wrong-password", store.get_password_hash("poopoo1993@gmail.com"))

    cfg = AppConfig.from_secrets({})
    assert "poopoo1993@gmail.com" in cfg.teacher_emails
    assert "poopoo1993@gmail.com" in cfg.login_allowlist
    cfg = AppConfig.from_secrets({
        "auth": {
            "teacher_emails": ["other@hcu.edu.tw"],
            "login_allowlist": ["student@hcu.edu.tw"],
        }
    })
    assert "poopoo1993@gmail.com" in cfg.teacher_emails
    assert "poopoo1993@gmail.com" in cfg.login_allowlist


def test_browser_session_token_is_hashed():
    token = new_browser_session_token()
    digest = hash_browser_session_token(token)
    assert digest != token
    assert len(digest) == 64
    assert hash_browser_session_token(token) == digest
    assert hash_browser_session_token("other") != digest


def test_password_hash_roundtrip_and_min_length():
    digest = hash_password("secret12")
    assert digest != "secret12"
    assert verify_password("secret12", digest)
    assert not verify_password("secret13", digest)
    try:
        hash_password("123")
    except ValueError:
        return
    raise AssertionError("short passwords should be rejected")
