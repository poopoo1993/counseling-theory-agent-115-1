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


def test_online_users_use_recent_last_seen(tmp_path):
    from src.auth import hash_browser_session_token, new_browser_session_token

    store = SqliteStore(str(tmp_path / "presence.sqlite"), "Asia/Taipei")
    live = hash_browser_session_token(new_browser_session_token())
    stale = hash_browser_session_token(new_browser_session_token())
    store.create_login_session(live, "live@hcu.edu.tw", "P-LIVE", "teacher", ttl_seconds=60)
    store.create_login_session(stale, "stale@hcu.edu.tw", "P-STALE", "student", ttl_seconds=60)
    store._upsert_by_key("AuthSessions", "token_hash", stale, {
        **store.get_login_session(stale),
        "last_seen_at": "2000-01-01T00:00:00+08:00",
    })
    store.touch_login_session(live)
    people = store.list_online_users(within_seconds=180)
    emails = [item["email"] for item in people]
    assert emails == ["live@hcu.edu.tw"]
    assert people[0]["role"] == "teacher"


def test_purge_session_transcript_removes_only_that_session(tmp_path):
    store = SqliteStore(str(tmp_path / "consent.sqlite"), "Asia/Taipei")
    store.append_turn({"session_id": "keep", "turn_index": 1, "content_raw": "留下"})
    store.append_turn({"session_id": "drop", "turn_index": 1, "content_raw": "刪除"})
    store.save_assessment({
        "assessment_id": "A1",
        "session_id": "drop",
        "skill_events": [{"technique_id": "automatic_thoughts", "evidence_quote": "刪除"}],
    })
    store.purge_session_transcript("drop")
    assert store.session_turns("drop") == []
    assert store.session_turns("keep")[0]["content_raw"] == "留下"
    assert store.get_assessment("drop") is None
    assert store.all_records("SkillEvents") == []


def test_sessions_schema_includes_research_consent():
    from src.data_store import SCHEMAS

    assert "research_consent" in SCHEMAS["Sessions"]


def test_anonymous_participant_id_is_random_and_prefixed():
    from src.session_service import new_anonymous_participant_id

    first = new_anonymous_participant_id()
    second = new_anonymous_participant_id()
    assert first.startswith("P-ANON-")
    assert second.startswith("P-ANON-")
    assert first != second
    assert len(first) == len("P-ANON-") + 12
    assert all(ch in "0123456789ABCDEF" for ch in first.removeprefix("P-ANON-"))


def test_reassign_session_participant_unlinks_identity_and_keeps_process(tmp_path):
    from src.session_service import new_anonymous_participant_id

    store = SqliteStore(str(tmp_path / "anon.sqlite"), "Asia/Taipei")
    student = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    store.start_session({
        "session_id": "S-anon",
        "conversation_thread_id": "T-keep",
        "participant_id": student,
        "case_id": "case-1",
        "research_consent": "anonymous",
        "completion_status": "completed",
        "started_at": "2026-09-15T21:00:00+08:00",
        "ended_at": "2026-09-15T21:08:00+08:00",
        "duration_seconds": "480",
    })
    store.append_turn({
        "turn_id": "t1",
        "session_id": "S-anon",
        "conversation_thread_id": "T-keep",
        "participant_id": student,
        "turn_index": 1,
        "content_raw": "晤談內容",
        "timestamp": "2026-09-15T21:01:00+08:00",
    })
    store.save_thread({
        "conversation_thread_id": "T-keep",
        "participant_id": student,
        "status": "active",
        "updated_at": store.now(),
        "last_session_id": "previous",
        "recent_turns": [{"content_raw": "不應被此次改掛"}],
    })
    anon = new_anonymous_participant_id()
    store.reassign_session_participant("S-anon", anon)
    session = next(row for row in store.all_records("Sessions") if row["session_id"] == "S-anon")
    turn = store.session_turns("S-anon")[0]
    assert session["participant_id"] == anon
    assert session["conversation_thread_id"] == ""
    assert session["case_id"] == ""
    assert turn["participant_id"] == anon
    assert turn["conversation_thread_id"] == ""
    assert turn["content_raw"] == "晤談內容"
    assert turn["timestamp"] == "2026-09-15T21:01:00+08:00"
    assert store.count_sessions(student) == 0
    assert all(row["participant_id"] != anon for row in store.all_records("IdentityMap"))
    thread = store.list_threads(student)[0]
    assert thread["conversation_thread_id"] == "T-keep"
    assert thread["participant_id"] == student


def test_memory_store_reassign_session_participant_unlinks_thread():
    from src.session_service import new_anonymous_participant_id

    store = MemoryStore("Asia/Taipei")
    student = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    store.start_session({
        "session_id": "S-mem",
        "conversation_thread_id": "T-mem",
        "participant_id": student,
        "case_id": "case-mem",
        "research_consent": "anonymous",
    })
    store.append_turn({
        "turn_id": "tm1",
        "session_id": "S-mem",
        "conversation_thread_id": "T-mem",
        "participant_id": student,
        "turn_index": 1,
        "content_raw": "匿名應保留",
        "timestamp": "2026-09-15T21:02:00+08:00",
    })
    anon = new_anonymous_participant_id()
    store.reassign_session_participant("S-mem", anon)
    session = store.all_records("Sessions")[0]
    turn = store.session_turns("S-mem")[0]
    assert session["participant_id"] == anon
    assert session["conversation_thread_id"] == ""
    assert turn["participant_id"] == anon
    assert turn["content_raw"] == "匿名應保留"


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
