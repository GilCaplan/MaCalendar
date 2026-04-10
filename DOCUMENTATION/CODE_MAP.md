# MACalendar — Code Map

> **Purpose**: Precise file + line pointers for common bug-fixing and feature work.  
> Read this before searching the codebase. Updated as code evolves.

---

## Database — `assistant/db.py`

| What | Location |
|------|----------|
| `CalendarDB` class | L93 |
| `__init__` (table creation, migrations) | L96–107 |
| `_conn()` context manager | L131–139 |
| `_migrate_todos()` | L120–129 |
| `_TODO_MIGRATIONS` list (additive ALTER TABLE stmts) | L33–40 |
| `_CREATE_SUBTASKS_TABLE` | L42–52 |
| `get_db()` singleton | L789 |
| **Events CRUD** | L144–518 |
| `create_event` | L145 |
| `update_event` (allowed fields set) | L332 |
| `delete_event` (re-root logic for series) | L441 |
| `update_series` / `delete_series_from` | L373 / L484 |
| **Todos CRUD** | L520–706 |
| `create_todo` | L524 |
| `get_todos` | L565 |
| `update_todo` (allowed fields set — add new fields here) | L611 |
| `toggle_todo_complete` | L621 |
| `delete_completed_todos` | L645 |
| `reorder_todos` | L656 |
| `sync_calendar_to_todos` | L669 |
| **Subtasks CRUD** | L709–770 |
| `get_subtasks` / `create_subtask` | L710 / L721 |
| `update_subtask` / `delete_subtask` | L733 / L742 |
| `delete_subtasks_for_todo` (call before `delete_todo`) | L745 |
| `reorder_subtasks` | L751 |

**Schema — `todos` table columns:**
`id, title, list, completed, priority, due_date, notes, source, source_event_id, created_at, completed_at, position, attachments`

**Schema — `subtasks` table columns:**
`id, todo_id, title, completed, position, created_at`

---

## NLU Pipeline — `assistant/pipeline.py`

| What | Location |
|------|----------|
| `Pipeline` class | L56 |
| `__init__` (registry, config, status callback) | L65 |
| `trigger()` — mic button handler, session queuing | L90 |
| `_run_pipeline()` — full STT→parse→execute flow | L146 |
| Rule-parser fast path decision point | L259 |
| `parse_with_context()` call (partial handoff to LLM) | L275 |
| Full LLM parse call | L285 |
| `view_switch` extraction after execute | L375–381 |
| `_set_status()` → sends signal to `CalendarWindow` | L706 |
| `_background_verify()` — LLM judge thread | L421 |
| `_detect_user_change()` — guard before applying correction | L562 |
| `_parse_segment()` — per-segment parse helper | L625 |
| `_append_scenario_bug()` — writes to `DOCUMENTATION/SCENARIO_BUG.md` | L587 |
| `_append_nlu_log()` — writes to `DOCUMENTATION/NLU_TRACKING.md` | L650 |

**Status values** (defined in `window.py` L43–52):  
`STATUS_IDLE`, `STATUS_LISTENING`, `STATUS_PROCESSING`, `STATUS_ERROR`, `STATUS_REFRESH`, `STATUS_SWITCH_TODAY`, `STATUS_SWITCH_TODO`

---

## Rule-Based NLU — `assistant/intent/rule_parser.py`

| What | Location |
|------|----------|
| `RULE_THRESHOLD = 0.85` | L66 |
| `RuleParseResult` dataclass | L75 |
| `RuleParserSkip` exception (raised → LLM fallback) | L86 |
| Phase 0 — preprocess + complexity gate | L269 / L1013 |
| Phase 1 — multi-intent split | L332 / L1020 |
| Phase 2 — temporal extraction | L398 / L1031 |
| Phase 3 — intent/domain routing | L554 / L1034 |
| Phase 4 — slot filling | L715 / L1042 |
| Phase 5 — anaphora resolution | L899 / L1045 |
| Phase 6 — confidence scoring | L944 / L1050 |
| `RuleBasedParser.analyze()` — entry point | L1003 |
| `RuleBasedParser.parse()` — raises `RuleParserSkip` if low confidence | L1090 |

---

## LLM Intent Parser — `assistant/intent/parser.py`

| What | Location |
|------|----------|
| `IntentParser` class | L38 |
| `parse()` — full LLM parse from scratch | L67 |
| `parse_with_context()` — partial handoff (fills gaps only) | L104 |
| `verify_fast_path_async()` — background judge thread | L140 |

---

## Context Memory — `assistant/intent/context.py`

| What | Location |
|------|----------|
| `ContextMemory` Borg singleton | L14 |
| Module-level `context_memory` instance | L69 |

Used by rule parser (L899) and actions for anaphora ("delete it", "move that").

---

## Actions System

### Registry — `assistant/actions/__init__.py`
| What | Location |
|------|----------|
| `ActionRegistry` class | L12 |
| `register` decorator | L169 |
| `build_system_prompt()` — assembles LLM system prompt | L51 |

### Base class — `assistant/actions/base.py`
| What | Location |
|------|----------|
| `BaseAction` ABC | L14 |
| `view_switch: ClassVar[Optional[str]]` | L37 — set on subclass to auto-switch UI view |
| `execute()` abstract method | L40 |

### Calendar actions — `assistant/actions/calendar/action.py`
| Class | Location | view_switch |
|-------|----------|-------------|
| `CreateEventAction` | L28 | — |
| `UpdateEventAction` | L77 | — |
| `DeleteEventAction` | L159 | — |
| `QueryScheduleAction` | L204 | `"switch_today"` |
| `_find_event()` fuzzy matcher | L334 | |

### Todo actions — `assistant/actions/todo/action.py`
| Class | Location | view_switch |
|-------|----------|-------------|
| `CreateTodoAction` | L60 | `"switch_todo"` |
| `CompleteTodoAction` | L125 | — |
| `DeleteTodoAction` | L173 | — |
| `UpdateTodoAction` | L211 | — |
| `QueryTodoAction` | L277 | `"switch_todo"` |
| `_find_todo()` fuzzy matcher | L22 | |

### Intent models
| File | Contents |
|------|----------|
| `assistant/actions/calendar/intent.py` | `CalendarIntent`, `UpdateEventIntent`, `DeleteEventIntent`, `QueryScheduleIntent` |
| `assistant/actions/todo/intent.py` | `CreateTodoIntent` (supports `titles: List[str]`), `CompleteTodoIntent`, `DeleteTodoIntent`, `UpdateTodoIntent`, `QueryTodoIntent` |

---

## Mac UI — `assistant/calendar_ui/`

### Main Window — `window.py`
| What | Location |
|------|----------|
| `CalendarWindow` class | L117 |
| `_build_ui()` — view stack setup | L162 |
| `_build_toolbar()` — top toolbar | L214 |
| `_handle_status()` — receives pipeline status, triggers refresh/view-switch | L540 |
| `refresh_calendar()` / `refresh_todos()` | L561 / L567 |
| `_set_view()` — switches Month/Week/Day/Tasks stack | L377 |
| `_on_event_clicked()` — opens EventDetailView | L455 |
| `_apply_theme()` | L600 |
| `_apply_ui_config()` | L626 |
| `_on_settings_popup()` | L663 |

**How pipeline → UI refresh works:**  
`Pipeline._set_status()` → `CalendarWindow._poll_status()` (L524, 100ms timer) → `_handle_status()` (L540) → `refresh_calendar()` or `refresh_todos()` or `_set_view()`.

**Adding a new view:** Add a stack page in `_build_ui()`, handle a new `STATUS_SWITCH_XXX` value in `_handle_status()`, set `view_switch = "switch_xxx"` on the action class.

### Tasks (Todo) View — `todo_view.py`
| What | Location |
|------|----------|
| `InsertLinkDialog` | L58 — 2-field modal for embedded hyperlinks |
| `SubtaskRow` | L102 — compact checkbox row for subtasks |
| `TodoDetailPanel` | L160 — expandable inline panel |
| `TodoDetailPanel._build()` | L196 — layout: notes stack → subtasks → attachments → metadata |
| `TodoDetailPanel.load()` | L415 — reload all fields from todo dict |
| `TodoDetailPanel._switch_to_edit()` | L461 |
| `TodoDetailPanel._on_insert_link()` | L490 — InsertLinkDialog → inserts `<a href>` |
| `TodoDetailPanel._reload_subtasks()` | L506 |
| `TodoDetailPanel._on_add_attachment()` | L611 |
| `TodoItemWidget` | L700 — single task row |
| `TodoItemWidget._build()` | L744 — outer VBox + title HBox + hidden detail panel |
| `TodoItemWidget._toggle_expand()` | L813 — show/hide detail panel + update size hint |
| `TodoItemWidget._update_item_size()` | L829 — recalculate QListWidget height after expand |
| `TodoItemWidget.set_list_item()` | L797 — called by TodoListWidget post-insertion |
| `TodoListWidget` | L905 |
| `TodoListWidget.populate()` | L941 — clears + rebuilds QListWidget from DB |
| `TodoListWidget._on_deleted()` | L1096 — deletes subtasks first, then todo |
| `TodoListWidget._make_new_task_row()` | L1020 |
| `SectionHeader` | L1110 |
| `TodoView` | L1245 |
| `TodoView.refresh()` | L1320 |

**Crash prevention pattern (important):**  
All signals that trigger widget rebuild use `QTimer.singleShot(0, signal.emit)` to prevent re-entrant `deleteLater()` crashes. See `_on_toggled`, `_on_edited`, `_on_deleted` in `TodoListWidget`.

**QListWidget expand pattern:**  
`_toggle_expand()` → `_detail_panel.show()/hide()` → `_update_item_size()` → `item.setSizeHint(self.sizeHint())` + `list_widget.setFixedHeight(recalculated)`.

### Other Views
| File | Class | Key method |
|------|-------|------------|
| `day_view.py` | `DayView` | `_build_timeline()`, resize handles (top/bottom 8px) |
| `week_view.py` | `WeekView` | 7-column grid |
| `month_view.py` | `MonthView` | `_render_month()` |
| `sidebar.py` | `Sidebar` | mini calendar, date selection |
| `event_dialog.py` | `EventDialog` | create/edit event form |
| `styles.py` | — | `get_app_style(dark)` — full Qt stylesheet; color constants |

---

## Flask API — `assistant/api/server.py`

| What | Location |
|------|----------|
| `create_app()` Flask factory | L134 |
| `_api_key_required` decorator | L141 |
| `_run_transcript()` — shared voice logic (rule→hybrid→LLM) | L202 |
| `voice_audio` POST `/voice` | L329 |
| `voice_text` POST `/voice/text` | L356 |
| `voice_verify` GET `/voice/verify/<token>` | L172 |
| Events endpoints (list/get/create/update/delete) | L370–432 |
| Todos endpoints (list/create/update/toggle/delete/reorder) | L435–517 |
| `config_get` / `config_patch` | L521 / L531 |

---

## Config — `assistant/config.py`

| Model | Location | Key fields |
|-------|----------|------------|
| `AppConfig` | L113 | `llm_engine`, `confirmation_level`, `verify_fast_path` |
| `UIConfig` | L101 | `font_month/week/day/tasks`, `compact_layout`, `dark_mode` |
| `TodoConfig` | L95 | `show_completed`, `sync.mode` |
| `AudioConfig` | L69 | `silence_duration_sec`, `device_index` |
| `TTSConfig` | L84 | `voice`, `rate`, `mute` |
| `load_config()` | L141 | reads `config.yaml` |

---

## Adding a New Action (checklist)

1. Add intent model to `assistant/actions/<domain>/intent.py`
2. Add `@register` class to `assistant/actions/<domain>/action.py` (see `BaseAction` in `base.py:14`)
3. Set `view_switch: ClassVar[str]` if the action should auto-switch UI view
4. Re-export from `assistant/actions/<domain>/__init__.py`
5. The `ActionRegistry` and LLM system prompt pick it up automatically

---

## Common Bug Areas

| Symptom | Where to look |
|---------|--------------|
| Task list doesn't update after change | `QTimer.singleShot(0, self.todo_changed.emit)` pattern in `TodoListWidget`; `TodoView.refresh()` L1320 |
| Enter key in new task field does nothing | `_commit()` in `_make_new_task_row()` — check `blockSignals` not left True |
| Expanded task row doesn't resize | `_update_item_size()` in `TodoItemWidget` L829 |
| Subtasks not deleted with parent task | `_on_deleted()` in `TodoListWidget` — must call `delete_subtasks_for_todo()` first |
| Voice command goes to LLM instead of fast path | `RULE_THRESHOLD = 0.85` in `rule_parser.py:66`; check confidence in `RuleParseResult` |
| Background verifier applying stale correction | `_detect_user_change()` in `pipeline.py:562` |
| New DB field not persisting | Add to `_TODO_MIGRATIONS` list AND to `update_todo`'s `allowed` set |
| View doesn't switch after voice action | Set `view_switch` on action class; handle value in `_handle_status()` `window.py:540` |
| iOS sync not seeing new field | Check `Models.swift` `Todo` struct and `APIClient.swift` `updateTodo()` |
