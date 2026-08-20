"""Auto-generate a workout routine from a free-text goal.

Two internal LLM calls (reusing IntentParser.call_llm_json — the same shared
per-provider HTTP call path as every other structured-output call in this
codebase, see assistant/intent/parser.py):
  1. Expand the user's goal into a structured WorkoutTemplate/Block/SetTemplate
     shape (validated with the pydantic models below).
  2. A short, single-pass self-critique for training-balance concerns.

The result is written to the DB as a draft template (status='draft') — nothing
is silently finalized. A later phase's client UI calls
PATCH /workout/templates/<id>/approve (or edits+replaces it) to finalize it.
"""

from __future__ import annotations

import datetime
import uuid
from typing import ClassVar, List, Optional, Type

from pydantic import BaseModel, Field, ValidationError

from assistant.actions import register
from assistant.actions.base import BaseAction, BaseIntent
from assistant.actions.workout_routine.intent import GenerateWorkoutRoutineIntent
from assistant.exceptions import ParseError

# ---------------------------------------------------------------------------
# Structured-output schema the first LLM call must fill in. Mirrors the shape
# of WorkoutTemplate/Block/SetTemplate in
# MACalendar-iOS/MACalendar-iOS/Workout/WorkoutModels.swift, minus IDs (this
# is what the *client* would send before UUIDs exist — the server mints UUIDs
# for exercises/blocks/sets/the template itself when persisting the draft).
# One struct covering both block kinds (unused fields left empty), matching
# how the iOS Block struct is modeled.
# ---------------------------------------------------------------------------

class _GenSet(BaseModel):
    type: str  # 'reps' | 'time'
    target_reps: Optional[int] = None
    weight_kg: Optional[float] = None
    target_seconds: Optional[int] = None
    note: Optional[str] = None


class _GenBlock(BaseModel):
    kind: str  # 'single' | 'superset'
    # .single
    exercise_name: Optional[str] = None
    sets: List[_GenSet] = Field(default_factory=list)
    rest_between_sets_override: Optional[int] = None
    # .superset
    exercise_name_a: Optional[str] = None
    exercise_name_b: Optional[str] = None
    sets_a: List[_GenSet] = Field(default_factory=list)
    sets_b: List[_GenSet] = Field(default_factory=list)
    rest_after_round: Optional[int] = None


class _GenTemplate(BaseModel):
    name: str
    default_rest_between_sets: int = 90
    default_rest_between_exercises: int = 120
    blocks: List[_GenBlock] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ROUTINE_SCHEMA_PROMPT = """You are an expert strength & conditioning coach. Expand the user's \
free-text workout goal into ONE structured workout routine (a single WorkoutTemplate). \
Respond with ONLY a JSON object, no prose, no markdown fences, matching EXACTLY this shape:

{
  "name": "<short routine name>",
  "default_rest_between_sets": <int seconds, e.g. 90>,
  "default_rest_between_exercises": <int seconds, e.g. 120>,
  "blocks": [
    {
      "kind": "single",
      "exercise_name": "<exercise name>",
      "sets": [
        {"type": "reps", "target_reps": <int>, "weight_kg": <float or null>, "target_seconds": null, "note": null}
      ],
      "rest_between_sets_override": <int seconds or null>
    },
    {
      "kind": "superset",
      "exercise_name_a": "<exercise A name>",
      "exercise_name_b": "<exercise B name>",
      "sets_a": [ {"type": "reps", "target_reps": <int>, "weight_kg": null, "target_seconds": null, "note": null} ],
      "sets_b": [ {"type": "reps", "target_reps": <int>, "weight_kg": null, "target_seconds": null, "note": null} ],
      "rest_after_round": <int seconds or null>
    }
  ]
}

Rules:
  - A set's "type" is "reps" for a rep-based set (fill target_reps, optional weight_kg) or "time" \
for a timed hold (fill target_seconds instead of target_reps).
  - Every "reps" set needs a positive integer target_reps; every "time" set needs a positive \
integer target_seconds. All rest values must be >= 0.
  - Every block needs at least one set ("sets" for kind="single"; both "sets_a" and "sets_b" \
non-empty for kind="superset").
  - In a "superset" block, exercise_name_a and exercise_name_b must be two DIFFERENT exercises \
(never the same exercise twice back-to-back in one block).
  - If the goal implies multiple days (e.g. "3-day split"), still return ONE template whose \
blocks cover the full requested split as one coherent session plan, unless the user clearly \
asked for a single day's workout.
  - Keep exercise names concise and conventional (e.g. "Barbell Bench Press", not a paragraph).
  - Return ONLY the JSON object described above."""

_CRITIQUE_PROMPT = """You are a strength & conditioning coach doing a quick sanity check on a \
generated workout routine. Look for training-balance concerns: all-push with no pull, an \
obviously lopsided muscle-group split, absurd/excessive volume for the stated goal, or missing \
rest. Respond with ONLY a JSON object: {"note": "<1-3 sentence critique, or empty string if you \
see no concerns>"}. Keep it concise and specific — no filler."""


class GenerationError(ParseError):
    """Raised when the LLM's generated routine fails schema or sanity validation."""


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

@register
class GenerateWorkoutRoutineAction(BaseAction):
    action_name: ClassVar[str] = "generate_workout_routine"
    description: ClassVar[str] = (
        "Auto-generate a brand-new workout routine/split from a free-text fitness goal and save "
        "it as a draft for the user to review. "
        "Triggers on: 'create/generate/build me a workout', 'make me a routine', 'give me a push "
        "pull legs split', 'design a 3-day upper lower program', 'plan a beginner strength "
        "routine'. "
        "Do NOT use this for logging a completed workout, or for editing/tweaking an existing "
        "routine — only for generating a brand-new one from scratch."
    )
    intent_model: ClassVar[Type[BaseIntent]] = GenerateWorkoutRoutineIntent
    parameters_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "The user's free-text description of the routine they want, verbatim or "
                    "lightly cleaned up, e.g. '3-day push pull legs hypertrophy split' or "
                    "'beginner full body routine, 3 days a week'."
                ),
            },
        },
        "required": ["goal"],
    }

    def execute(self, intent: GenerateWorkoutRoutineIntent, config) -> str:  # type: ignore[override]
        from assistant.actions import registry as global_registry
        from assistant.db import get_db
        from assistant.intent.parser import IntentParser

        parser = IntentParser(config, global_registry)

        generated = self._generate_routine(parser, intent.goal)
        self._validate_routine(generated)
        critique = self._self_critique(parser, intent.goal, generated)

        db = get_db()
        self._persist_draft(db, generated)

        message = f"I've drafted '{generated.name}' for you to review."
        if critique:
            message += f" One note: {critique}"
        return message

    # ------------------------------------------------------------------
    # LLM call 1: generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_routine(parser: "IntentParser", goal: str) -> _GenTemplate:
        user_prompt = f"User's goal: {goal!r}\n\nProduce the JSON routine now."
        data = parser.call_llm_json(_ROUTINE_SCHEMA_PROMPT, user_prompt)
        try:
            return _GenTemplate.model_validate(data)
        except ValidationError as e:
            raise GenerationError(f"Could not generate a valid routine: {e}") from e

    # ------------------------------------------------------------------
    # Sanity validation (beyond pydantic schema validation): reps > 0,
    # rest >= 0, no fully-empty blocks, exercise names non-empty, no
    # immediately-duplicated exercise back-to-back within a block.
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_routine(template: _GenTemplate) -> None:
        if not template.name.strip():
            raise GenerationError("Generated routine has no name.")
        if not template.blocks:
            raise GenerationError("Generated routine has no exercises.")
        if template.default_rest_between_sets < 0 or template.default_rest_between_exercises < 0:
            raise GenerationError("Generated routine has a negative default rest duration.")

        def _check_set(s: _GenSet, where: str) -> None:
            if s.type == "reps":
                if not s.target_reps or s.target_reps <= 0:
                    raise GenerationError(f"Generated routine has a non-positive rep count in {where}.")
            elif s.type == "time":
                if not s.target_seconds or s.target_seconds <= 0:
                    raise GenerationError(f"Generated routine has a non-positive hold time in {where}.")
            else:
                raise GenerationError(f"Generated routine has an unknown set type in {where}.")

        for i, block in enumerate(template.blocks):
            where = f"block {i + 1}"
            if block.kind == "single":
                if not (block.exercise_name or "").strip():
                    raise GenerationError(f"Generated routine is missing an exercise name in {where}.")
                if not block.sets:
                    raise GenerationError(f"Generated routine has an empty block ({where}).")
                if block.rest_between_sets_override is not None and block.rest_between_sets_override < 0:
                    raise GenerationError(f"Generated routine has a negative rest duration in {where}.")
                for s in block.sets:
                    _check_set(s, where)
            elif block.kind == "superset":
                name_a = (block.exercise_name_a or "").strip()
                name_b = (block.exercise_name_b or "").strip()
                if not name_a or not name_b:
                    raise GenerationError(f"Generated routine is missing an exercise name in {where}.")
                if name_a.lower() == name_b.lower():
                    raise GenerationError(
                        f"Generated routine repeats the same exercise back-to-back within {where}."
                    )
                if not block.sets_a or not block.sets_b:
                    raise GenerationError(f"Generated routine has an empty block ({where}).")
                if block.rest_after_round is not None and block.rest_after_round < 0:
                    raise GenerationError(f"Generated routine has a negative rest duration in {where}.")
                for s in block.sets_a + block.sets_b:
                    _check_set(s, where)
            else:
                raise GenerationError(f"Generated routine has an unknown block kind in {where}.")

    # ------------------------------------------------------------------
    # LLM call 2: one-shot self-critique (not a retry loop — best-effort,
    # never blocks drafting on failure)
    # ------------------------------------------------------------------

    @staticmethod
    def _self_critique(parser: "IntentParser", goal: str, template: _GenTemplate) -> str:
        summary_lines = [f"Routine: {template.name}"]
        for i, block in enumerate(template.blocks):
            if block.kind == "single":
                summary_lines.append(
                    f"  Block {i + 1} (single): {block.exercise_name} — {len(block.sets)} set(s)"
                )
            else:
                summary_lines.append(
                    f"  Block {i + 1} (superset): {block.exercise_name_a} + {block.exercise_name_b} "
                    f"— {len(block.sets_a)}/{len(block.sets_b)} set(s)"
                )
        summary = "\n".join(summary_lines)
        user_prompt = f"User's goal: {goal!r}\n\nGenerated routine:\n{summary}\n\nAny balance concerns?"
        try:
            data = parser.call_llm_json(_CRITIQUE_PROMPT, user_prompt)
            return str(data.get("note", "")).strip()
        except Exception:
            return ""  # self-critique is best-effort; never block drafting on its failure

    # ------------------------------------------------------------------
    # Persistence: reuse-or-create exercises by case-insensitive name match,
    # then write the template (+blocks+sets) as a draft.
    # ------------------------------------------------------------------

    @staticmethod
    def _persist_draft(db, template: _GenTemplate) -> str:
        now = datetime.datetime.now().isoformat()

        def _exercise_id(name: str) -> str:
            name = name.strip()
            existing = db.find_workout_exercise_by_name(name)
            if existing:
                return existing["id"]
            new_id = str(uuid.uuid4())
            db.create_workout_exercise(id=new_id, name=name, created_at=now)
            return new_id

        def _set_payload(s: _GenSet) -> dict:
            return {
                "id": str(uuid.uuid4()),
                "type": s.type,
                "target_reps": s.target_reps,
                "weight_kg": s.weight_kg,
                "target_seconds": s.target_seconds,
                "note": s.note,
            }

        blocks_payload = []
        for block in template.blocks:
            block_id = str(uuid.uuid4())
            if block.kind == "single":
                blocks_payload.append({
                    "id": block_id,
                    "kind": "single",
                    "exercise_id": _exercise_id(block.exercise_name),
                    "sets": [_set_payload(s) for s in block.sets],
                    "rest_between_sets_override": block.rest_between_sets_override,
                    "exercise_id_a": None,
                    "exercise_id_b": None,
                    "sets_a": [],
                    "sets_b": [],
                    "rest_after_round": None,
                })
            else:
                blocks_payload.append({
                    "id": block_id,
                    "kind": "superset",
                    "exercise_id": None,
                    "sets": [],
                    "rest_between_sets_override": None,
                    "exercise_id_a": _exercise_id(block.exercise_name_a),
                    "exercise_id_b": _exercise_id(block.exercise_name_b),
                    "sets_a": [_set_payload(s) for s in block.sets_a],
                    "sets_b": [_set_payload(s) for s in block.sets_b],
                    "rest_after_round": block.rest_after_round,
                })

        template_id = str(uuid.uuid4())
        db.create_workout_template({
            "id": template_id,
            "name": template.name,
            "default_rest_between_sets": template.default_rest_between_sets,
            "default_rest_between_exercises": template.default_rest_between_exercises,
            "created_at": now,
            "status": "draft",
            "blocks": blocks_payload,
        })
        return template_id
