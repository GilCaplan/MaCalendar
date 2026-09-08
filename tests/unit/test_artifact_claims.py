"""The published explainers must agree with the code they describe.

Three artifacts are published to public URLs. They quote constants — the
routing threshold, the confidence multipliers, how many verbs the table
holds, how many past commands are retrieved — and every one of those is a
number somebody can change in an afternoon without ever opening the HTML.
Several of them are quoted on more than one page, so a check that reads only
one page misses the other's drift entirely — that already happened once (the
architecture page carried a stale test count for weeks because the checks
only read the internals page). Most checks below run against every published
page and skip whichever ones don't make the claim, rather than assuming in
advance which page says what; that's what lets a check catch drift on a page
that didn't exist yet when the check was written.

That already happened, twice. The pages claimed 706 tests when there were
778, and "55% of the pool has never been reviewed" when purging the test
entries had moved it to 48%. Neither is a big error; both are the kind that
make a reader stop trusting the parts they cannot check.

So the agreement is a test rather than a promise. Each case below reads the
value out of the code and asserts the artifact says the same thing. When a
constant changes, this goes red and names the file to edit — which is the
whole point, because the alternative is noticing months later.

Claims that cannot be mechanised — measured accuracies, latencies, anything
from a corpus run — are not here. Those live in ASSISTANT_AUDIT_SUMMARY.md,
and `test_measured_claims_cite_a_run` checks that the summary still contains
the run the artifact quotes, so at least the citation cannot rot silently.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "DOCUMENTATION" / "artifacts"
INTERNALS = ARTIFACTS / "internals.html"


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
          7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
          12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
          16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
          20: "twenty"}


def _word(n: int) -> str:
    """Small numbers are spelled out in prose; larger ones are not."""
    return _WORDS.get(n, str(n))


def _prose(path: pathlib.Path) -> str:
    """The page's words, with SVG coordinates, CSS and JS code stripped out.

    Diagram geometry is full of bare numbers, and matching '0.85' against a
    path's y-coordinate would let a claim pass for the wrong reason. The
    explorable pages carry an inline <script> full of its own numbers
    (viewBox coordinates, panel scale factors, array indices) — a blind
    `<script>` strip stopped those from leaking in, but every one of
    explorer.html's actual claims (its panels' `sum`/`more` fields) also
    lives *inside* that script, as JS template-literal strings rendered into
    the DOM at runtime rather than present as static HTML. Stripping the
    whole block first would silently drop everything there was to check on
    that page, which is worse than the noise it fixes. So: pull the
    backtick-delimited string content out of <script> first — that's where
    this codebase's multi-line HTML content lives, as opposed to the
    double-quoted strings used for both content and code (selectors,
    attributes) — and keep only that.
    """
    s = path.read_text()
    recovered = " ".join(
        lit for block in re.findall(r"<script>(.*?)</script>", s, flags=re.S)
        for lit in re.findall(r"`([^`]*)`", block)
    )
    s = re.sub(r"<svg.*?</svg>", " ", s, flags=re.S)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S)
    s = s + " " + recovered
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


PAGES = sorted(ARTIFACTS.glob("*.html")) if ARTIFACTS.exists() else []


@pytest.fixture(scope="module")
def prose() -> str:
    if not INTERNALS.exists():
        pytest.skip(f"{INTERNALS} not present")
    return _prose(INTERNALS)


@pytest.fixture(scope="module")
def all_prose() -> dict:
    """Every published page, for claims that appear on more than one.

    The architecture page carried a stale test count for weeks because the
    checks only read the internals page — the drift was on the artifact
    nobody was testing.
    """
    if not PAGES:
        pytest.skip("no artifacts present")
    return {p.name: _prose(p) for p in PAGES}


# ---------------------------------------------------------------------------
# Routing — the number the whole page is organised around
# ---------------------------------------------------------------------------

def test_the_routing_threshold_matches_the_parser(all_prose):
    from assistant.intent.rule_parser import RULE_THRESHOLD
    for name, text in all_prose.items():
        if "rout" not in text.lower():
            continue
        import re as _re
        # word-bounded: "0.8" must not be satisfied by the "0.85" inside a
        # multiplier row (that substring accident green-lit a stale page once)
        assert _re.search(rf"{_re.escape(str(RULE_THRESHOLD))}(?![0-9])", text), (
            f"the parser routes at {RULE_THRESHOLD}; {name} says otherwise")


def test_every_confidence_multiplier_is_quoted_correctly(all_prose):
    """The four penalties, read out of the function that applies them."""
    src = (ROOT / "assistant" / "intent" / "rule_parser.py").read_text()
    body = src.split("def _compute_confidence")[1].split("\ndef ")[0]
    multipliers = sorted({m.group(1) for m in re.finditer(r"multiplier \*= (0\.\d+)", body)})
    assert multipliers, "no multipliers found — has _compute_confidence been rewritten?"
    for name, text in all_prose.items():
        # "confidence" alone also matches architecture.html's unrelated routing
        # claim ("confidence ≥ 0.85") — anchor on "multipl" specifically so
        # that page (which never states the per-case multipliers) is correctly
        # skipped rather than held to a claim it doesn't make.
        if "multipl" not in text.lower():
            continue
        for value in multipliers:
            # 0.7 in code is written 0.70 on the page; accept either spelling.
            spellings = {value, f"{float(value):.2f}"}
            assert any(s in text for s in spellings), (
                f"_compute_confidence multiplies by {value}, which {name} never mentions")


# ---------------------------------------------------------------------------
# The verb table and the action registry
# ---------------------------------------------------------------------------

def test_the_size_of_the_verb_table_is_current(all_prose):
    from assistant.intent.rule_parser import INTENT_MAP
    for name, text in all_prose.items():
        if "verb" not in text.lower():
            continue
        assert f"{len(INTENT_MAP)} verb" in text, (
            f"INTENT_MAP holds {len(INTENT_MAP)} verbs; {name} quotes a different count")


def test_the_number_of_rule_reachable_actions_is_current(all_prose):
    from assistant.intent.rule_parser import INTENT_MAP
    reachable = len(set(INTENT_MAP.values()))
    for name, text in all_prose.items():
        if "reachable" not in text.lower():
            continue
        assert re.search(rf"\b{reachable}\b", text), (
            f"{reachable} actions are reachable by rule; {name} does not say so")


def test_the_split_between_task_and_other_actions_is_current(all_prose):
    """'Eight of the fifteen actions are about tasks' — both halves."""
    registry = _loaded_registry()
    names = sorted(registry)
    task_actions = [n for n in names if "todo" in n or "subtask" in n]
    task_word, total_word = _word(len(task_actions)), _word(len(names))
    for name, text in all_prose.items():
        # "N of the M actions" alone also matches the unrelated rule-reachable
        # claim ("nine of the fifteen actions are reachable this way") — anchor
        # on "about task" too, or explorer.html's "9 of the 15 reachable" false-
        # triggered this check against the wrong pair of numbers.
        if not re.search(r"of\s+the\s+\w+\s+actions?\s+are\s+about\s+task", text, re.I):
            continue
        assert re.search(rf"\b{task_word}\s+of\s+the\s+{total_word}\b", text, re.I), (
            f"{len(task_actions)} of {len(names)} actions are task actions; "
            f"{name}'s phrasing no longer matches")


def _loaded_registry():
    """Every action the app defines, found by class rather than by registry.

    conftest swaps the global registry for a two-action dummy so unit tests
    are not at the mercy of the real one, so reading it here counts the
    fixture instead of the app.
    """
    import importlib
    import pkgutil

    import assistant.actions as A
    from assistant.actions.base import BaseAction
    for mod in pkgutil.walk_packages(A.__path__, "assistant.actions."):
        try:
            importlib.import_module(mod.name)
        except Exception:      # an optional action module must not fail the check
            pass

    found = set()
    stack = list(BaseAction.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        name = getattr(cls, "action_name", "")
        # Only the app's own actions: conftest defines a dummy action of its
        # own, and counting it would report one more action than exists.
        module = getattr(cls, "__module__", "")
        if name and module.startswith("assistant.actions."):
            found.add(name)
    return found


# ---------------------------------------------------------------------------
# Retrieval of past commands
# ---------------------------------------------------------------------------

def test_the_number_of_examples_retrieved_matches_the_default(all_prose):
    from assistant.intent.memory import CommandMemory
    import inspect
    k = inspect.signature(CommandMemory.retrieve).parameters["k"].default
    for name, text in all_prose.items():
        if "past command" not in text.lower() and "closest" not in text.lower() \
                and "most similar" not in text.lower():
            continue
        assert re.search(rf"\b(only )?{_word(k)}\b", text, re.I) or f"k={k}" in text, (
            f"retrieve() defaults to k={k}; {name} quotes a different number")


def test_the_similarity_weights_are_quoted_correctly(prose):
    """0.6 word overlap + 0.4 sequence similarity, stated as percentages."""
    src = (ROOT / "assistant" / "intent" / "memory.py").read_text()
    m = re.search(r"score\s*=\s*(0\.\d+)\s*\*\s*jacc\s*\+\s*(0\.\d+)\s*\*\s*seq", src)
    assert m, "the similarity formula has moved — update this test and the artifact"
    jacc, seq = (int(round(float(g) * 100)) for g in m.groups())
    assert f"{jacc}% word overlap" in prose, f"scoring is {jacc}% Jaccard, artifact disagrees"
    assert f"{seq}% sequence" in prose, f"scoring is {seq}% sequence, artifact disagrees"


def test_the_candidate_pool_size_is_current(prose):
    src = (ROOT / "assistant" / "intent" / "memory.py").read_text()
    m = re.search(r"ORDER BY ts DESC LIMIT (\d+)", src)
    assert m, "the retrieval query has moved"
    n = int(m.group(1))
    assert f"{n:,}" in prose or str(n) in prose, (
        f"the pool is the most recent {n} commands; the artifact says otherwise")


# ---------------------------------------------------------------------------
# The models
# ---------------------------------------------------------------------------

def test_the_models_named_are_the_models_configured(all_prose):
    """Whisper, spaCy and the LLM, as config.example.yaml and the code set them."""
    cfg = (ROOT / "config.example.yaml").read_text()
    llm = re.search(r"model:\s*\"(llama[^\"]+)\"", cfg)
    assert llm, "the default Ollama model is no longer a llama build"
    _, _, size = llm.group(1).partition(":")

    parser = (ROOT / "assistant" / "intent" / "rule_parser.py").read_text()
    spacy_model = re.search(r'spacy\.load\("([^"]+)"\)', parser)
    assert spacy_model, "the rule parser no longer loads a spaCy model by this name"

    whisper = re.search(r"model:\s*\"mlx-community/whisper-(\w+)-mlx\"", cfg)
    assert whisper, "config.example.yaml no longer names a Whisper size this way"

    for name, text in all_prose.items():
        if "llama" in text.lower():
            assert size.upper() in text.upper(), (
                f"the configured model is {llm.group(1)}; {name} quotes a different size")
        if re.search(r"\bwhisper\b.{0,20}\b(tiny|base|small|medium|large)\b", text, re.I):
            assert whisper.group(1) in text.lower(), (
                f"{name} names a Whisper size but not the one actually configured")

    # The exact spaCy filename is technical-page detail, internals.html only,
    # by design — a "big picture" page names Whisper by parameter count
    # instead (explorer.html: "74M"), not by this identifier. A generic "does
    # the page attempt this claim" marker false-triggered on unrelated
    # snake_case identifiers already in internals.html's own API examples
    # (routed_to_llm, base_updated_at) — checking only the one page that is
    # actually supposed to make this claim avoids guessing at intent from text.
    internals_text = all_prose.get(INTERNALS.name)
    if internals_text and "spacy" in internals_text.lower():
        assert spacy_model.group(1) in internals_text, (
            "internals.html must name the spaCy model the parser actually loads")


def test_the_artifact_does_not_claim_an_embedding_model(prose):
    """Retrieval is lexical. If that changes, the page has to change with it."""
    src = (ROOT / "assistant" / "intent" / "memory.py").read_text()
    assert "SequenceMatcher" in src, (
        "retrieval no longer uses SequenceMatcher — the 'no embedding model' "
        "claim in the artifact may now be false")


def test_the_endpoint_and_action_counts_on_the_summary_page(all_prose):
    """The architecture page opens with a stat block. Each number is checkable."""
    server = (ROOT / "assistant" / "api" / "server.py").read_text()
    endpoints = len(re.findall(r"@app\.(?:get|post|patch|delete|put)\(", server))
    actions = len(_loaded_registry())
    for name, text in all_prose.items():
        if "Endpoints" not in text:
            continue
        assert re.search(rf"Endpoints\s+{endpoints}\b", text), (
            f"{name} miscounts the endpoints; there are {endpoints}")
        assert re.search(rf"Actions\s+{actions}\b", text), (
            f"{name} miscounts the actions; there are {actions}")


def test_the_line_count_on_the_summary_page_is_not_stale(all_prose):
    """Quoted to the hundred, so it only has to be close — but not by 2,000."""
    import subprocess
    out = subprocess.run(
        ["bash", "-c",
         "find assistant scripts -name '*.py' | xargs wc -l | tail -1"],
        capture_output=True, text=True, cwd=ROOT).stdout
    m = re.search(r"(\d+)\s+total", out)
    if not m:
        pytest.skip("could not count the Python lines")
    actual = int(m.group(1))
    for name, text in all_prose.items():
        for q in re.finditer(r"Python\s+([\d,]+)\s+lines", text):
            claimed = int(q.group(1).replace(",", ""))
            assert abs(actual - claimed) <= 1000, (
                f"{name} says {claimed:,} lines of Python; there are {actual:,}")


def test_no_page_quotes_a_test_count(all_prose):
    """The suite grows on almost every commit, so a count is stale by design.

    It was corrected four times in a single afternoon — and each correction was
    a published page briefly claiming a number that was not true. A figure that
    needs maintaining to stay true, and tells the reader nothing they would act
    on, is worth less than the word "tests".

    Written as a prohibition rather than a tolerance so it cannot creep back:
    the point is not that the number be right, it is that there be no number.
    """
    for name, text in all_prose.items():
        found = re.findall(r"\b[\d,]{2,7}\s+tests?\b", text)
        assert not found, (
            f"{name} quotes a test count ({found}). Say \"tests\" — the number "
            "changes with every commit and nobody reads it as information.")


def test_the_models_are_placed_in_the_right_processes(all_prose):
    """Two of the three models load inside the assistant, not the model server.

    A reader looked at the drawing and concluded the separate box held all
    three, which is a reasonable thing to conclude when it is the only box with
    a model named in it. It holds one. spaCy loads in the rule parser and
    Whisper in the API — both inside the process that does the deciding — and
    the drawing now says so. If that ever stops being true the pages have to
    change with it.
    """
    parser = (ROOT / "assistant" / "intent" / "rule_parser.py").read_text()
    server = (ROOT / "assistant" / "api" / "server.py").read_text()
    assert "spacy.load" in parser, "spaCy no longer loads in the rule parser"
    assert "WhisperSTT" in server, "the API no longer loads a speech model"

    # Only the page that draws the two as separate boxes has to label them:
    # a page discussing the model in prose is not making the claim visually,
    # and demanding a phrase of it would be policing style rather than fact.
    for name, text in all_prose.items():
        if "THE ASSISTANT" not in text:
            continue
        assert "its own process" in text, (
            f"{name} draws the language model beside the assistant without "
            "saying it is a separate process — the distinction a reader got wrong")
        assert "Whisper" in text and "spaCy" in text, (
            f"{name} claims three local models but names only one, which is how "
            "the other two came to look like they lived in the model server")


def test_the_multi_item_title_cap_is_current(all_prose):
    """The explorer states the cap on how many titles one split can produce.

    Read from source rather than asserted, because it is exactly the kind of
    number that moves in a refactor without anyone thinking to update a page
    three files away.

    Checked against the phrase itself, not against "does this number appear
    anywhere on the page" — a first version of this test asked the weaker
    question, and a page with dozens of unrelated numbers on it (0.70, 7.8s,
    ...) made a bare digit-anywhere check pass no matter what the real cap
    was. The point of a claims test is to fail on a wrong number; one that
    cannot fail is not a test.
    """
    src = (ROOT / "assistant" / "intent" / "rule_parser.py").read_text()
    m = re.search(r"return split_items\(body, drop=_PRONOUN_TITLES\)\[:(\d+)\]", src)
    assert m, "the multi-item title split no longer caps itself the way this test expects"
    cap = int(m.group(1))
    words = {8: "eight", 9: "nine", 10: "ten", 12: "twelve"}
    expected = words.get(cap, str(cap))
    for name, text in all_prose.items():
        found = re.search(r"capped at (\w+) items?", text)
        if not found:
            continue
        assert found.group(1) == expected, (
            f"{name} says \"capped at {found.group(1)} items\", which does not "
            f"match the {cap} in rule_parser.py")


def test_the_table_and_column_counts_are_current(all_prose):
    """Quoted as words on the page, so they cannot be caught by a number scan."""
    import sqlite3
    db = pathlib.Path(os.path.expanduser("~/.assistant_tools/calendar.db"))
    if not db.exists():
        pytest.skip("no calendar database on this machine (CI)")
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    tables = len(list(c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")))
    events = len(list(c.execute("PRAGMA table_info(events)")))
    todos = len(list(c.execute("PRAGMA table_info(todos)")))

    words = {16: "sixteen", 19: "nineteen", 21: "twenty-one"}
    for name, text in all_prose.items():
        if "tables" not in text:
            continue
        assert words.get(tables, str(tables)) in text or str(tables) in text, (
            f"{name}: the database has {tables} tables")
        if "EVENT ROW" in text:
            assert f"{events} COLUMNS" in text, f"{name}: an event row has {events} columns"
            assert words.get(todos, str(todos)) in text, f"{name}: a task row has {todos} columns"


def test_measured_claims_cite_a_run_that_still_exists(prose):
    """Accuracies come from a corpus run, and the report is overwritten.

    ASSISTANT_AUDIT.md is regenerated on every audit, so it cannot be the
    source for a published number. The conclusion has to be in the summary,
    which is append-only — this checks the artifact's headline is actually
    recorded there.
    """
    summary = (ROOT / "DOCUMENTATION" / "ASSISTANT_AUDIT_SUMMARY.md").read_text()
    m = re.search(r"(\d+)% correct", prose)
    assert m, "the artifact no longer states an accuracy"
    claimed = m.group(1)
    assert f"{claimed}%" in summary, (
        f"the artifact claims {claimed}% but no run in ASSISTANT_AUDIT_SUMMARY.md "
        "reports it — either the summary is missing a run, or the number is invented")


def test_the_corpus_size_quoted_matches_the_summary(all_prose):
    summary = (ROOT / "DOCUMENTATION" / "ASSISTANT_AUDIT_SUMMARY.md").read_text()
    for name, text in all_prose.items():
        for m in re.finditer(r"(\d+)-command corpus", text):
            assert f"{m.group(1)} commands" in summary, (
                f"{name} cites an {m.group(1)}-command corpus, but no run of that "
                "size is recorded in the summary")


def test_the_memory_comparison_cites_a_run_that_still_exists(all_prose):
    """The k=0 vs k=4 comparison ('scored 98% and 97%') is Run 7's finding.

    Phrased as a two-way score rather than a single "N% correct" — the more
    general test_measured_claims_cite_a_run_that_still_exists doesn't match
    this shape, so it needed its own check or the citation could drift
    unnoticed (exactly the failure mode this whole file exists to prevent,
    on the one number most likely to change once the memory-scaling study
    the k-sweep, the held-out day, the external pool — produces a new
    finding to replace Run 7's inconclusive one).
    """
    summary = (ROOT / "DOCUMENTATION" / "ASSISTANT_AUDIT_SUMMARY.md").read_text()
    for name, text in all_prose.items():
        m = re.search(r"scored (\d+)% and (\d+)%", text)
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        assert f"{a}%" in summary and f"{b}%" in summary, (
            f"{name} claims the memory comparison scored {a}% and {b}%, but "
            "ASSISTANT_AUDIT_SUMMARY.md doesn't record a run with both figures "
            "— either the summary is missing that run, or the page is stale")


# ---------------------------------------------------------------------------
# The privacy rule, which is the one that cannot be allowed to regress
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", sorted(ARTIFACTS.glob("*.html")) if ARTIFACTS.exists() else [])
def test_no_personal_word_list_entry_reaches_a_published_page(path):
    """The pages are public; the vocabulary is the author's own words.

    Anything in the personal word list is by definition a name, a place, or a
    piece of shorthand specific to whoever uses this — exactly what must not
    appear on a URL. Four such words survived a manual sweep once, inside SVG
    aria-labels, so this reads the whole file rather than the prose.
    """
    # Read the real word list, not the scratch copy conftest points at — a
    # scratch vocabulary is empty, so checking it would pass unconditionally.
    # Read-only: the rule about the real stores is that tests must not write
    # to them, and checking a published page for leaks is what it is for.
    import json
    import os
    real = pathlib.Path(os.path.expanduser("~/.assistant_tools/vocab.json"))
    if not real.exists():
        pytest.skip("no personal vocabulary on this machine (CI)")
    try:
        raw = json.loads(real.read_text())
    except (json.JSONDecodeError, OSError):
        pytest.skip("the vocabulary could not be read")
    # The file is a settings object with the word list under "entries";
    # reading it as the list itself picked up its own keys as words.
    found = raw.get("entries") if isinstance(raw, dict) else raw
    words = set()
    for entry in (found or []):
        word = entry.get("word") if isinstance(entry, dict) else entry
        if isinstance(word, str) and word.strip():
            words.add(word.strip().lower())
    if not words:
        pytest.skip("the vocabulary is empty in this environment")
    # A word is a leak unless it has been declared general. Presuming the
    # other way round would mean every new name added to the word list
    # silently became publishable.
    allowed = _public_words()
    text = path.read_text().lower()
    # Short entries collide with ordinary English ('go', 'set'); the risk this
    # guards against is distinctive words, which are long ones.
    leaked = sorted(w for w in words - allowed
                    if len(w) >= 5 and re.search(rf"\b{re.escape(w)}\b", text))
    assert not leaked, (
        f"{path.name} contains personal vocabulary: {leaked}. Replace each with "
        "an invented example, or — only if it is genuinely general — add it to "
        "DOCUMENTATION/artifacts/public_words.txt with a reason.")


def _public_words() -> set[str]:
    path = ARTIFACTS / "public_words.txt"
    if not path.exists():
        return set()
    return {line.strip().lower() for line in path.read_text().splitlines()
            if line.strip() and not line.startswith("#")}


def test_the_named_rule_count_matches_validate(all_prose):
    """"Fifteen named rules" on the explorer must track the module that owns
    them — a rule added without updating the page is how numbers rot."""
    import assistant.engine.validate as v
    n = sum(1 for name in dir(v) if name.startswith("_rule_"))
    word = _word(n)
    for name, text in all_prose.items():
        if "named rule" not in text.lower():
            continue
        assert re.search(rf"\b({n}|{word})\s+named rules", text, re.I), (
            f"validate.py holds {n} named rules; {name} quotes a different count")


def test_the_loop_budget_matches_crosscheck(all_prose):
    from assistant.engine.crosscheck import MAX_REENTRIES
    word = _word(MAX_REENTRIES)
    for name, text in all_prose.items():
        if "loop" not in text.lower() or "re-runs the stage" not in text.lower():
            continue
        assert re.search(rf"at most {word} times", text, re.I), (
            f"the loop budget is {MAX_REENTRIES}; {name} says otherwise")


# ---------------------------------------------------------------------------
# The engine's components — the page names them, so the names must be real
#
# The explorer page draws the engine as its actual objects rather than as
# friendly labels, which is worth more to a reader and rots faster: a class
# renamed in a refactor leaves a page naming something that no longer exists.
# Each check below reads the name out of the module that owns it. They fire
# only on a page that makes the claim (the marker phrase), so a page that
# describes the system at a different altitude is not held to it.
# ---------------------------------------------------------------------------

#: Only a page that draws FastRule's internals uses this phrase.
_ENGINE_MARK = "atomic-item executor"


def _classes(path: pathlib.Path) -> set:
    return {m.group(1) for m in re.finditer(r"^class (\w+)", path.read_text(), re.M)}


def test_the_fastrule_components_named_on_the_page_exist(all_prose):
    """FastRule's inner objects, by the names the page prints."""
    have = _classes(ROOT / "assistant" / "engine" / "fastrule.py")
    for cls in ("FastRule", "Atomicity", "Gatekeeper", "Scorer"):
        assert cls in have, f"{cls} is no longer a class in engine/fastrule.py"
    for name, text in all_prose.items():
        if _ENGINE_MARK not in text:
            continue
        for cls in ("Atomicity", "Gatekeeper", "Scorer"):
            assert cls in text, (
                f"{name} draws FastRule but never names {cls}, which is one of "
                "the objects it is made of")


def test_the_engine_objects_named_on_the_page_exist(all_prose):
    """Engine / DeepSystem / Stage / Component / EngineState."""
    orchestrator = _classes(ROOT / "assistant" / "engine" / "__init__.py")
    component = _classes(ROOT / "assistant" / "engine" / "component.py")
    state = _classes(ROOT / "assistant" / "engine" / "state.py")
    assert {"Engine", "DeepSystem"} <= orchestrator, "the orchestrator's classes moved"
    assert {"Component", "Stage"} <= component, "component.py's classes moved"
    assert "EngineState" in state, "EngineState is no longer defined in state.py"
    for name, text in all_prose.items():
        if _ENGINE_MARK not in text:
            continue
        for ident in ("DeepSystem", "EngineState", "Component", "Stage"):
            assert ident in text, f"{name} draws the engine but never names {ident}"


def test_the_deep_stage_names_match_the_state_contract(all_prose):
    """The stage names are the ones `state.STAGES` declares, in the code."""
    from assistant.engine.state import STAGES
    for name, text in all_prose.items():
        if _ENGINE_MARK not in text:
            continue
        for stage in STAGES:
            if stage == "intake":
                continue          # the orchestrator's own half, drawn as Engine
            assert stage in text, (
                f"{name} draws the deep track but never names the {stage} stage")


def test_the_deferral_reason_classes_are_current(all_prose):
    """A deferral's class decides the handoff — there are exactly three."""
    from assistant.engine.fastrule import (INCAPACITY, REFUSAL, STRUCTURE,
                                           _REASON_CLASS)
    classes = {REFUSAL, STRUCTURE, INCAPACITY}
    assert set(_REASON_CLASS.values()) == classes, (
        "a deferral reason now maps to a class the page does not describe")
    for name, text in all_prose.items():
        if "deferral carries a" not in text.lower():
            continue
        for cls in classes:
            assert cls.upper() in text, (
                f"{name} describes the deferral contract without naming {cls.upper()}")


def test_the_two_fastrule_thresholds_are_current(all_prose):
    """The front door's bar and the per-fragment bar are different numbers."""
    from assistant.engine.generate import SUBITEM_RULE_THRESHOLD
    from assistant.intent.rule_parser import RULE_THRESHOLD
    for name, text in all_prose.items():
        if "per fragment" not in text:
            continue
        for value in (RULE_THRESHOLD, SUBITEM_RULE_THRESHOLD):
            assert re.search(rf"{re.escape(str(value))}(?![0-9])", text), (
                f"{name} quotes the two FastRule bars, but {value} is not one of them")


def test_the_number_of_shipped_classifiers_is_current(all_prose):
    """Three small logistic models ride inside the fast path."""
    from assistant.intent.classifier import ModelRouter
    n = sum(1 for v in vars(ModelRouter()).values() if hasattr(v, "featurizer"))
    for name, text in all_prose.items():
        if "fitted classifiers" not in text:
            continue
        assert re.search(rf"\b{n}\b\s+fitted classifiers", text), (
            f"the router carries {n} fitted classifiers; {name} says otherwise")


def test_the_classifier_feature_counts_are_current(all_prose):
    """Each featurizer's signal count, read from its own `names` list.

    Named signals are the point of these models — a page that quotes how many
    there are has to track the list, or it is quoting a number from a model
    that no longer exists.
    """
    from assistant.intent.classifier import (AtomicityFeatures, KindFeatures,
                                             OperationFeatures)
    counts = {"OperationFeatures": len(OperationFeatures.names),
              "KindFeatures": len(KindFeatures.names),
              "AtomicityFeatures": len(AtomicityFeatures.names)}
    for name, text in all_prose.items():
        for cls, n in counts.items():
            if cls not in text:
                continue
            assert f"{cls} with {n} signals" in text, (
                f"{cls} holds {n} named signals; {name} quotes a different count")


def test_the_count_of_model_calling_stages_is_current(all_prose):
    """"Five of the seven engine stages may call the language model."

    The claim a reader is most likely to act on — how much of the pipeline is
    deterministic — so it is read from the stage modules themselves.
    """
    engine = ROOT / "assistant" / "engine"
    stages = ("transcript", "segment", "decompose", "validate", "generate",
              "crosscheck", "label")
    callers = [s for s in stages
               if re.search(r"call_json\(|parser\.parse", (engine / f"{s}.py").read_text())]
    for name, text in all_prose.items():
        if "stages may call the language model" not in text:
            continue
        assert re.search(rf"\b{_word(len(callers))} of the seven engine stages", text, re.I), (
            f"{len(callers)} of the seven stages can call the model; {name} says otherwise")
# ---------------------------------------------------------------------------
# The datasets the evaluation section describes
# ---------------------------------------------------------------------------

def test_the_dataset_sizes_quoted_are_current(all_prose):
    """Row counts read from the dataset files, not from the prose that cites them.

    These are the numbers a reader would use to judge whether the evaluation
    means anything, and every one of them moves when a set is regenerated.
    """
    import collections
    import json
    pool = ROOT / "dataset" / "inputs" / "history_3000.json"
    sealed = ROOT / "dataset" / "inputs" / "test_split.json"
    generated = ROOT / "dataset" / "fastrule" / "fastrule_7200.jsonl"
    personas = ROOT / "dataset" / "personas" / "personas.jsonl"
    if not all(p.exists() for p in (pool, sealed, generated, personas)):
        pytest.skip("the datasets are not present in this checkout")

    n_pool = json.loads(pool.read_text())["n"]
    n_sealed = json.loads(sealed.read_text())["n"]
    splits = collections.Counter()
    for line in generated.open():
        splits[json.loads(line)["split"]] += 1
    rows = [json.loads(line) for line in personas.open()]
    speakers = {r["persona"] for r in rows}
    assert {r["split"] for r in rows} == {"test"}, (
        "a persona row is no longer test-only — the page says every one of them is")

    for name, text in all_prose.items():
        if "real voice utterances" in text:
            assert f"{n_pool:,} real voice utterances" in text, (
                f"{name} miscounts the verification pool; it holds {n_pool:,}")
        if "rows sealed" in text:
            assert f"{n_sealed} rows sealed" in text, (
                f"{name} miscounts the sealed rows; there are {n_sealed}")
        if "rows expanded from pattern skeletons" in text:
            total = splits["train"] + splits["test"]
            assert f"{total:,} rows expanded from pattern skeletons" in text, (
                f"{name} miscounts the generated set; it holds {total:,} rows")
            assert f"{splits['train']:,} to train and tune on" in text, (
                f"{name} miscounts its training half ({splits['train']:,})")
            assert f"{splits['test']:,} held back" in text, (
                f"{name} miscounts its held-back half ({splits['test']:,})")
        if "synthetic users" in text:
            assert re.search(rf"\b{_word(len(speakers))} synthetic users", text, re.I), (
                f"there are {len(speakers)} personas; {name} says otherwise")
            assert f"{len(rows):,} rows" in text, (
                f"{name} miscounts the persona rows; there are {len(rows):,}")


def test_the_split_drawn_on_the_loop_view_matches_the_files():
    """The seal is now a PICTURE — a bar split train | sealed — not a paragraph.

    Every other check on this page runs against `_prose`, which strips the
    <svg> blocks out on purpose: diagram geometry is full of bare numbers and
    matching a claim against a path coordinate would let it pass for the wrong
    reason. But the loop view's seal guard draws the split with its two row
    counts printed on the bar, and a number a reader can see is a claim
    whatever element it lives in. So this one reads the raw file, and only for
    the two strings the drawing actually prints — narrow enough that a
    coordinate cannot satisfy it by accident.

    The group carries data-claim="seal-split" so the check fires on the
    drawing rather than on any page that happens to mention a seal.
    """
    import json
    pool = ROOT / "dataset" / "inputs" / "history_3000.json"
    sealed = ROOT / "dataset" / "inputs" / "test_split.json"
    if not (pool.exists() and sealed.exists()):
        pytest.skip("the datasets are not present in this checkout")
    n_pool = json.loads(pool.read_text())["n"]
    n_sealed = json.loads(sealed.read_text())["n"]

    drew = False
    for path in PAGES:
        raw = path.read_text()
        if 'data-claim="seal-split"' not in raw:
            continue
        drew = True
        assert f"train &#183; {n_pool - n_sealed:,}" in raw or \
               f"train · {n_pool - n_sealed:,}" in raw, (
            f"{path.name} draws the training half, but the pool holds {n_pool} "
            f"rows of which {n_sealed} are sealed — the bar should say "
            f"{n_pool - n_sealed:,}")
        assert f"sealed &#183; {n_sealed}" in raw or f"sealed · {n_sealed}" in raw, (
            f"{path.name} draws the sealed half as a different number; "
            f"test_split.json holds {n_sealed} rows")
    if not drew:
        pytest.skip("no published page draws the split")
