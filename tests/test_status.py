from nagare.tmux.status import detect_status, parse_details
from nagare.models import SessionStatus


def test_detect_waiting_choice_prompt():
    content = """\
 Do you want to proceed?
 ❯ 1. Yes
   2. No

 Esc to cancel · Tab to amend"""
    assert detect_status(content) == SessionStatus.WAITING_INPUT


def test_detect_waiting_file_create():
    content = """\
 Do you want to create RESOURCES_REPORT.md?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend"""
    assert detect_status(content) == SessionStatus.WAITING_INPUT


def test_detect_running():
    content = """\
  nemke@Cosmo:/home/nemke/Projects/mugen (git:main) | Opus 4.6 | ctx:50%
  ⏵⏵ accept edits on · curl -s -X DELETE -H "Authorization: Be… (running)"""
    assert detect_status(content) == SessionStatus.RUNNING


def test_detect_running_status_bar():
    content = """\
some output here
more output
  doing something (running)"""
    assert detect_status(content) == SessionStatus.RUNNING


def test_detect_idle():
    content = """\
     ◻ Task 8: End-to-end verification

❯

  nemke@Cosmo:/home/nemke/Projects/mugen (git:main) | Opus 4.6 | ctx:50%"""
    assert detect_status(content) == SessionStatus.IDLE


def test_detect_dead_empty():
    assert detect_status("") == SessionStatus.DEAD


def test_parse_details_full_status_bar():
    content = """\
some output
  nemke@Cosmo:/home/nemke/Projects/cosmo-ai (git:chat_history) | Opus 4.6 | ctx:51%
  ⏵⏵ accept edits on (shift+tab to cycle)"""
    details = parse_details(content)
    assert details.git_branch == "chat_history"
    assert details.model == "Opus 4.6"
    assert details.context_usage == "51%"


def test_parse_details_empty():
    details = parse_details("")
    assert details.git_branch == ""
    assert details.model == ""
    assert details.context_usage == ""


def test_parse_details_no_status_bar():
    details = parse_details("just some random output\nnothing to see here")
    assert details.git_branch == ""
