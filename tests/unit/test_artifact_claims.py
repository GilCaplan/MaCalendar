"""The published explainers must agree with the code they describe.

Two artifacts are published to public URLs. They quote constants — the routing
threshold, the confidence multipliers, how many verbs the table holds, how many
past commands are retrieved — and every one of those is a number somebody can
change in an afternoon without ever opening the HTML.

That already happened. The pages claimed 706 tests when there were 778, and
"55% of the pool has never been reviewed" when purging the test entries had
moved it to 48%. Neither is a big error; both are the kind that make a reader
stop trusting the parts they cannot check.

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

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "DOCUMENTATION" / "artifacts"
INTERNALS = ARTIFACTS / "internals.html"


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
          7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
          12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}


def _word(n: int) -> str:
    """Small numbers are spelled out in prose; larger ones are not."""
    return _WORDS.get(n, str(n))


def _prose(path: pathlib.Path) -> str:
    """The page's words, with SVG coordinates and CSS stripped out.

    Diagram geometry is full of bare numbers, and matching '0.85' against a
    path's y-coordinate would let a claim pass for the wrong reason.
    """
    s = path.read_text()
    s = re.sub(r"<svg.*?</svg>", " ", s, flags=re.S)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S)
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

def test_the_routing_threshold_matches_the_parser(prose):
    from assistant.intent.rule_parser import RULE_THRESHOLD
    assert str(RULE_THRESHOLD) in prose, (
        f"the parser routes at {RULE_THRESHOLD}; the artifact says otherwise")


def test_every_confidence_multiplier_is_quoted_correctly(prose):
    """The four penalties, read out of the function that applies them."""
    src = (ROOT / "assistant" / "intent" / "rule_parser.py").read_text()
    body = src.split("def _compute_confidence")[1].split("\ndef ")[0]
    multipliers = sorted({m.group(1) for m in re.finditer(r"multiplier \*= (0\.\d+)", body)})
    assert multipliers, "no multipliers found — has _compute_confidence been rewritten?"
    for value in multipliers:
        # 0.7 in code is written 0.70 on the page; accept either spelling.
        spellings = {value, f"{float(value):.2f}"}
        assert any(s in prose for s in spellings), (
            f"_compute_confidence multiplies by {value}, which the artifact never mentions")


# ---------------------------------------------------------------------------
# The verb table and the action registry
# ---------------------------------------------------------------------------

def test_the_size_of_the_verb_table_is_current(prose):
    from assistant.intent.rule_parser import INTENT_MAP
    assert f"{len(INTENT_MAP)} verb" in prose, (
        f"INTENT_MAP holds {len(INTENT_MAP)} verbs; the artifact quotes a different count")


def test_the_number_of_rule_reachable_actions_is_current(prose):
    from assistant.intent.rule_parser import INTENT_MAP
    reachable = len(set(INTENT_MAP.values()))
    assert re.search(rf"\b{reachable}\b", prose), (
        f"{reachable} actions are reachable by rule; the artifact does not say so")


def test_the_split_between_task_and_other_actions_is_current(prose):
    """'Eight of the fifteen actions are about tasks' — both halves."""
    registry = _loaded_registry()
    names = sorted(registry)
    task_actions = [n for n in names if "todo" in n or "subtask" in n]
    task_word, total_word = _word(len(task_actions)), _word(len(names))
    assert re.search(rf"\b{task_word}\s+of\s+the\s+{total_word}\b", prose, re.I), (
        f"{len(task_actions)} of {len(names)} actions are task actions; "
        "the artifact's phrasing no longer matches")


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

def test_the_number_of_examples_retrieved_matches_the_default(prose):
    from assistant.intent.memory import CommandMemory
    import inspect
    k = inspect.signature(CommandMemory.retrieve).parameters["k"].default
    assert re.search(rf"\b(only )?{_word(k)}\b", prose, re.I) or f"k={k}" in prose, (
        f"retrieve() defaults to k={k}; the artifact quotes a different number")


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

def test_the_models_named_are_the_models_configured(prose):
    """Whisper, spaCy and the LLM, as config.example.yaml and the code set them."""
    cfg = (ROOT / "config.example.yaml").read_text()
    llm = re.search(r"model:\s*\"(llama[^\"]+)\"", cfg)
    assert llm, "the default Ollama model is no longer a llama build"
    family, _, size = llm.group(1).partition(":")
    assert size.upper().replace("B", "B") in prose.replace(" ", "") or size.upper() in prose, (
        f"the configured model is {llm.group(1)}; the artifact quotes a different size")

    parser = (ROOT / "assistant" / "intent" / "rule_parser.py").read_text()
    spacy_model = re.search(r'spacy\.load\("([^"]+)"\)', parser)
    assert spacy_model and spacy_model.group(1) in prose, (
        "the artifact must name the spaCy model the parser actually loads")

    whisper = re.search(r"model:\s*\"mlx-community/whisper-(\w+)-mlx\"", cfg)
    assert whisper and whisper.group(1) in prose.lower(), (
        "the artifact must name the Whisper size actually configured")


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


def test_the_corpus_size_quoted_matches_the_summary(prose):
    summary = (ROOT / "DOCUMENTATION" / "ASSISTANT_AUDIT_SUMMARY.md").read_text()
    m = re.search(r"(\d+)-command corpus", prose)
    assert m, "the artifact no longer says how big the corpus is"
    assert f"{m.group(1)} commands" in summary, (
        f"no run of {m.group(1)} commands is recorded in the summary")


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
