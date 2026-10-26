from datetime import date

from jobgent.assistant import AssistantReply, ProfileEdit, chat
from jobgent.llm import FakeLLM
from jobgent.profile.models import Personal, Profile, SearchProfile
from jobgent.profile.store import ProfileStore


def store(tmp_path) -> ProfileStore:
    st = ProfileStore(tmp_path)
    st.save(Profile(personal=Personal(name="T"), search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))))
    return st


def test_chat_applies_edits_and_reports_them(tmp_path):
    st = store(tmp_path)
    llm = FakeLLM([AssistantReply(reply="Done, goal set to 12.", edits=[ProfileEdit(path="preferences.weekly_goal", value="12")])])
    result = chat(llm, "m", st, history=[], message="set my weekly goal to 12")
    assert result.reply.startswith("Done") and result.applied == ["preferences.weekly_goal"] and result.failed == []
    assert st.load().preferences.weekly_goal == 12
    system, user = llm.prompts[0]
    assert "weekly_goal" in user and "set my weekly goal" in user


def test_chat_reports_bad_paths_without_crashing(tmp_path):
    st = store(tmp_path)
    llm = FakeLLM([AssistantReply(reply="ok", edits=[ProfileEdit(path="nope.x", value="1")])])
    result = chat(llm, "m", st, history=[("user", "hi"), ("assistant", "hello")], message="x")
    assert result.applied == [] and len(result.failed) == 1 and "nope.x" in result.failed[0]
    assert "hello" in llm.prompts[0][1]


def test_chat_appends_free_text_notes(tmp_path):
    st = store(tmp_path)
    llm = FakeLLM([AssistantReply(reply="Noted.", edits=[], notes="Likes robotics; did a hackathon in 2025")])
    chat(llm, "m", st, history=[], message="I did a hackathon in 2025")
    assert "hackathon" in (tmp_path / "notes.md").read_text()
