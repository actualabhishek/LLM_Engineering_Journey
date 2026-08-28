#!/bin/bash
# SessionStart hook: arm the postflow listener automatically for every
# session opened in this project. See postflow-plugin/README.md.
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"This is the postflow project (Telegram-driven LinkedIn content pipeline). At the start of this session, run /postflow start now, without waiting to be asked, so the listener is armed for the rest of the session. If this session was NOT launched with the flag --channels plugin:telegram@claude-plugins-official, tell the user plainly that inbound Telegram \"Topic: ...\" messages will not reach this session, and that they need to restart claude with that flag for the listener to actually receive them."}}
JSON
