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


def test_thread_turns_return_full_prior_transcript():
    store = MemoryStore("Asia/Taipei")
    store.append_turn({
        "session_id": "S1", "conversation_thread_id": "T-full",
        "turn_index": 1, "timestamp": "2026-01-01T10:00:00+08:00",
        "speaker_role": "ai_client", "content_raw": "第一句",
    })
    store.append_turn({
        "session_id": "S1", "conversation_thread_id": "T-full",
        "turn_index": 2, "timestamp": "2026-01-01T10:00:10+08:00",
        "speaker_role": "student_counselor", "content_raw": "你聽起來很累。",
    })
    store.append_turn({
        "session_id": "S2", "conversation_thread_id": "T-full",
        "turn_index": 1, "timestamp": "2026-01-08T10:00:00+08:00",
        "speaker_role": "ai_client", "content_raw": "後來還是睡不好。",
    })
    store.append_turn({
        "session_id": "S-other", "conversation_thread_id": "T-other",
        "turn_index": 1, "timestamp": "2026-01-01T09:00:00+08:00",
        "speaker_role": "ai_client", "content_raw": "別的歷程",
    })
    texts = [row["content_raw"] for row in store.thread_turns("T-full")]
    assert texts == ["第一句", "你聽起來很累。", "後來還是睡不好。"]


def test_list_threads_only_returns_active_rows():
    store = MemoryStore("Asia/Taipei")
    participant_id = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    store.save_thread({
        "conversation_thread_id": "T-progress", "participant_id": participant_id,
        "mode": "practice", "status": "in_progress", "updated_at": "2026-01-01T00:00:00+08:00",
    })
    store.save_thread({
        "conversation_thread_id": "T-closed", "participant_id": participant_id,
        "mode": "practice", "status": "closed", "updated_at": "2026-01-02T00:00:00+08:00",
    })
    store.save_thread({
        "conversation_thread_id": "T-active", "participant_id": participant_id,
        "mode": "practice", "status": "active", "updated_at": "2026-01-03T00:00:00+08:00",
    })
    listed = store.list_threads(participant_id)
    assert [row["conversation_thread_id"] for row in listed] == ["T-active"]


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
    assert "AnonymousSessions" in SCHEMAS
    assert "AnonymousChatLogs" in SCHEMAS
    assert "participant_id" not in SCHEMAS["AnonymousSessions"]
    assert "participant_id" not in SCHEMAS["AnonymousChatLogs"]


def test_save_anonymous_transcript_keeps_process_off_identity(tmp_path):
    store = SqliteStore(str(tmp_path / "anon.sqlite"), "Asia/Taipei")
    student = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    store.start_session({
        "session_id": "S-anon",
        "conversation_thread_id": "T-keep",
        "participant_id": student,
        "research_consent": "anonymous",
        "completion_status": "completed",
        "started_at": "2026-09-16T11:00:00+08:00",
        "ended_at": "2026-09-16T11:08:00+08:00",
        "duration_seconds": "480",
        "mode": "experience",
        "school_id": "cbt",
        "selected_techniques": ["automatic_thoughts"],
        "selected_technique_names": ["辨識自動化思考"],
    })
    store.append_turn({
        "turn_id": "t1",
        "session_id": "S-anon",
        "conversation_thread_id": "T-keep",
        "participant_id": student,
        "turn_index": 1,
        "speaker_role": "student_client",
        "content_raw": "晤談內容",
        "timestamp": "2026-09-16T11:01:00+08:00",
    })
    anon_id = store.save_anonymous_transcript(
        store.all_records("Sessions")[0],
        store.session_turns("S-anon"),
    )
    store.purge_session_transcript("S-anon")
    identified = store.all_records("Sessions")[0]
    assert identified["participant_id"] == student
    assert identified["research_consent"] == "anonymous"
    assert store.session_turns("S-anon") == []
    anon_session = store.all_records("AnonymousSessions")[0]
    assert anon_session["anonymous_session_id"] == anon_id
    assert "participant_id" not in anon_session
    turns = store.anonymous_session_turns(anon_id)
    assert turns[0]["content_raw"] == "晤談內容"
    assert turns[0]["timestamp"] == "2026-09-16T11:01:00+08:00"
    assert "participant_id" not in turns[0]


def test_memory_store_saves_anonymous_transcript_apart_from_chatlogs():
    store = MemoryStore("Asia/Taipei")
    student = store.get_or_create_participant("student@hcu.edu.tw", "student", "test-salt")
    store.append_turn({
        "session_id": "S-mem",
        "participant_id": student,
        "turn_index": 1,
        "speaker_role": "ai_counselor",
        "content_raw": "匿名應另表保留",
        "timestamp": "2026-09-16T11:02:00+08:00",
    })
    anon_id = store.save_anonymous_transcript(
        {
            "started_at": "2026-09-16T11:00:00+08:00",
            "ended_at": "2026-09-16T11:08:00+08:00",
            "duration_seconds": "480",
            "mode": "experience",
            "school_id": "cbt",
        },
        store.session_turns("S-mem"),
    )
    store.purge_session_transcript("S-mem")
    assert store.session_turns("S-mem") == []
    turns = store.anonymous_session_turns(anon_id)
    assert turns[0]["content_raw"] == "匿名應另表保留"
    assert store.all_records("AnonymousSessions")[0]["anonymous_session_id"] == anon_id


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


def test_google_sheets_store_includes_login_session_mixin():
    from src.data_store import GoogleSheetsStore, LoginSessionMixin

    assert issubclass(GoogleSheetsStore, LoginSessionMixin)
    assert hasattr(GoogleSheetsStore, "create_login_session")
    assert hasattr(GoogleSheetsStore, "touch_login_session")
    assert hasattr(GoogleSheetsStore, "list_online_users")
    assert hasattr(GoogleSheetsStore, "thread_turns")


def test_choose_store_backend_uses_sheets_when_secrets_present():
    from src.data_store import choose_store_backend, require_sheets_enabled, sheets_secrets_present

    empty = {}
    assert choose_store_backend(empty) == "sqlite"
    assert not sheets_secrets_present(empty)
    assert not require_sheets_enabled(empty)

    configured = {
        "SPREADSHEET_ID": "sheet-id-demo",
        "GOOGLE_SERVICE_ACCOUNT_JSON": {
            "client_email": "bot@example.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
            "private_key": "not-used-in-this-test",
        },
    }
    assert sheets_secrets_present(configured)
    assert choose_store_backend(configured) == "sheets"

    required_only = {"REQUIRE_SHEETS": "true"}
    assert require_sheets_enabled(required_only)
    assert choose_store_backend(required_only) == "sheets"
    assert not sheets_secrets_present(required_only)


class _FakeAPIError(Exception):
    def __init__(self, status_code=429, retry_after=None):
        self.response = type("Response", (), {
            "status_code": status_code,
            "headers": {"Retry-After": retry_after} if retry_after else {},
        })()
        super().__init__(f"{status_code} quota")


class _FakeWorksheet:
    def __init__(self, title, headers):
        self.title = title
        self.headers = list(headers)
        self.rows = []
        self.row_values_calls = 0
        self.update_calls = 0
        self.append_row_calls = 0
        self.append_rows_calls = 0
        self.batch_update_calls = 0
        self.get_all_records_calls = 0

    def row_values(self, row):
        self.row_values_calls += 1
        return list(self.headers) if row == 1 else []

    def append_row(self, values, value_input_option="RAW"):
        self.append_row_calls += 1
        if not self.headers:
            self.headers = [str(item) for item in values]
            return
        self.rows.append([str(item) for item in values])

    def append_rows(self, values, value_input_option="RAW"):
        self.append_rows_calls += 1
        for row in values:
            if not self.headers:
                self.headers = [str(item) for item in row]
                continue
            self.rows.append([str(item) for item in row])

    def freeze(self, rows=None, cols=None):
        return None

    def update(self, values=None, range_name=None):
        self.update_calls += 1
        if values:
            self.headers = [str(item) for item in values[0]]

    def batch_update(self, data, value_input_option="RAW"):
        self.batch_update_calls += 1
        for item in data:
            range_name = str(item.get("range") or "")
            values = item.get("values") or []
            if not range_name.startswith("A") or not values:
                continue
            try:
                row_index = int(range_name[1:]) - 2
            except ValueError:
                continue
            if 0 <= row_index < len(self.rows):
                self.rows[row_index] = [str(cell) for cell in values[0]]

    def get_all_records(self, default_blank=""):
        self.get_all_records_calls += 1
        records = []
        for row in self.rows:
            item = {}
            for index, header in enumerate(self.headers):
                item[header] = row[index] if index < len(row) else default_blank
            records.append(item)
        return records

    def delete_rows(self, index: int):
        del self.rows[index - 2]


class _FakeBook:
    def __init__(self, sheets):
        self._sheets = list(sheets)
        self.worksheets_calls = 0
        self.batch_gets = 0

    def worksheets(self):
        self.worksheets_calls += 1
        return list(self._sheets)

    def add_worksheet(self, title, rows, cols):
        ws = _FakeWorksheet(title, [])
        self._sheets.append(ws)
        return ws

    def values_batch_get(self, ranges, params=None):
        self.batch_gets += 1
        blocks = []
        for rng in ranges:
            name = rng.split("!")[0].strip("'")
            ws = next(item for item in self._sheets if item.title == name)
            blocks.append({"range": rng, "values": [ws.headers] if ws.headers else []})
        return {"valueRanges": blocks}


def _fake_sheets_store(headers_ok: bool = True):
    from src.data_store import SCHEMAS, GoogleSheetsStore

    sheets = [
        _FakeWorksheet(name, list(headers) if headers_ok else [])
        for name, headers in SCHEMAS.items()
    ]
    book = _FakeBook(sheets)
    store = GoogleSheetsStore.__new__(GoogleSheetsStore)
    store.book = book
    store.timezone = "Asia/Taipei"
    store.worksheets = {}
    store._init_write_buffer()
    store.ensure_schema()
    with store._buffer_lock:
        store._cancel_flush_timer_locked()
    return store, book


def test_retry_sheets_call_retries_quota_then_succeeds(monkeypatch):
    from src.data_store import is_transient_sheets_error, retry_sheets_call

    sleeps = []
    monkeypatch.setattr("src.data_store.time.sleep", sleeps.append)
    assert is_transient_sheets_error(_FakeAPIError(429))
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise _FakeAPIError(429)
        return "ok"

    assert retry_sheets_call(flaky) == "ok"
    assert state["n"] == 3
    assert sleeps


def test_public_store_error_message_hides_api_details():
    from src.data_store import SHEETS_USER_ERROR, public_store_error_message

    message = public_store_error_message(_FakeAPIError(429))
    assert message == SHEETS_USER_ERROR
    assert "quota" not in message.lower()


def test_google_sheets_ensure_schema_batches_and_skips_second_pass():
    store, book = _fake_sheets_store()
    assert book.batch_gets == 1
    assert book.worksheets_calls == 1
    assert all(ws.row_values_calls == 0 for ws in book._sheets)
    store.ensure_schema()
    store.ensure_schema()
    assert book.worksheets_calls == 1
    assert book.batch_gets == 1


def test_google_sheets_ensure_schema_adds_missing_column():
    from src.data_store import SCHEMAS

    store, book = _fake_sheets_store()
    sessions = store.worksheets["Sessions"]
    sessions.headers = [item for item in SCHEMAS["Sessions"] if item != "research_consent"]
    store._schema_ready = False
    store.worksheets = {}
    store.ensure_schema()
    assert "research_consent" in sessions.headers
    assert sessions.update_calls == 1


def test_seed_whitelist_does_not_rewrite_existing_teacher():
    from src.data_store import MemoryStore

    store = MemoryStore("Asia/Taipei")
    store.seed_whitelist(("student@hcu.edu.tw",), ("teacher@hcu.edu.tw",))
    calls = {"n": 0}
    original = store._upsert_by_key

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    store._upsert_by_key = wrapped
    store._whitelist_seed_key = None
    store.seed_whitelist(("student@hcu.edu.tw",), ("teacher@hcu.edu.tw",))
    assert calls["n"] == 0
    assert store.is_whitelisted("student@hcu.edu.tw")
    assert store.get_whitelist_role("teacher@hcu.edu.tw") == "teacher"


def test_sheets_buffer_holds_below_threshold_then_flush_batches(monkeypatch):
    monkeypatch.setattr("src.data_store.SHEETS_FLUSH_INTERVAL_SECONDS", 3600)
    store, _ = _fake_sheets_store()
    chat = store.worksheets["ChatLogs"]
    before_rows = chat.append_rows_calls
    before_row = chat.append_row_calls
    for index in range(79):
        store.append_turn({"session_id": "S1", "turn_index": index, "content_raw": f"t{index}"})
    assert chat.append_rows_calls == before_rows
    assert chat.append_row_calls == before_row
    assert len(store.session_turns("S1")) == 79
    store.flush()
    assert chat.append_rows_calls == before_rows + 1
    assert len(store.session_turns("S1")) == 79


def test_sheets_buffer_flushes_once_at_row_threshold(monkeypatch):
    monkeypatch.setattr("src.data_store.SHEETS_FLUSH_INTERVAL_SECONDS", 3600)
    store, _ = _fake_sheets_store()
    chat = store.worksheets["ChatLogs"]
    before_rows = chat.append_rows_calls
    for index in range(80):
        store.append_turn({"session_id": "S1", "turn_index": index, "content_raw": f"t{index}"})
    assert chat.append_rows_calls == before_rows + 1
    assert len(store.session_turns("S1")) == 80


def test_sheets_buffer_coalesces_thread_upserts(monkeypatch):
    monkeypatch.setattr("src.data_store.SHEETS_FLUSH_INTERVAL_SECONDS", 3600)
    store, _ = _fake_sheets_store()
    threads = store.worksheets["Threads"]
    store.save_thread({
        "conversation_thread_id": "T1",
        "participant_id": "P1",
        "status": "active",
        "updated_at": "1",
        "latest_snapshot": "first",
    })
    store.save_thread({
        "conversation_thread_id": "T1",
        "participant_id": "P1",
        "status": "active",
        "updated_at": "2",
        "latest_snapshot": "second",
    })
    assert threads.append_rows_calls == 0
    assert threads.batch_update_calls == 0
    store.flush()
    assert threads.append_rows_calls == 1
    assert threads.batch_update_calls == 0
    assert threads.get_all_records()[-1]["latest_snapshot"] == "second"
    store.save_thread({
        "conversation_thread_id": "T1",
        "participant_id": "P1",
        "status": "active",
        "updated_at": "3",
        "latest_snapshot": "third",
    })
    store.flush()
    assert threads.batch_update_calls == 1
    assert threads.get_all_records()[-1]["latest_snapshot"] == "third"


def test_immediate_sheets_write_without_buffer(monkeypatch):
    monkeypatch.setattr("src.data_store.SHEETS_FLUSH_INTERVAL_SECONDS", 3600)
    store, _ = _fake_sheets_store()
    risk = store.worksheets["RiskEvents"]
    auth = store.worksheets["AuthSessions"]
    before_risk = risk.append_rows_calls
    before_auth = auth.append_rows_calls
    store.append("RiskEvents", {"risk_event_id": "r1", "event_type": "keyword"})
    store.append("AuthSessions", {
        "token_hash": "abc",
        "email": "student@hcu.edu.tw",
        "participant_id": "P1",
        "role": "student",
        "created_at": store.now(),
        "expires_at": store.now(),
        "last_seen_at": store.now(),
    })
    assert risk.append_rows_calls == before_risk + 1
    assert auth.append_rows_calls == before_auth + 1


def test_finish_session_flushes_buffered_chat_and_session(monkeypatch):
    monkeypatch.setattr("src.data_store.SHEETS_FLUSH_INTERVAL_SECONDS", 3600)
    store, _ = _fake_sheets_store()
    sessions = store.worksheets["Sessions"]
    chat = store.worksheets["ChatLogs"]
    store.start_session({"session_id": "S1", "participant_id": "P1", "completion_status": "in_progress"})
    store.append_turn({"session_id": "S1", "turn_index": 1, "content_raw": "hello"})
    assert sessions.append_rows_calls == 0
    assert chat.append_rows_calls == 0
    store.finish_session({"session_id": "S1", "participant_id": "P1", "completion_status": "completed"})
    assert sessions.append_rows_calls == 1
    assert sessions.batch_update_calls == 1
    assert chat.append_rows_calls == 1
    assert store.session_turns("S1")[0]["content_raw"] == "hello"

