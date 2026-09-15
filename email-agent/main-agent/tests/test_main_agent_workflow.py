from src.workflows.main_agent_workflow import _split_subject_body


def test_splits_subject_and_body_when_present():
    draft = "Subject: Q3 Budget Review\n\nHi team,\n\nSee attached.\n"
    subject, body = _split_subject_body(draft)
    assert subject == "Q3 Budget Review"
    assert body == "Hi team,\n\nSee attached."


def test_falls_back_to_generic_subject_when_missing():
    draft = "Hi team, see attached.\n"
    subject, body = _split_subject_body(draft)
    assert subject == "Demo Email"
    assert body == draft.strip()


def test_subject_line_is_case_insensitive():
    subject, _ = _split_subject_body("SUBJECT: Reminder\n\nDon't forget.")
    assert subject == "Reminder"
