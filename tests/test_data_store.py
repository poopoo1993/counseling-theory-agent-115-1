from src.data_store import MemoryStore, SqliteStore, parse_json_cell
from src.prompts import case_data_from_plan


def test_memory_store_preserves_identity_thread_and_raw_turn():
    store = MemoryStore("Asia/Taipei")
    participant_id = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    assert participant_id.startswith("P-")
    store.append_turn({"session_id": "S1", "turn_index": 1, "content_raw": "（停頓）原始內容"})
    assert store.session_turns("S1")[0]["content_raw"] == "（停頓）原始內容"
    store.save_thread({
        "conversation_thread_id": "T1", "participant_id": participant_id,
        "mode": "practice", "status": "active", "updated_at": store.now(),
    })
    assert store.list_threads(participant_id)[0]["conversation_thread_id"] == "T1"


def test_sqlite_store_preserves_identity_thread_plan_and_raw_turn(tmp_path):
    store = SqliteStore(str(tmp_path / "app.sqlite"), "Asia/Taipei")
    store.seed_whitelist(("student@hcu.edu.tw",), ("teacher@hcu.edu.tw",))
    assert store.is_whitelisted("student@hcu.edu.tw")
    assert store.get_whitelist_role("teacher@hcu.edu.tw") == "teacher"
    participant_id = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    assert participant_id.startswith("P-")
    store.append_turn({"session_id": "S1", "turn_index": 1, "content_raw": "（停頓）原始內容"})
    assert store.session_turns("S1")[0]["content_raw"] == "（停頓）原始內容"
    store.save_thread({
        "conversation_thread_id": "T1",
        "participant_id": participant_id,
        "mode": "practice",
        "status": "active",
        "updated_at": store.now(),
        "counseling_plan": {"phase_goals": ["建立安全關係"], "info_targets": [{"id": "t1"}]},
        "chat_analysis": {"next_focus": "了解自動化思考"},
    })
    thread = store.list_threads(participant_id)[0]
    assert thread["conversation_thread_id"] == "T1"
    assert parse_json_cell(thread["counseling_plan"], {})["phase_goals"] == ["建立安全關係"]
    assert parse_json_cell(thread["chat_analysis"], {})["next_focus"] == "了解自動化思考"


def test_case_data_from_plan_keeps_opening_fields():
    case = case_data_from_plan({
        "case_id": "demo",
        "public_opening": "我最近很累。",
        "phase_goals": ["ignored"],
    })
    assert case["case_id"] == "demo"
    assert case["public_opening"] == "我最近很累。"
    assert "phase_goals" not in case


def test_login_session_roundtrip_and_expiry(tmp_path):
    from src.auth import hash_browser_session_token, new_browser_session_token

    store = SqliteStore(str(tmp_path / "app.sqlite"), "Asia/Taipei")
    token = new_browser_session_token()
    digest = hash_browser_session_token(token)
    store.create_login_session(digest, "student@hcu.edu.tw", "P-demo", "student", ttl_seconds=60)
    row = store.get_login_session(digest)
    assert row is not None
    assert row["email"] == "student@hcu.edu.tw"
    assert row["token_hash"] == digest
    assert "api_key" not in row
    store.delete_login_session(digest)
    assert store.get_login_session(digest) is None

    expired = hash_browser_session_token("expired-token")
    store.create_login_session(expired, "student@hcu.edu.tw", "P-demo", "student", ttl_seconds=-1)
    assert store.get_login_session(expired) is None


def test_memory_store_preserves_identity_thread_and_raw_turn():
    store = MemoryStore("Asia/Taipei")
    participant_id = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    assert participant_id.startswith("P-")
    store.append_turn({"session_id": "S1", "turn_index": 1, "content_raw": "（停頓）原始內容"})
    assert store.session_turns("S1")[0]["content_raw"] == "（停頓）原始內容"
    store.save_thread({
        "conversation_thread_id": "T1", "participant_id": participant_id,
        "mode": "practice", "status": "active", "updated_at": store.now(),
    })
    assert store.list_threads(participant_id)[0]["conversation_thread_id"] == "T1"
