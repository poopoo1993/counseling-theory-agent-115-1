from src.data_store import MemoryStore


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
