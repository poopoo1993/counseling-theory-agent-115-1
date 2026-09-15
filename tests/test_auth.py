from src.auth import create_otp, is_email_allowed, is_teacher, verify_otp
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
