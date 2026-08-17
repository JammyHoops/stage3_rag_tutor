# All comments — for humanising

Every comment and docstring currently in `stage3/`, `tests/`, `evaluation/`
and `scripts/`, extracted automatically (file:line references) after the
2026-08-17 cleanup pass (TODOs consolidated to `docs/TODO.md`, decision
narrative consolidated to `docs/design/FINDINGS_AND_DECISIONS.md`, so
what's left here should mostly be plain what-it-does comments).

This is a working file for one pass, not a permanent doc — safe to delete
once you're done editing. Edit the wording however you like (this is
exactly the "humanise the phrasing" pass), then either:
- paste the whole file back and I'll apply it file-by-file, or
- tell me which specific lines/files changed and I'll apply just those.

Docstrings are shown by their line span (`lines N-M`); a plain `LN:` is a
`#` comment on that line, and `(inline, after ...)` marks a trailing
comment on a code line (the code snippet is just there so you can find it
in the file — don't need to edit that part).

---


================================================================================
FILE: stage3/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/api/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/api/chat.py
================================================================================
--- docstring (lines 1-18) ---
Chat/conversation endpoints — the API surface for a Claude-Projects-style UI.

PROVENANCE — NEW. Split into its own router rather than growing
``api/main.py`` further. Subject = project, topic = chat within that
project, matching the taxonomy in ``stage3/taxonomy/topics.py`` and the
persistence in ``stage3/conversations/store.py``. No auth exists or is
planned — local-only research prototype, ``student_id`` passed explicitly
per request; see ``api/main.py``'s docstring.

Every endpoint that can trigger an LLM call (POST /conversations,
/reassess, /messages) catches ``llm.client.LLMGenerationError`` and
returns 503, rather than letting a hard failure silently produce a blank
persisted tutor message. ``post_conversation`` also retries the opening
diagnostic question on a re-fetch of an existing conversation that never
got one (0 questions asked, still 'pending') — without this, a
first-creation LLM failure would leave that thread permanently stuck,
since ``get_or_create_conversation`` only reports ``created=True`` once.

L38: # Friendly, fixed client-facing message — deliberately NOT the raw
L39: # provider exception text (str(e)), which could carry internal
L40: # provider/quota details not meant for the frontend. Full detail is
L41: # already in server logs via llm/client.py's logger.error.
--- docstring (lines 81-96) ---
Get-or-create: idempotent per (student, subject, topic). Safe to
    call every time a topic is clicked in the UI; never creates a
    duplicate thread.

    On a genuine first creation, synchronously starts the diagnostic
    round (tutor speaks first) so the opening question is already there
    by the time the frontend fetches messages. This is the only call site
    that passes student_id/profiles into start_diagnostic — see that
    function's docstring for why.

    Also retries the opening question on an existing conversation that
    never actually got one (0 questions asked, still 'pending') — the
    only way that state can persist is a previous LLMGenerationError, and
    without this retry the thread would be stuck forever, since `created`
    only reports True once.

--- docstring (lines 127-133) ---
Explicit "Re-check my understanding" — starts a fresh diagnostic
    round on an existing thread, not a new conversation.

    Deliberately does not pass student_id/profiles to start_diagnostic: a
    re-check means the student already has tutoring history, so this is
    no longer "cold start" in the sense Stage 1 data is meant for.

L142: # reset_diagnostic already ran, so the conversation is left at
L143: # (0 questions asked, 'pending') — cleanly retryable by clicking
L144: # the button again, no extra recovery logic needed here.
--- docstring (lines 151-154) ---
Single-conversation fetch — used by the frontend to refresh
    diagnostic_status/diagnostic_questions_asked after each turn, since
    those change over the life of a thread (unlike the mostly-static
    fields returned by the list endpoint's cached view).


================================================================================
FILE: stage3/api/main.py
================================================================================
--- docstring (lines 1-23) ---
FastAPI surface for Stage 3.

PROVENANCE — /health and /feedback KEPT (adapted) from AI_IT_Helpdesk; the
duplicate RAG API stack was removed rather than merged. /feedback is the
write side of the retrieval feedback loop (counters read back by the
reranker) — during expert evaluation, a reviewer's chunk-relevance
judgements can be committed through it.

/subjects, /subjects/{subject}/topics, and /conversations* (chat.py
router) are NEW — see stage3/api/chat.py for the conversation/chat
backend that supports a Claude-Projects-style UI. /students* (students.py
router) are also NEW — a student directory (derived from who has
conversations; no real login exists) and a mastery read-through.

/tutor below is superseded, not pending: the conversation/chat backend
(chat.py's router) is the live tutoring path the frontend actually calls.
/tutor was an earlier single-shot sketch before the conversational design
was settled — left as a deliberate 501 rather than removed, in case a
non-conversational integration ever needs one.

No student-facing deployment is in scope — local-only for the project
(bind 127.0.0.1).

L43: # Local-only dev CORS: allows the Vite dev server (default port) to call this
L44: # API directly. Explicit origin list, not "*" — costs nothing and documents
L45: # intent. Add another origin here if Vite picks a different port.
L90: # RETIRED — see module docstring. Superseded by chat.py's conversation
L91: # endpoints, not pending implementation.

================================================================================
FILE: stage3/api/students.py
================================================================================
--- docstring (lines 1-16) ---
Student-directory + mastery-read endpoints.

PROVENANCE — NEW. Split into its own router since it wraps two different
modules/schemas kept separate elsewhere (conversations/store.py vs.
student_state/store.py).

No login/registry exists in this prototype by design; ``student_id`` is a
pseudonymous, freely-typed identifier. ``GET /students`` is therefore not
an authoritative roster — it's "everyone who has ever started a
conversation," powering the frontend's searchable student picker as
search-assist, not access control. A student typing an id that's never
been seen before is still valid and expected.

``GET /students/{id}/mastery`` is a thin read-through to
``student_state/store.py::get_knowledge_state``.


================================================================================
FILE: stage3/chunking.py
================================================================================
--- docstring (lines 1-9) ---
Document chunking for the curriculum knowledge base.

PROVENANCE — NEW. Currently a passthrough: ``chunk_document`` returns the
whole document as a single chunk. This is sufficient because every
in-scope connector (Isaac Science, Ada Computer Science) already splits
content into natural sections at ingest time — see those connectors and
docs/design/FINDINGS_AND_DECISIONS.md for why a real sentence-aware
chunker was never needed. See docs/TODO.md if that changes.

--- docstring (lines 17-22) ---
Split one normalised document into chunk dicts ready for the store.

    Input shape (from connectors): {id, text, source, metadata}
    Output shape (for vectordb.store.add_chunks): same keys, with
    chunk-level ids of the form "<doc_id>#<n>".

L33: (inline, after `"id": f"{doc.get('id', 'unknown')}`) # 0",

================================================================================
FILE: stage3/config.py
================================================================================
--- docstring (lines 1-7) ---
Central configuration for Stage 3.

PROVENANCE — ADAPTED from AI_IT_Helpdesk's config module. All values can
be overridden from the environment (.env) so nothing sensitive is
hard-coded. See docs/design/FINDINGS_AND_DECISIONS.md for the reasoning
behind individual defaults (temperature, embedding model, etc).

L19: # Project root = directory containing the stage3/ package
L40: # Local model: no data leaves the machine at embedding time.

================================================================================
FILE: stage3/connectors/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/connectors/ada_computer_science.py
================================================================================
--- docstring (lines 1-31) ---
Connector for Ada Computer Science (adacomputerscience.org).

PROVENANCE — NEW. Third subject for the core/foundation curriculum-tiering
design (docs/design/stage3-curriculum-retrieval-design.md), and the only
connector that delivers a genuine foundation (GCSE) tier — see
docs/design/FINDINGS_AND_DECISIONS.md §2 for why Isaac Science's
Biology/Chemistry content doesn't.

Runs the same open-source platform as Isaac Science (identical JSON shape,
identical API path, on a different domain) — ``_clean_markdown`` and
``_collect_text_fragments`` are imported from ``isaac_science.py`` rather
than duplicated. Tier extraction is structurally different from that
connector though: Isaac Science decides ``difficulty_tier`` once per whole
concept; this one decides it per SECTION, because individual accordion
sections here carry their own ``audience`` list.

``concept_id`` is stored explicitly on every document. ``prerequisites``
is stored as ``None`` — see docs/TODO.md for the foundation-tier trigger
this blocks.

PINNED API VERSION: same version string as Isaac Science (``v4.2.7``) at
time of writing, pinned independently since this is a separate deployment
of the platform. Same failure mode / rediscovery method as documented in
``isaac_science.py``.

Licence is CC BY-NC-SA 4.0 (confirmed via headless-browser render — see
FINDINGS_AND_DECISIONS.md §2). ``spec_code`` is left ``None``: Ada's
audience data includes an ``examBoard`` list per section but not a spec
code number. Project/coursework meta-tags (NEA scenario concepts) are
deliberately excluded from ``_TAG_TO_TOPIC`` — see docs/TODO.md.

L46: # PINNED — see module docstring above before touching this.
L50: (inline, after `REQUEST_TIMEOUT = 15`) # seconds
L52: # Hand-authored, extensible. Keys are Ada tag strings, lowercased with
L53: # spaces->underscores. See docs/TODO.md for excluded project/meta tags.
L59: # design/testing/dev-lifecycle content sits in the Programming paper
L60: # in exam-board specs, not Computer Systems, so it's grouped here too.
L79: # image/sound representation and "creating media" are data-
L80: # representation content in GCSE/A-level specs, not a separate topic.
--- docstring (lines 92-98) ---
Map a section's own audience stages to our difficulty_tier.

    a_level takes priority if both are present. gcse-only sections are the
    genuine foundation content. Anything else (Scotland's own stage
    labels, or Ada's internal "core"/"advanced" labels with neither gcse
    nor a_level present) is skipped, not guessed.

--- docstring (lines 107-112) ---
Split one concept JSON into tiered sections: the top-level intro
    (tiered from the concept's own audience) plus one section per
    accordion sub-item (tiered from that item's own audience — unlike
    Isaac Science, where only the whole concept is tiered). Sections whose
    stages don't resolve to a difficulty_tier are dropped, not guessed.

L132: (inline, after `continue`) # e.g. Scotland-only section — not guessed
L176: # -- API calls -----------------------------------------------------
L189: # The `subjects` query param is a no-op on this platform (same
L190: # finding as Isaac Science) — filter client-side instead. A
L191: # handful of real outliers (Scotland/SQA reference pages, one
L192: # untagged page) lack "computer_science" and are correctly
L193: # excluded here, not a bug.
L230: # -- Document construction ------------------------------------------
L242: (inline, after `return []`) # e.g. fully Scotland-only concept — nothing tiered

================================================================================
FILE: stage3/connectors/base.py
================================================================================
--- docstring (lines 1-5) ---
Base connector interface for all knowledge sources.

PROVENANCE — KEPT (near-verbatim) from AI_IT_Helpdesk. Normalises every
source into the same document shape before anything downstream sees it.

--- docstring (lines 14-21) ---
Abstract base class for all knowledge-base sources.

    Each connector must return a list of document dicts with keys:
    - "id": str (unique within that source — enables stable Chroma IDs)
    - "text": str (full text content, pre-chunking)
    - "source": str (name of the connector)
    - "metadata": dict (e.g. subject, topic, provenance tier, file path)

--- docstring (lines 27-32) ---
Fetch and normalise documents from the source.

        Minimal logic only: file reads / API calls plus light cleaning
        into the standard document schema. Chunking happens later
        (stage3/chunking.py), not here.


================================================================================
FILE: stage3/connectors/curriculum_docs.py
================================================================================
--- docstring (lines 1-16) ---
Connector for curriculum documents on local disk.

PROVENANCE — NEW. Follows the pattern of the helpdesk's transcript
connector (walk a directory, normalise each file into the standard
document schema).

Not currently wired to any real content — every in-scope subject is
sourced from Isaac Science / Ada Computer Science instead (see those
connectors). Kept in case a genuinely document-only source (e.g. a
locally-supplied spec PDF) is ever added — see docs/TODO.md.

Expected layout under data/curriculum/ (drives metadata):

    data/curriculum/<subject>/<provenance_tier>/<files>
    e.g. data/curriculum/biology/awarding_body_spec/organisms.md

L26: # File types readable without extraction libraries; no PDF support yet.
L48: # <subject>/<provenance_tier>/<file> — fall back gracefully if
L49: # the layout is shallower than expected.
L55: (inline, after `except Exception as e:`) # pragma: no cover

================================================================================
FILE: stage3/connectors/isaac_science.py
================================================================================
--- docstring (lines 1-50) ---
Connector for Isaac Science (isaacscience.org) — curriculum retrieval source.

PROVENANCE — NEW. First connector for the core/foundation curriculum-tiering
design (docs/design/stage3-curriculum-retrieval-design.md). Covers Biology
and Chemistry, core (A-level) tier — see ``IsaacChemistryConnector`` below
for the Chemistry variant.

WHY AN API CONNECTOR, NOT A SCRAPER: isaacscience.org is a JS-rendered SPA;
a raw HTML fetch returns an empty shell. The site calls a real, public,
unauthenticated JSON API instead:

    GET {BASE}/pages/concepts?subjects=<subject>&limit=N&start_index=N
        -> {"results": [{"id", "title", "tags", ...}, ...]}
    GET {BASE}/pages/concepts/{id}
        -> full concept: title, tags, audience[].stage (gcse/a_level),
          a "children" tree of markdown content blocks, some laid out as
          an accordion of named sub-sections (natural chunk boundaries).

PINNED API VERSION: the API is version-pinned in the URL (``API_VERSION``
below) with no stable alias — an unversioned path or ``/api/latest/...``
returns a 502 or the SPA's HTML shell instead of JSON. If ``fetch()``
starts returning nothing or logging "stale" warnings: load isaacscience.org
in a browser with devtools open, find a request under
``/api/v.../api/...``, and update ``API_VERSION`` to match.

CONTENT SEGMENTATION: each concept is split at its own natural boundaries
(the top-level intro plus each accordion sub-section) into one document
per section — see ``_extract_sections``. This is why ``chunking.py``'s
passthrough chunker is adequate here: the structure-aware splitting
already happened at this layer.

TOPIC MAPPING: Isaac's own ``tags`` are more granular than the fixed
chat-UI topic list needs. ``_TAG_TO_TOPIC_BY_SUBJECT`` is a small,
hand-authored, extensible lookup — an unmapped concept is still ingested
(subject-scoped retrieval still finds it) but logged with a warning.

No real GCSE ("foundation") content exists on this source for Biology or
Chemistry — see docs/design/FINDINGS_AND_DECISIONS.md §2 for what was
checked and why. ``prerequisites`` is stored as ``None`` — no cross-concept
dependency graph is available from this source; see docs/TODO.md.
``spec_code``/``misconceptions`` are likewise not present in this source's
data. The AS/A2 split isn't available at this API's granularity, only
``audience[].stage`` (gcse/a_level); ``level`` stores the raw stage value.
LaTeX/mhchem markup (``$\ce{C6H12O6}$`` etc.) is left as-is in chunk text.

Licence is CC BY 4.0 (confirmed via headless-browser render — see
FINDINGS_AND_DECISIONS.md §2). ``tutor/attribution.py`` derives licence
from ``source`` rather than this stored field, robust regardless of
ingest timing.

L65: # PINNED — see module docstring above before touching this.
L69: (inline, after `REQUEST_TIMEOUT = 15`) # seconds
L71: # Hand-authored, extensible — see module docstring "TOPIC MAPPING".
L72: # Keyed by subject, then by Isaac tag string (lowercased, spaces->underscores).
L73: # One dict per subject: tag vocabularies don't overlap meaningfully across
L74: # subjects (biology's "transport" and chemistry's "transport [of
L75: # electrons]" aren't the same concept).
L78: # biochemistry
L87: # cell biology
L95: # genetics
L102: # physiology
L112: # ecology
L117: # data analysis / statistics
L123: # Isaac tags every chemistry concept with one of four broad
L124: # category tags (physical/organic/inorganic/foundations) as well
L125: # as finer-grained tags. Mapping both is deliberately redundant:
L126: # if Isaac ever drops the broad tag, the specific one still
L127: # resolves it.
--- docstring (lines 153-153) ---
Strip Isaac's glossary-inline markup down to the plain term text.

--- docstring (lines 158-163) ---
Recursively walk a content node's children, collecting text.

    Figure nodes contribute their caption as "[Figure: ...]" rather than
    the image itself — non-text content is a documented limitation, not
    handled here.

--- docstring (lines 177-180) ---
Split one concept JSON into natural sections: the top-level intro
    (all non-accordion content blocks combined) plus one section per
    accordion sub-item, e.g. "Carbohydrates" -> "Carbohydrates -
    Monosaccharides".

L228: # -- API calls -----------------------------------------------------
L245: # Filter client-side on tags too, regardless of whether the
L246: # `subjects` query param is fully reliable: cheap to
L247: # double-check here, expensive to silently ingest the wrong
L248: # subject's content.
L285: # -- Document construction ------------------------------------------
L299: (inline, after `return []`) # core tier only from this source; no GCSE content
--- docstring (lines 342-347) ---
Chemistry variant — same platform, API and parsing logic as
    ``IsaacScienceConnector``; only ``subject`` (and therefore the tag-to-
    topic map it looks up) differs. A thin subclass rather than a second
    copy, so ``connectors/registry.py`` keeps its "one class per registry
    key, no-arg instantiation" convention.


================================================================================
FILE: stage3/connectors/registry.py
================================================================================
--- docstring (lines 1-8) ---
Connector registry.

PROVENANCE — pattern KEPT from the helpdesk's connector mapping; the IT
sources it pointed at have been removed. All three in-scope subjects are
sourced: Isaac Science for Biology/Chemistry (core tier only), Ada
Computer Science (core + foundation tiers — see that connector's
docstring for why it's the only one with real foundation content).

L19: (inline, after `"isaac_science": IsaacScienceConnector,`) # biology, core tier
L20: (inline, after `"isaac_chemistry": IsaacChemistryConnector,`) # chemistry, core tier
L21: (inline, after `"ada_computer_science": AdaComputerScienceConnecto`) # core + foundation

================================================================================
FILE: stage3/conversations/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/conversations/store.py
================================================================================
--- docstring (lines 1-25) ---
Durable chat/conversation storage — one thread per (student, subject, topic).

PROVENANCE — NEW. Supports a Claude-Projects-style UI: subject = project,
topic = chat within that project. Topic and conversation are 1:1 (one
continuous thread per (student, subject, topic), enforced by the UNIQUE
constraint below), so every topic in the frontend's fixed taxonomy is
directly clickable as a chat — ``get_or_create_conversation`` is the entry
point, not ``create_conversation`` directly.

Kept in its own SQLite file (``CONFIG.paths.conversations_db``), separate
from ``student_state/store.py`` — that file's schema is mastery-only;
conversation transcripts are a different concern (turn-by-turn chat
history, not a knowledge-state estimate).

SCHEMA:
    conversations : one row per chat thread
                    (student, subject, topic, created_at, updated_at)
    messages      : one row per turn, ordered by id
                    (conversation_id, role ['student'|'tutor'], content,
                     chunk_doc_ids [JSON list, tutor turns only], created_at)

``content`` is always stored post-redaction: rows are replayed back into
prompts as conversation history, so they must already carry the same
privacy guarantee ``redaction.redact()`` provides.

--- docstring (lines 80-80) ---
Create tables if absent. Safe to call repeatedly.

--- docstring (lines 101-108) ---
Start a new chat thread; returns the new conversation id.

    Low-level primitive — raises ``sqlite3.IntegrityError`` if a
    conversation for this exact (student, subject, topic) already exists
    (see the UNIQUE constraint in ``_SCHEMA``). Most callers want
    ``get_or_create_conversation`` instead; this is kept as-is for tests
    and any caller that specifically wants "create, fail if present."

--- docstring (lines 122-132) ---
Return (id, created) for the (student, subject, topic) thread,
    creating it if it doesn't exist yet. This is the entry point the UI
    actually uses — every topic in the fixed taxonomy is clickable
    immediately, with no separate "New Chat" step; clicking a topic just
    resolves to its one continuous thread. See the module docstring.

    ``created`` tells the caller whether to kick off the opening
    diagnostic question (``tutor/chat_session.py::start_diagnostic``) —
    only on a genuine first creation, never on a re-fetch of an existing
    thread.

--- docstring (lines 151-154) ---
Update a conversation's diagnostic round progress. ``status`` must
    be 'pending' or 'done' — see the module docstring's DESIGN DECISION
    on the diagnostic mechanism and tutor/diagnostic.py.

--- docstring (lines 166-168) ---
Start a fresh diagnostic round on an EXISTING thread (the "Re-check
    my understanding" action) — appended to the same conversation, not a
    new one, per the one-thread-per-topic decision.

--- docstring (lines 183-189) ---
All distinct student_ids that have ever started a conversation,
    sorted. This is the only honest source of "known students" in the
    system — there is no login/registry (see api/main.py's module
    docstring) — used to power the frontend's searchable student picker
    (see components/StudentSelect). A student typing a brand-new id is
    still valid and expected; this just lists who's been seen before.

--- docstring (lines 200-200) ---
Most-recently-updated first — matches a Claude-Projects-style chat list.

--- docstring (lines 220-220) ---
Append one turn; returns the new message id.

--- docstring (lines 239-239) ---
Full history for a conversation, oldest first.

--- docstring (lines 251-251) ---
Bounded window of the most recent turns, returned oldest-first (chronological).


================================================================================
FILE: stage3/ingest.py
================================================================================
--- docstring (lines 1-11) ---
CLI entry point: ingest a source into the curriculum knowledge base.

PROVENANCE — KEPT (adapted) from AI_IT_Helpdesk's ingest module, including
the trust pre-seeding step (writes a baseline ``kb_score`` and zeroed
feedback counters into every chunk's metadata at ingest time — read back
by the retriever's reranker). See docs/design/FINDINGS_AND_DECISIONS.md
for the reasoning behind the provenance tier ordering below.

Usage:
    python -m stage3.ingest --source curriculum_docs

L21: # ---------------------------------------------------------------------------
L22: # Provenance trust pre-seeding — see FINDINGS_AND_DECISIONS.md §3
L23: # ---------------------------------------------------------------------------
L29: (inline, after `"third_party_education_platform": 2.0,`) # Isaac Science, Ada CS
L72: (inline, after `if __name__ == "__main__":`) # pragma: no cover

================================================================================
FILE: stage3/llm/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/llm/client.py
================================================================================
--- docstring (lines 1-22) ---
Provider-neutral LLM client.

PROVENANCE — pattern KEPT from AI_IT_Helpdesk (the retry-with-backoff loop
and "vendor specifics stay inside the wrapper" rule); the concrete Gemini
binding was not carried over — the helpdesk had two parallel LLM call
paths using two different Google SDKs, collapsed here to one abstract
interface.

``NullLLM`` exists so the whole pipeline can be exercised offline — wiring
tests, prompt inspection, expert-review dry runs — without an API key or
any network call.

Provider: Google AI Studio / Gemini (``GeminiLLM`` below), via the current
``google-genai`` SDK. Model is configurable (``LLM_MODEL``, default
``gemini-flash-latest``) rather than hard-coded.

``generate`` raises ``LLMGenerationError`` on hard failure rather than
returning ``""`` — see docs/design/FINDINGS_AND_DECISIONS.md §7 for why.
Temperature is 0.2 (``config.py``); see the same section for the
reasoning. See docs/TODO.md for known operational gotchas: free-tier rate
limits, pinned-model-ID 404s, and token-count accounting.

--- docstring (lines 37-44) ---
Raised by ``LLMClient.generate`` when every retry attempt failed.

    Deliberately a hard failure, not a silent "". Callers should let this
    propagate past any persistence step (storing a message, advancing
    diagnostic progress, logging an interaction) so a failed turn never
    gets recorded as if it succeeded. ``api/chat.py`` is where it's
    finally caught and turned into a client-facing error response.

--- docstring (lines 48-48) ---
All agents call ``generate``; vendor specifics stay in subclasses.

--- docstring (lines 52-52) ---
Single un-retried provider call. Implement per provider.

--- docstring (lines 56-57) ---
Retry wrapper. Raises ``LLMGenerationError`` on hard failure
        after retries.

L67: # A call that raised nothing but still came back empty is
L68: # just as unusable as one that raised — treat it the same
L69: # way (retry, then eventually raise), not as quiet success.
L75: (inline, after `except Exception as e:`) # pragma: no cover
--- docstring (lines 90-90) ---
Offline stand-in: echoes a canned response. No network, no key.

--- docstring (lines 101-106) ---
Google AI Studio (Gemini API) client, via the ``google-genai`` SDK.

    Import is lazy (inside __init__, not module-level) so that the
    NullLLM/offline path — used by tests and anyone without a key — never
    requires ``google-genai`` to be installed at all.

--- docstring (lines 148-148) ---
Factory keyed on config. Extend as concrete clients are added.


================================================================================
FILE: stage3/profiles/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/profiles/stage1_loader.py
================================================================================
--- docstring (lines 1-36) ---
Loader for the Stage 1 learner-profile export.

PROVENANCE — NEW. No helpdesk equivalent; the third context source in the
Stage 3 design alongside curriculum retrieval and knowledge state.

Real schema: a synthetic fixture matching the user's own Stage 1
pipeline's output, committed at
``data/stage1/stage1_profiles.synthetic.csv`` (the real runtime default
path, ``stage1_profiles.csv``, stays gitignored — copy the fixture into
place to exercise this locally). Real, non-synthetic Stage 1 data is
deliberately not being pursued — see
docs/design/FINDINGS_AND_DECISIONS.md §5.

SCHEMA: one row per (student_id, subject) — a student can appear multiple
times, once per subject Stage 1 has a record for. Two coarse-category
fields, not raw scores:

    flag_status      "none" | "provisional" | "confirmed"
    attainment_band  "well_below" | "below" | "in_line" | "above"

These serve genuinely different purposes downstream, not redundant with
each other:
    - ``flag_status``      -> ``tutor/context_builder.py::profile_to_note``
                              (a one-time pedagogical note, diagnostic-
                              opening only).
    - ``attainment_band``  -> ``tutor/context_builder.py::
                              attainment_band_to_prior`` (a numeric
                              mastery seed — see
                              student_state/store.py::seed_mastery_prior).

Only ``scaffolding_note`` — a short, coarse text string — is ever allowed
to reach an LLM prompt (see ``tutor/prompt_template.py``'s
``ALLOWED_PROFILE_FIELDS`` guard, enforced at runtime). ``attainment_band``
never reaches the LLM as text; it only ever becomes a float written to the
mastery table.

--- docstring (lines 50-55) ---
Load the Stage 1 export into {student_id: {subject: profile_row}}.

    Nested by subject because the real export is one row per
    (student_id, subject) — a student with records in two subjects
    appears as two rows, not one row with a list field.

--- docstring (lines 78-79) ---
Explicit lookup — returns None for an unknown student or a known
    student with no record in this specific subject.


================================================================================
FILE: stage3/redaction.py
================================================================================
--- docstring (lines 1-33) ---
Shared redaction gate for any student-authored text reaching an LLM.

PROVENANCE — NEW (relocated from a Stage-2-only gate in
``stage2_bridge/intake.py``; generalised because typed chat input needs
the same privacy boundary as Stage 2 OCR output).

FAIL-CLOSED BY DESIGN: unredacted student text must never reach a cloud
LLM via any path. Three detection layers run independently against the
original text and are merged as spans (never sequentially, so one layer's
output can't confuse another — see ``_merge_spans``), plus one allowlist
override:

    A. Known-names register (exact match, ``data/redaction/known_names.txt``,
       gitignored) — avoids false-positiving on STEM vocabulary the way a
       blind "strip capitalised words" heuristic would.
    B. Structured PII regex: email addresses, UK phone numbers.
    C. Local spaCy NER (PERSON entities), offline — catches names not on
       the register (a friend, an unregistered sibling, an OCR-garbled
       name).
    Allowlist override (``data/redaction/allowed_terms.txt``, committed —
       curriculum vocabulary, not student data) — suppresses redaction of
       listed terms regardless of which layer matched them, so a
       scientist's eponym ("Newton's third law") isn't wrongly redacted by
       Layer C.

Matched spans are replaced with bracketed category placeholders
(``[NAME]``, ``[EMAIL]``, ``[PHONE]``) rather than deleted outright, so
sentence structure stays intact for the tutor LLM to parse.

See docs/design/FINDINGS_AND_DECISIONS.md §4 for the reasoning behind this
design and its documented trade-offs, and docs/TODO.md for open items
(DOB detection, register collisions, phone/email validation).

L47: # ---------------------------------------------------------------------------
L48: # Spans + merge/apply (shared by all layers)
L49: # ---------------------------------------------------------------------------
L56: (inline, after `category: str`) # "NAME" | "EMAIL" | "PHONE"
L60: # Tiebreak for equal-start, equal-length spans. Arbitrary but deterministic.
--- docstring (lines 65-71) ---
Sort by (start, -length) and absorb fully-nested/overlapping spans.

    Sorting longest-first means a wider EMAIL span at the same start
    position absorbs any narrower NAME spans nested inside it (e.g. the
    two halves of an email's local part), instead of both being applied
    and corrupting the match.

L84: # else nxt is fully inside current: drop it
L102: # ---------------------------------------------------------------------------
L103: # Layer A — known-names register
L104: # ---------------------------------------------------------------------------
L106: (inline, after `MIN_TOKEN_LEN = 3`) # drops initials / very short tokens to cut false positives
L123: # Longest-first: re alternation is first-match-wins, so a full name
L124: # must precede its own component tokens at the same position.
L135: # No register yet is a normal early-deployment state, not an
L136: # error; Layers B/C still run.
L145: (inline, after `line = line.split("`) # ", 1)[0].strip()
--- docstring (lines 154-154) ---
``names`` overrides the configured register file (used by tests).

L167: # ---------------------------------------------------------------------------
L168: # Layer B — structured PII regex
L169: # ---------------------------------------------------------------------------
L173: (inline, after `r"(?:\+44\s?7\d{3}|\b07\d{3})[\s-]?\d{3}[\s-]?\d{3`) # UK mobile
L174: (inline, after `r"|(?:\+44\s?|\b0)\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4`) # UK landline (loose)
L184: # ---------------------------------------------------------------------------
L185: # Layer C — local spaCy NER (lazy-loaded)
L186: # ---------------------------------------------------------------------------
L188: (inline, after `_NLP = None`) # module-level cache, populated on first real use
--- docstring (lines 192-193) ---
Lazy import + load, so importing this module never forces a spaCy
    load for code paths that don't call redact().

L201: # Not caught by redact(): a missing model must fail loudly,
L202: # not silently degrade to register+regex-only.
L219: # ---------------------------------------------------------------------------
L220: # Allowlist override
L221: # ---------------------------------------------------------------------------
L233: (inline, after `line = line.split("`) # ", 1)[0].strip()
--- docstring (lines 242-244) ---
Drop any span whose matched text is on the allowlist. Applies to
    every layer, not just NER — protects against register false positives
    too.

L256: # ---------------------------------------------------------------------------
L257: # Public API
L258: # ---------------------------------------------------------------------------
--- docstring (lines 262-268) ---
Redact personal identifiers from student text before any cloud call.

    FAIL-CLOSED BY DESIGN — see module docstring. Do not catch exceptions
    from any layer here (particularly the NER model-missing RuntimeError)
    and fall back to a partial pass; that would be a silent weakening of
    the guarantee this module exists to provide.


================================================================================
FILE: stage3/retriever/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/retriever/search.py
================================================================================
--- docstring (lines 1-22) ---
Vector search with local reranking over the curriculum KB.

PROVENANCE — KEPT (adapted) from AI_IT_Helpdesk. Rather than trusting raw
vector similarity, this over-fetches candidates (top_k * 4) and reranks
with an explicit, tuneable blend:

    rank = (similarity * 0.70 + provenance_trust * 0.25 + feedback * 0.05)
           * time_decay

Both the raw Chroma distance and the adjusted score are retained on every
result, so a reranker-vs-raw-similarity comparison is possible later at no
extra cost. The helpdesk's ticket-source filter is replaced by a
subject/topic/difficulty_tier metadata filter here.

See docs/design/FINDINGS_AND_DECISIONS.md §3 for the weight sanity-check
results and why time-decay is currently inert, and docs/TODO.md for the
open feedback-semantics question and blend-weight tuning study.

``difficulty_tier`` (alongside ``subject``/``topic``) makes foundation-tier
content retrievable on request; it is not wired into an automatic trigger
anywhere yet — see docs/TODO.md.

L31: # ---------------------------------------------------------------------------
L32: # Filters  (ADAPTED)
L33: # ---------------------------------------------------------------------------
--- docstring (lines 40-46) ---
Scope retrieval to a subject (and optionally topic / difficulty_tier).

    ``difficulty_tier`` is "core" | "foundation" — not named `tier`, which
    would collide with the existing `provenance_tier` (trust axis).

    Chroma requires ``$and`` for multiple conditions.

L62: # ---------------------------------------------------------------------------
L63: # Scoring helpers  (KEPT verbatim)
L64: # ---------------------------------------------------------------------------
--- docstring (lines 80-80) ---
Read-time decay of old feedback (floor 0.70).

L94: # Negatives count slightly stronger — conservative by design.
--- docstring (lines 106-110) ---
Blend similarity, provenance trust, feedback and decay.

    ``similarity_search_with_score`` returns a DISTANCE (lower = better);
    it is converted to a similarity-like value via 1 / (1 + distance).

L114: (inline, after `kb_score = _safe_float(meta.get("kb_score"), 0.0)`) # provenance trust
L122: # ---------------------------------------------------------------------------
L123: # Retriever  (KEPT, filter signature adapted)
L124: # ---------------------------------------------------------------------------
--- docstring (lines 127-134) ---
Reranking wrapper around the Chroma store.

    Returns a list of dicts each containing:
        - content     : the chunk text
        - score       : raw Chroma distance   (kept for ablation)
        - rank_score  : adjusted score used for ordering
        - plus all chunk metadata (subject, provenance_tier, doc_id, ...)

L151: # Over-fetch then rerank locally.
--- docstring (lines 176-178) ---
Convenience helper (constructed per call — cheap, and avoids the
    helpdesk's module-level singleton, which instantiated the store on
    import and made testing awkward).


================================================================================
FILE: stage3/stage2_bridge/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/stage2_bridge/intake.py
================================================================================
--- docstring (lines 1-27) ---
Intake for Stage 2 handwriting-recognition output (file-based handoff).

PROVENANCE — NEW. The helpdesk accepted typed text only; this module is
the seam between the MATLAB Stage 2 pipeline and the Stage 3 tutor, via a
file-based handoff.

CONTRACT: MATLAB writes one JSON file per submission into
data/stage2_inbox/ with the shape:

    {
      "submission_id": "SUB-0001",
      "student_id":   "<pseudonymous StudentID>",
      "subject":      "biology",
      "extracted_text": "...",
      "mean_char_confidence": 0.93        # optional
    }

Processed files are moved to data/stage2_archive/ so the inbox only ever
contains unprocessed work.

Stage 2 runs locally precisely so that only redacted extracted text ever
reaches a cloud LLM. ``redact()`` now lives in ``stage3/redaction.py``
(re-exported here for backwards compatibility, since the same gate applies
to typed chat input too, not just Stage 2 output) — see docs/TODO.md for
open items (low-confidence handling, subject validation, malformed-file
handling).

--- docstring (lines 53-53) ---
List unprocessed Stage 2 output files, oldest first.

--- docstring (lines 61-61) ---
Parse and validate one handoff file.

--- docstring (lines 79-79) ---
Move a processed file out of the inbox.


================================================================================
FILE: stage3/student_state/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/student_state/explanation_method.py
================================================================================
--- docstring (lines 1-41) ---
Per-student explanation-method selection — Thompson sampling.

PROVENANCE — NEW. Implements
``docs/design/stage3-explanation-method-design.md``. Supersedes an
earlier plan to key scaffolding off a fixed disability-category lookup
table; see docs/design/FINDINGS_AND_DECISIONS.md §6 for why (SEND Code of
Practice / EEF guidance). The tutor instead tracks, per (student, method),
whether that method has actually worked for that student, and picks a
method each turn accordingly.

Kept as a sibling module to ``student_state/store.py``, sharing the same
SQLite file, but a separate schema — see that module's docstring.

MECHANISM (Thompson sampling, Beta-Bernoulli per (student, method)):
    - Each (student, method, signal_type) pair has a Beta(alpha, beta)
      posterior over "does this method work for this student".
    - Cold start: a student with no data for a method uses that method's
      cohort prior (``method_cohort_prior``), or a uniform ``Beta(1, 1)``
      default if the cohort has no data either.
    - Selection samples one draw per method from its current posterior
      and picks the argmax, not the highest mean — so a method with a
      high mean but few observations still gets picked sometimes
      (exploration), and a mediocre early result isn't permanently
      discarded.

Only ``signal_type="immediate"`` is ever written; ``correct_retention``/
``retention_gap_days`` exist in the schema but stay NULL — see
docs/TODO.md.

One LLM call, not two: the correctness signal is folded into the same
normal-turn call as a trailing marker line, mirroring
``tutor/diagnostic.py``'s ``[[MASTERY_SCORE: x]]`` pattern.
``parse_understanding_marker`` below is that marker's parser; the prompt
side lives in ``tutor/prompt_template.py``, turn-by-turn wiring in
``tutor/chat_session.py``.

No new concept-tracking machinery: the caller passes whatever
``concept_id`` the top retrieved curriculum chunk carries. A subject with
no curriculum content never produces a ``concept_id``, so this is a clean
no-op there.

L57: # Fixed taxonomy — see design doc "Method taxonomy". Deliberately small;
L58: # do not add methods ad hoc without updating the design doc too (more
L59: # categories means less evidence per category per student).
L69: # Short instruction text per method — what actually reaches the prompt
L70: # (see tutor/prompt_template.py's EXPLANATION APPROACH line). Plain
L71: # pedagogy description, not a category label.
L99: # Uniform, deliberately uninformative cold-start prior. Used only when
L100: # neither the student nor the cohort has any data yet for a given method.
--- docstring (lines 158-158) ---
Create tables if absent. Safe to call repeatedly.

--- docstring (lines 170-172) ---
Return this student's (alpha, beta) for (method, signal_type),
    creating it (seeded from the cohort prior, or the uniform default if
    the cohort has no data either) if it doesn't exist yet.

--- docstring (lines 207-212) ---
Thompson sampling: one Beta draw per method, return the argmax.

    ``_rng`` is an injection point for deterministic tests — production
    callers should never pass it (falls back to the module-level
    ``random`` functions, i.e. genuinely random draws).

--- docstring (lines 234-237) ---
Record that ``method`` was used to explain ``concept_id`` this
    turn. ``correct_immediate`` starts NULL — graded by a later call to
    ``record_understanding`` once the student's next answer on the same
    concept comes in. Returns the new interaction id.

--- docstring (lines 252-256) ---
The most recent ungraded interaction for this conversation, or
    None. Scoped to ONE conversation (not the whole student) — a
    deliberate addition beyond the design doc's schema sketch, needed so
    two topic threads for the same student never cross-grade each
    other's pending interactions.

--- docstring (lines 275-277) ---
Close out a pending interaction and update the Beta-Bernoulli
    posterior for (student, method, signal_type). Returns the new
    (alpha, beta).

--- docstring (lines 297-307) ---
Aggregate every GRADED interaction across all students into a
    per-method cohort prior. Manual/periodic (e.g. a weekly batch) —
    there is no scheduler in this project; see module docstring and
    ``__main__`` below for how it's actually invoked.

    Cohort alpha/beta start from the same uniform default as an
    individual student's cold start (``DEFAULT_PRIOR_ALPHA/BETA``), then
    add the summed successes/failures across all students — so a cohort
    with little data stays close to neutral too, not artificially
    confident.

--- docstring (lines 341-347) ---
Split an LLM response into (visible_text, understood).

    ``understood`` is ``None`` if the marker is missing or malformed —
    callers must treat that as "no signal", never guess True/False. Same
    fail-safe-not-fail-crash discipline as
    ``tutor/diagnostic.py::parse_graded_response``.


================================================================================
FILE: stage3/student_state/store.py
================================================================================
--- docstring (lines 1-37) ---
Per-student knowledge state — durable, structured, NOT a vector store.

PROVENANCE — NEW. No helpdesk equivalent; its only "state" was Rasa
session slots that evaporated when a session ended. Stage 3 needs
knowledge state that persists across sessions.

Plain SQLite, not a vector store — knowledge state never needs semantic
search. Students are identified only by the pseudonymous StudentID from
the LAET extract, no names or UPNs.

SCHEMA:
    observations : one row per assessed interaction
                   (student, subject, topic, outcome, timestamp, source)
    mastery      : one row per (student, subject, topic) — the current
                   estimate the tutor reads at prompt-build time

Mastery is seeded and updated by an LLM-graded diagnostic Q&A at the start
of each topic (``tutor/diagnostic.py``, ``tutor/chat_session.py::
start_diagnostic`` / ``_run_diagnostic_answer_turn``), not continuous
grading of ordinary tutoring turns. The student can explicitly trigger a
fresh round later ("Re-check my understanding"). Outcome scale is graded
(0.0/0.5/1.0), not binary. Update rule is EWMA (``ALPHA=0.35``); see
docs/design/FINDINGS_AND_DECISIONS.md §5 for why this over a rolling
window or Bayesian Knowledge Tracing. An unseen (student, subject, topic)
has no ``mastery`` row at all — cold start is an explicit empty state, not
a guessed default.

``seed_mastery_prior`` is a one-time exception to that cold-start rule,
for a student with Stage 1 attainment data — see its own docstring and
FINDINGS_AND_DECISIONS.md §5.

``student_state/explanation_method.py`` is a sibling module sharing this
same SQLite file but kept separate: a genuinely different schema/concern
(Thompson sampling over which teaching method works per student). See
docs/TODO.md for the open mastery-decay and foundation-tier-trigger
questions.

L48: # EWMA smoothing factor for the mastery update rule. Recent evidence
L49: # weighted more than history, but bounded so one data point can't swing
L50: # the estimate wildly.
--- docstring (lines 88-88) ---
Create tables if absent. Safe to call repeatedly.

--- docstring (lines 101-104) ---
Store one observation and update the mastery estimate via EWMA.

    ``outcome`` must be 0.0, 0.5, or 1.0. Returns the new mastery estimate.

--- docstring (lines 151-166) ---
Write an initial mastery estimate BEFORE any real diagnostic
    observation exists, derived from a Stage 1 attainment_band (see
    profiles/stage1_loader.py::attainment_band_to_prior via
    tutor/context_builder.py) — n_obs stays 0 so it's structurally
    distinguishable from a real observation-derived row. Called once, at
    diagnostic start, for a genuinely first-ever round only — see
    tutor/chat_session.py::start_diagnostic.

    NEVER overwrites: a no-op if a row already exists for this (student,
    subject, topic) — this must not be able to clobber real progress.
    The first real ``record_observation`` call after this finds the
    seeded row already present and blends into it via the normal EWMA
    branch (not the cold-start ``new_estimate = outcome`` branch), so
    ``n_obs`` becomes 1 — correctly counting only real observations, the
    seed itself is never counted as one.

--- docstring (lines 182-186) ---
Return current mastery rows for a student (optionally one subject).

    Returns an empty list for unseen students — the explicit cold-start
    state, not a guessed default.


================================================================================
FILE: stage3/taxonomy/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/taxonomy/topics.py
================================================================================
--- docstring (lines 1-14) ---
Controlled subject/topic taxonomy for the tutoring UI.

PROVENANCE — NEW. Supports a Claude-Projects-style UI: subject = project,
topic = chat within that project. Topics are a fixed, curriculum-authored
list per subject; students don't invent topics. These files are
hand-edited directly — no authoring UI yet, see docs/TODO.md.

Expected layout under data/topics/ (one file per subject):

    data/topics/<subject>.json
    e.g. data/topics/biology.json ->
        {"subject": "biology",
         "topics": [{"id": "genetics", "label": "Genetics"}, ...]}

--- docstring (lines 33-33) ---
Return the sorted subject slugs that have a topic file.

--- docstring (lines 41-41) ---
Return the fixed topic list for a subject; [] if the subject is unknown.

--- docstring (lines 56-56) ---
Look up one topic; None if the subject or topic id is unknown.


================================================================================
FILE: stage3/tutor/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/tutor/attribution.py
================================================================================
--- docstring (lines 1-23) ---
Human-readable Creative Commons attribution for curriculum content.

PROVENANCE — NEW. Isaac Science and Ada Computer Science content both
require real attribution and link-back wherever it surfaces in tutor
output — a licensing obligation. Before this, the only "provenance"
exposed anywhere was raw internal ``chunk_doc_ids``.

Shared by ``prompt_template.py`` (normal tutoring turns) and
``diagnostic.py`` (diagnostic turns) so the title-recovery/dedup logic
isn't duplicated.

Licence values: Isaac Science is CC BY 4.0, Ada Computer Science is
CC BY-NC-SA 4.0 — confirmed via headless-browser render; see
docs/design/FINDINGS_AND_DECISIONS.md §2. Attribution is keyed by chunk
``source`` via a hardcoded lookup rather than the chunk's own stored
``licence`` field, so it stays correct regardless of ingest timing.

TITLE RECOVERY: chunk metadata has no dedicated "concept title" field,
only ``section_title`` (e.g. "Carbohydrates" for a concept's intro
section, "Carbohydrates - Monosaccharides" for a sub-section). Splitting
on the separator and taking the first part recovers the plain concept
title without a new metadata field.

L29: # Keyed by the chunk `source` field. NOT derived from the chunk's own
L30: # `licence` field — see module docstring.
--- docstring (lines 46-50) ---
One citation per unique source concept (deduped by ``source_url``),
    sorted by title for deterministic output. Chunks from an unrecognised
    or missing ``source`` are silently skipped — nothing to attribute
    (e.g. a future non-CC source), not an error.


================================================================================
FILE: stage3/tutor/chat_session.py
================================================================================
--- docstring (lines 1-41) ---
Typed-chat turn handler — parallel to, not a replacement for, session.py.

PROVENANCE — NEW. ``tutor/session.py::run_turn`` is file-handoff shaped (it
takes a ``Submission`` produced by the Stage 2 MATLAB bridge) with no
notion of an ongoing conversation. This module adds that: a chat turn
belongs to a persistent ``conversations`` thread (``conversations/
store.py``) keyed by (student, subject, topic), and carries a bounded
window of prior turns into the prompt as ``conversation_history``.

Mastery is updated only through the diagnostic mechanism
(``start_diagnostic`` / ``_run_diagnostic_answer_turn``); normal tutoring
turns never call ``record_observation`` directly — see
``tutor/diagnostic.py``.

Explanation-method selection (``student_state/explanation_method.py``) is
wired into the normal-tutoring branch only. Each normal turn, if the top
retrieved curriculum chunk carries a ``concept_id``, a method is
Thompson-sampled and logged as a pending interaction; if the previous
turn's pending interaction was about the same concept, the same LLM call
also grades whether the student's answer demonstrated understanding (a
trailing ``[[UNDERSTANDING: yes|no]]`` marker, stripped before display).
A subject with no curriculum content never resolves a concept_id, so this
degrades to a no-op there.

A hard LLM failure (``llm/client.py``'s ``LLMGenerationError``) propagates
straight out of every entry point here without this module needing to
check anything — no message gets persisted, no progress advances, for a
turn that never produced an answer. ``api/chat.py`` catches it and turns
it into a 503.

``prompt.attributions`` (``tutor/attribution.py``) is passed to every
``add_message(role="tutor", ...)`` call site, diagnostic turns included.

``start_diagnostic`` optionally takes ``student_id``/``profiles`` and uses
them once, at the one genuinely cold-start moment: a one-time
diagnostic-opening teaching note (``profile_to_note``) and a one-time
mastery prior (``attainment_band_to_prior`` +
``student_state/store.py::seed_mastery_prior``). See
``tutor/context_builder.py``'s docstring for why it lives here and not
the normal-tutoring path.

--- docstring (lines 89-90) ---
Best-effort human-readable label for prompt text — falls back to
    the raw topic id if the taxonomy lookup misses.

--- docstring (lines 103-116) ---
Generate and store the opening question of a diagnostic round.

    Called synchronously right after a conversation is created, or when a
    fresh round is explicitly requested (api/chat.py's /reassess endpoint)
    — the tutor speaks first, with no preceding student message.

    ``student_id``/``profiles`` should only be passed for a genuinely
    first-ever diagnostic round (api/chat.py's ``post_conversation``,
    never ``/reassess``): the one place Stage 1 data is allowed to touch
    anything, a one-time teaching note (``profile_to_note``) and a
    one-time mastery prior (``attainment_band_to_prior`` +
    ``seed_mastery_prior``). Omitted, the default, degrades cleanly to no
    note and no seed.

--- docstring (lines 148-150) ---
Grade the student's answer to the most recently asked diagnostic
    question, then either ask the next one or hand off to normal tutoring.
    See tutor/diagnostic.py's module docstring for the mechanism.

L153: # This round's questions are always the most recent `questions_asked`
L154: # tutor messages — a diagnostic round is contiguous at the tail of the
L155: # thread (never interleaved with normal tutoring), whether this is a
L156: # brand-new thread or a "Re-check my understanding" round appended
L157: # after older tutoring history.
L193: # else: marker was missing/malformed — deliberately not recording a
L194: # guessed observation, see tutor/diagnostic.py::parse_graded_response.
--- docstring (lines 224-240) ---
One chat turn: typed student message in → grounded response out.

    Pipeline: redact → branch on diagnostic phase → (diagnostic: grade +
    next/wrap-up) or (normal: fetch bounded history → build three-source
    context → guarded prompt → LLM) → persist both turns.

    ``diagnostic_status``/``diagnostic_questions_asked`` are the
    conversation's own stored diagnostic progress (see
    conversations/store.py) — defaults assume "not in a diagnostic round"
    for callers that don't track it, but the real API layer always passes
    the conversation's actual values.

    ``topic`` is the conversation's own stored topic (see
    conversations/store.py) — passed through to retrieval so curriculum
    chunks tagged with the matching topic actually surface. See
    tutor/context_builder.py's docstring for the vocabulary-alignment note.

L266: # concept_id comes from the top retrieved chunk; no chunk / no
L267: # concept_id means explanation-method selection is a clean no-op.
L292: # A hard LLM failure raises past this point; see llm/client.py.
L321: # NOT calling student_state.record_observation here (see module docstring).

================================================================================
FILE: stage3/tutor/context_builder.py
================================================================================
--- docstring (lines 1-27) ---
Three-source context fusion — the core new work of Stage 3.

PROVENANCE — NEW. The helpdesk retrieved from one collection and returned
one ranked list. Stage 3 fuses three sources with different semantics:

    1. curriculum content   -> semantic retrieval (reranked; kept layer)
    2. knowledge state      -> structured lookup, not embedding search
    3. Stage 1 profile      -> small structured record, injected directly

Only source 1 is genuinely a retrieval problem; treating 2 and 3 as
retrieval would be the wrong tool.

``summarise_state`` buckets each topic's mastery estimate into one short,
deterministic clause: >=0.75 "secure on", >=0.4 "developing understanding
of", else "still building the basics of".

``profile_to_note`` and ``attainment_band_to_prior`` map a Stage 1 profile
row to prompt/mastery content, but ``build_context`` below never calls
either — see docs/design/FINDINGS_AND_DECISIONS.md §5 for why (this call
site is structurally never a cold-start moment; the real one is
``chat_session.py::start_diagnostic``, which calls both directly). This
function therefore takes no ``profiles`` argument, and ``ContextBundle``
carries no ``profile_note`` field.

See docs/TODO.md for open items: query formulation, top_k/token budget,
and the foundation-tier trigger.

--- docstring (lines 45-45) ---
Compact, deterministic textual summary of mastery rows for the prompt.

L47: (inline, after `return ""`) # cold start: explicit empty, handled by the prompt template
L63: # Coarse, one-time diagnostic-opening tone note per flag_status — called
L64: # from chat_session.py::start_diagnostic, not build_context below. Says
L65: # nothing that would let the tutor signal a gap to the student.
--- docstring (lines 82-86) ---
Map a Stage 1 profile row's ``flag_status`` to the single allowed
    prompt field. Emits only {'scaffolding_note': <coarse text>} or {} —
    ``None`` profile, ``flag_status == "none"``, and any unrecognised
    value all fail closed to {} (no note), never a guess.

L93: # Coarse mastery-prior mapping per attainment_band, chosen to land inside
L94: # summarise_state's own bucket boundaries (0.4 / 0.75) so a seeded
L95: # estimate reads consistently with the rest of the mastery scale. See
L96: # student_state/store.py::seed_mastery_prior for how it gets written and
L97: # fades as real evidence accumulates.
--- docstring (lines 107-112) ---
Map a Stage 1 profile row's ``attainment_band`` to a starting
    mastery estimate. ``None`` for a missing profile or an unrecognised
    band — fail closed to no seed, never a guessed default. Independent
    of ``flag_status`` — attainment data exists (and is used) even for
    students with no flag at all.

--- docstring (lines 125-136) ---
Assemble the curriculum + knowledge-state context for one normal
    tutoring turn.

    ``student_id`` is used only for the knowledge-state lookup; it is
    never placed in the bundle contents.

    ``topic`` should be drawn from the same ``data/topics/<subject>.json``
    vocabulary that curriculum chunks are tagged against at ingest time —
    an arbitrary string will just silently match nothing.

    Does not touch Stage 1 profile data — see module docstring.


================================================================================
FILE: stage3/tutor/diagnostic.py
================================================================================
--- docstring (lines 1-39) ---
LLM-graded diagnostic Q&A — the mastery-baseline mechanism.

PROVENANCE — NEW. Implements the mechanism behind
``student_state/store.py::record_observation``: each topic thread opens
with a short Q&A that seeds a real mastery estimate, rather than starting
cold. Kept as its own module rather than folded into
``prompt_template.py`` because it has a genuinely different prompt
contract: the LLM must emit a machine-parseable score marker alongside its
visible reply.

Questions are LLM-generated and LLM-graded, not drawn from real curriculum
question banks — see docs/design/FINDINGS_AND_DECISIONS.md §5 for why
(bespoke interactive widgets with no answer key in the public API).

MECHANISM: ``chat_session.py`` calls ``build_opening_prompt`` once when a
diagnostic round starts. For each of the next ``QUESTION_COUNT`` student
answers, it calls ``build_grading_prompt``, which asks the LLM to grade
the just-given answer and (unless this is the final question) ask the
next one, in a single call. The response ends with a machine-parseable
score marker on its own line, e.g.:

    Good, that's broadly right. Now, can you tell me...
    [[MASTERY_SCORE: 0.5]]

``parse_graded_response`` strips that marker before anything is shown to
the student and extracts the score. If the marker is missing or
malformed, the response is still shown but no score is returned — the
caller must not guess a value and must skip ``record_observation`` for
that turn.

``build_opening_prompt`` accepts an optional ``profile_note`` — the one
genuinely cold-start moment for Stage 1 data, reusing
``prompt_template.py``'s ``_guard``/``ALLOWED_PROFILE_FIELDS`` directly.
See ``tutor/context_builder.py``'s docstring for why it lives here and
not the normal-tutoring path. Not threaded into ``build_grading_prompt``
— the note frames the opening question's tone only.

See docs/TODO.md for open items (non-repeat guarantee, extract length cap).

L53: # How many questions make up one diagnostic round. Kept small — this is
L54: # meant to be a "quick" baseline check, not a real assessment.
L77: (inline, after `attributions: list[dict[str, str]]`) # human-readable CC citations — see attribution.py
--- docstring (lines 101-108) ---
The very first message of a diagnostic round — no prior answer to grade.

    ``profile_note``, when given, may contain only ALLOWED_PROFILE_FIELDS
    (same guard as prompt_template.py's normal-turn path) and renders as
    a TEACHING NOTE line — the one place Stage 1 data is allowed to
    influence a prompt, since this is the genuinely cold-start moment
    (see context_builder.py's module docstring).

--- docstring (lines 146-153) ---
Grade the answer to the most recent question, then either ask the
    next one or (if ``is_final``) wrap up into normal tutoring.

    ``prior_questions`` is every diagnostic question asked so far this
    round (oldest first) — passed so the model doesn't repeat itself.
    ``student_answer`` must already be redaction.redact()-ed, same
    requirement as prompt_template.build_prompt's equivalent parameter.

--- docstring (lines 193-197) ---
Split an LLM diagnostic response into (visible_text, score).

    ``score`` is ``None`` if the marker is missing or malformed — callers
    must treat that as "don't record an observation", not as a 0.0.


================================================================================
FILE: stage3/tutor/prompt_template.py
================================================================================
--- docstring (lines 1-33) ---
Explicit, auditable prompt construction — the privacy boundary in code.

PROVENANCE — NEW, and a deliberate correction of the helpdesk pattern,
which f-stringed its entire raw context dict into the prompt. See
docs/design/FINDINGS_AND_DECISIONS.md §7 for why that was a real privacy
risk for Stage 3 specifically.

DESIGN RULE: every field that reaches the prompt is named in the function
signature below. Nothing is interpolated wholesale. ``_guard`` rejects any
value containing a forbidden key, so a future refactor can't quietly
reintroduce the helpdesk pattern.

``explanation_method`` and ``pending_understanding_check`` wire in
Thompson-sampled explanation-method selection (see
``student_state/explanation_method.py``); the latter asks the LLM to end
its reply with a trailing ``[[UNDERSTANDING: yes|no]]`` marker, parsed by
``student_state.explanation_method.parse_understanding_marker``.

The pedagogy instruction set (``SYSTEM_PROMPT``) and the chunk character
budget (``MAX_CHUNK_CHARS``) are grounded in VanLehn (2011) and calibrated
against real ingested chunk lengths — see FINDINGS_AND_DECISIONS.md §7.

``BuiltPrompt.attributions`` (populated by
``tutor/attribution.py::build_attributions``) carries human-readable CC
citations through to the frontend, replacing a raw dump of internal
``chunk_doc_ids``.

``ALLOWED_PROFILE_FIELDS`` is enforced here but no longer called from this
module's own ``build_prompt`` with a non-empty note — see
``tutor/context_builder.py``'s docstring for why the real Stage 1 signal
moved to ``diagnostic.py::build_opening_prompt`` instead (reusing this
module's ``_guard``/``ALLOWED_PROFILE_FIELDS`` directly).

L43: # Fields that must never appear in prompt inputs. Checked
L44: # case-insensitively as substrings of keys.
L51: (inline, after `"residual",`) # raw Stage 1 model output
L52: (inline, after `"sen",`) # any support-need field
L58: # The only profile-derived content permitted into a prompt. Coarse
L59: # category text, not model internals.
L62: # Conversation history: bounded turn window and the only allowed shape per
L63: # turn, guarded the same way as profile_note/chunks (see DESIGN RULE above).
L69: # Per-chunk character cap for CONTEXT. Calibrated against real ingested
L70: # chunk lengths (observed range 222-6413 chars, median ~1163) so one long
L71: # outlier chunk can't crowd out the rest of the top_k results.
L108: (inline, after `chunk_doc_ids: list[str]`) # provenance — flows to feedback + ShowSources
L109: (inline, after `attributions: list[dict[str, str]]`) # human-readable CC citations — see attribution.py
--- docstring (lines 113-113) ---
Reject forbidden keys anywhere in a prompt-bound mapping.

--- docstring (lines 125-125) ---
Reject forbidden keys or non-allowed fields in any history turn.

--- docstring (lines 147-164) ---
Assemble the tutoring prompt from named fields only.

    - ``redacted_student_text`` MUST have passed redaction.redact() —
      required for ALL student text, typed chat included, not just Stage 2
      OCR output.
    - ``profile_note`` may contain only ALLOWED_PROFILE_FIELDS.
    - ``conversation_history`` may contain only ALLOWED_HISTORY_FIELDS per
      turn (``role``, ``text``); truncated to the last MAX_HISTORY_TURNS.
    - ``explanation_method`` must be one of EXPLANATION_METHODS (see
      student_state/explanation_method.py) or None — renders as an
      EXPLANATION APPROACH instruction line.
    - ``pending_understanding_check``, when given, may contain only
      ALLOWED_UNDERSTANDING_CHECK_FIELDS (``concept_label``) and adds an
      instruction asking the LLM to end its reply with a trailing
      ``[[UNDERSTANDING: yes|no]]`` marker — omitted entirely when None,
      so no marker is ever requested on turns where it wouldn't mean
      anything.

L194: (inline, after `_guard(chunk, f"curriculum_chunk[{i}]")`) # defensive — should be clean

================================================================================
FILE: stage3/tutor/session.py
================================================================================
--- docstring (lines 1-16) ---
Tutoring turn handler for the Stage 2 file-handoff path.

PROVENANCE — NEW; replaces both Rasa and the helpdesk orchestrator. Rasa
(intent classification + story-based dialogue) is the wrong shape for
open tutoring dialogue, where a turn isn't one of a small set of intents;
the orchestrator's raw-context prompt assembly is replaced by the guarded
template in prompt_template.py. What's retained: the answer travels with
the doc IDs that produced it, so provenance can be shown to a reviewer.

Dormant: this is the older, file-handoff-shaped turn handler (takes a
``Submission`` from the Stage 2 MATLAB bridge), parallel to
``tutor/chat_session.py`` (what the live chat UI actually uses). No
conversation-thread concept, no mastery/explanation-method wiring, no
Stage 1 cold-start parity with ``chat_session.py::start_diagnostic``. Not
exercised by any test or live endpoint today — see docs/TODO.md.

--- docstring (lines 37-41) ---
One tutoring turn: Stage 2 submission in -> grounded response out.

    Pipeline: redact -> build curriculum + knowledge-state context ->
    guarded prompt -> LLM.


================================================================================
FILE: stage3/vectordb/__init__.py
================================================================================
(no comments)

================================================================================
FILE: stage3/vectordb/store.py
================================================================================
--- docstring (lines 1-9) ---
Chroma vector store for the curriculum knowledge base.

PROVENANCE — KEPT (lightly adapted) from AI_IT_Helpdesk. ``_stable_doc_id``
and ``_normalize_metadata`` carried over as-is; collection renamed to
"stage3_curriculum" and the persist directory now comes from central
config rather than a hard-coded relative path. See
docs/design/FINDINGS_AND_DECISIONS.md §1 for the reasoning behind what was
kept, and docs/TODO.md for the open feedback-semantics question.

L24: # ---------------------------------------------------------------------------
L25: # Paths / config
L26: # ---------------------------------------------------------------------------
L33: # ---------------------------------------------------------------------------
L34: # Embeddings (local model — see module docstring)
L35: # ---------------------------------------------------------------------------
--- docstring (lines 41-41) ---
Return (and create if needed) the Chroma vector store.

L49: # ---------------------------------------------------------------------------
L50: # Metadata normalisation  (KEPT verbatim)
L51: # ---------------------------------------------------------------------------
--- docstring (lines 54-54) ---
Make metadata safe for Chroma: values must be str/int/float/bool/None.

L68: # ---------------------------------------------------------------------------
L69: # ID helpers  (KEPT verbatim — critical for idempotent re-ingest)
L70: # ---------------------------------------------------------------------------
L81: # ---------------------------------------------------------------------------
L82: # Public API
L83: # ---------------------------------------------------------------------------
--- docstring (lines 86-86) ---
Add chunk dicts ({text, metadata, id?}) to the vector DB.

--- docstring (lines 103-108) ---
Basic similarity search with optional metadata filters.

    NOTE: the tutoring pipeline should normally go through
    stage3/retriever/search.py (which adds reranking); this raw entry point
    is kept for debugging and for the reranker-vs-raw ablation.

L115: # ---------------------------------------------------------------------------
L116: # Feedback counters (KEPT) — see docs/TODO.md for the open semantics question
L117: # ---------------------------------------------------------------------------
--- docstring (lines 129-129) ---
Update feedback counters in Chroma metadata. Returns docs updated.

L134: (inline, after `collection = store._collection`) # underlying chromadb collection
L162: (inline, after `except Exception as e:`) # pragma: no cover

================================================================================
FILE: tests/__init__.py
================================================================================
(no comments)

================================================================================
FILE: tests/test_ada_computer_science_connector.py
================================================================================
--- docstring (lines 1-8) ---
Offline tests for the Ada Computer Science connector's parsing logic.

No network calls — feeds a trimmed-down fixture shaped like the real
"Binary arithmetic" (`number_arithmetic`) concept captured during
connector development (see connectors/ada_computer_science.py's module
docstring). Live behavior (the actual HTTP calls) is verified manually,
not here — same policy as tests/test_isaac_science_connector.py.

L14: # Trimmed but structurally real: a top-level intro (a_level+gcse audience,
L15: # same as the real concept), one accordion with an a_level-only section, a
L16: # gcse-only section, a dual-tagged section, and a Scotland-only section
L17: # (must be dropped, not guessed at).
L153: (inline, after `self.assertEqual(intro["difficulty_tier"], "core")`) # concept audience includes a_level
L217: # CC BY-NC-SA 4.0 confirmed directly via headless-browser
L218: # render 2026-08-16 — see connector docstring "CORRECTED" note.

================================================================================
FILE: tests/test_attribution.py
================================================================================
--- docstring (lines 1-2) ---
Offline tests for tutor/attribution.py — human-readable CC citations.
No LLM/network calls; pure function over chunk dicts.

L98: # Guards against a future connector name change silently breaking
L99: # attribution instead of failing loudly somewhere obvious.

================================================================================
FILE: tests/test_chat_session.py
================================================================================
--- docstring (lines 1-11) ---
Regression coverage for tutor/chat_session.py's run_chat_turn.

Added 2026-08-17 after finding this path was broken: the normal-tutoring
branch called `bundle.profile_note`, a ContextBundle field removed during
the Stage 1 refactor, so every real tutoring turn past the diagnostic
would have raised AttributeError. Nothing caught it because this module
had no test coverage at all. `search_kb` and the LLM client are stubbed
so this stays a fast, offline test; conversations/student-state DBs are
redirected to a temp file per test via CONFIG, matching the db_path
pattern used elsewhere, since chat_session.py doesn't expose one itself.

L53: (inline, after `pass`) # sqlite can briefly hold a file handle open on Windows
L64: (inline, after `"doc_id": "isaac_science:cb_carbohydrates__0`) # 0",

================================================================================
FILE: tests/test_context_builder.py
================================================================================
--- docstring (lines 1-1) ---
Offline tests for context_builder.summarise_state — no retriever/LLM imports.

L106: # A "none" flag still has a usable attainment_band — the two
L107: # fields are deliberately independent (see module docstring).

================================================================================
FILE: tests/test_conversations_store.py
================================================================================
--- docstring (lines 1-1) ---
Offline tests for conversation/message persistence — no vectordb/retriever imports.

L60: # Second conversation for stu-1 (different topic) must not duplicate
L61: # it in the id list.
L79: (inline, after `chunk_doc_ids=["curriculum_docs:maths/spec.md`) # 0"],
L88: (inline, after `self.assertEqual(messages[1]["chunk_doc_ids"], ["c`) # 0"])
L103: (inline, after `chunk_doc_ids=["isaac_science:cb_carbohydrates__0`) # 0"],

================================================================================
FILE: tests/test_diagnostic.py
================================================================================
--- docstring (lines 1-2) ---
Offline tests for tutor/diagnostic.py — prompt builders + score-marker
parsing. No LLM/network calls; prompt builders are pure string assembly.

L18: (inline, after `"doc_id": "isaac_science:cb_carbohydrates__0`) # 0",
L40: (inline, after `self.assertEqual(prompt.chunk_doc_ids, ["isaac_sci`) # 0"])
L188: # "Quick" diagnostic — sanity bound, not a strict business rule.

================================================================================
FILE: tests/test_evaluation_scenarios.py
================================================================================
--- docstring (lines 1-2) ---
Offline tests for evaluation/scenarios.py — the fixed scenario set.
No LLM/network/vectordb calls.

L31: # Catches drift if data/topics/<subject>.json ever changes ids.
L42: # Should not raise — same call run_scenarios.py makes for real.

================================================================================
FILE: tests/test_expert_review.py
================================================================================
--- docstring (lines 1-3) ---
Offline tests for evaluation/expert_review.py — rubric validation,
CSV export/import round-trip, descriptive report generation. No LLM/
network/vectordb calls; uses fake transcript fixtures in a temp dir.

--- docstring (lines 122-122) ---
fill_rows: {(scenario_id, criterion): (rating, comment)}


================================================================================
FILE: tests/test_explanation_method_store.py
================================================================================
--- docstring (lines 1-3) ---
Offline tests for student_state/explanation_method.py — Thompson
sampling, Beta-Bernoulli updates, cohort recompute, marker parsing. No
LLM/network calls.

L78: # Give "analogy" a strong, real track record for this student —
L79: # everything else stays at the neutral Beta(1,1) default.
L95: # Wins big majority (proves the posterior mean matters)...
L97: # ...but not literally every draw (proves exploration survives —
L98: # the whole point of sampling instead of argmax-on-mean).
L242: # Every method gets a row (even at the default), since the function
L243: # writes one row per method in the taxonomy regardless of data.
L289: (inline, after `)`) # never graded

================================================================================
FILE: tests/test_isaac_science_connector.py
================================================================================
--- docstring (lines 1-8) ---
Offline tests for the Isaac Science connector's parsing logic.

No network calls — feeds a trimmed-down fixture shaped like a real
response captured during development (see connectors/isaac_science.py's
module docstring for how that shape was confirmed). Live behavior (the
actual HTTP calls) is verified manually, not here — consistent with
tests/test_smoke.py's own "avoid heavy/networked deps" policy.

L14: # A trimmed-down but structurally real fixture — mirrors the shape of the
L15: # actual "Carbohydrates" A-level Biology concept captured during connector
L16: # development (intro content block + one accordion sub-section + a figure).
L148: (inline, after `self.assertEqual(len(docs), 2)`) # intro + one accordion section
L156: # CC BY 4.0 confirmed directly via headless-browser render
L157: # 2026-08-16 — see connector docstring "CORRECTED" note.
L172: # A trimmed-down but structurally real fixture — mirrors the shape of the
L173: # actual "Acids and Bases" A-level Chemistry concept confirmed live against
L174: # the API during connector development.
L220: # Guards against the two subjects' tag maps bleeding into each
L221: # other after the refactor to a subject-keyed dict.
L224: (inline, after `connector = IsaacScienceConnector()`) # defaults to biology

================================================================================
FILE: tests/test_llm_client.py
================================================================================
--- docstring (lines 1-10) ---
Offline tests for llm/client.py's retry-then-raise contract.

Covers the 2026-08-14 fix: LLMClient.generate() raises LLMGenerationError
on hard failure (after retries) or on a call that keeps succeeding with
no exception but empty content — instead of silently returning "" for
callers to (not) check. See that module's docstring for why this
changed: real call sites weren't checking the old "" contract, so a
failed LLM call was producing a blank tutor message that got persisted
and shown to the student as if it were a real answer.

--- docstring (lines 21-22) ---
Returns/raises a scripted sequence of outcomes, one per call —
    either a string (returned) or an Exception INSTANCE (raised).

--- docstring (lines 37-39) ---
Keeps retries fast and deterministic; restores CONFIG afterward —
    same mutate-then-restore pattern as TestGeminiClientFailsFast in
    test_smoke.py.

L63: (inline, after `self.assertEqual(client.calls, 3)`) # max_retries=2 -> 3 total attempts

================================================================================
FILE: tests/test_redaction.py
================================================================================
--- docstring (lines 1-10) ---
Real, spaCy-backed redaction tests.

Deliberately kept OUT of tests/test_smoke.py, which documents itself as
avoiding heavy-dependency codepaths — this file exercises the full
redact() pipeline including the local NER model and requires
``python -m spacy download en_core_web_sm`` to have been run once.

Run:  python -m pytest tests/test_redaction.py
  or: python -m unittest tests.test_redaction

L76: (inline, after `self.assertNotIn("[NAME]", out)`) # fully absorbed into the EMAIL span
L77: (inline, after `self.assertEqual(out.count("["), 1)`) # exactly one placeholder, no artifact
L80: # The load-bearing test: proves the Newton/eponym problem is
L81: # actually closed by the allowlist, regardless of whether this
L82: # spaCy model happens to tag "Newton" as PERSON or not.
L99: (inline, after `self.assertIn("Newton", out)`) # protected by the allowlist

================================================================================
FILE: tests/test_retriever_search.py
================================================================================
--- docstring (lines 1-14) ---
Unit tests for the pure reranking/filter helpers in retriever/search.py.

Deliberately scoped to the pure, module-level functions only —
``build_metadata_filter``, ``_decay_multiplier``, ``_feedback_bonus``, and
``_adjusted_rank_score`` need no Chroma store and no network access.
``Retriever.search`` itself (which does need a live store) is exercised by
live/manual verification instead, matching this project's existing pattern
of unit-testing pure logic and leaving DB-backed paths to real runs — see
the 2026-08-16 cleanup-pass weight sanity-check recorded in this module's
docstring for that live evidence.

Run:  python -m pytest tests/test_retriever_search.py
  or: python -m unittest tests.test_retriever_search

L103: # Equal counts of each: positives contribute 0.08/each, negatives
L104: # 0.12/each — net should be negative, per the module's "conservative
L105: # by design" comment.
L113: # distance 0.5 -> sim = 1 / 1.5 = 0.6667 (repeating)
L114: # kb_score 2.0, fb_pos=1 fb_neg=0 -> feedback bonus 0.08
L115: # no last_feedback_at -> decay 1.0
L125: # _safe_float's default (9999.0) makes an unparseable raw score
L126: # rank near the bottom rather than crashing or ranking first.

================================================================================
FILE: tests/test_smoke.py
================================================================================
--- docstring (lines 1-12) ---
Smoke tests — wiring only, no vector store, no network, no API key.

Deliberately avoids importing vectordb/retriever modules (they pull in
langchain + sentence-transformers, and the embedding model download is not
something a smoke test should trigger). Those paths get exercised by real
ingest runs instead.

Run:  python -m pytest tests/  (or: python -m unittest discover tests)

Redaction: the register/regex/allowlist layers are covered here (no
spaCy needed); the full NER-backed pipeline is in tests/test_redaction.py.

L21: # The helpdesk config.py raised ValueError on import (mutable
L22: # dataclass defaults). This guards the fix.
L36: (inline, after `self.assertEqual(chunks[0]["id"], "maths/spec.md`) # 0")
L54: (inline, after `profile_note={"sen_status": "K"},`) # must be rejected
L64: (inline, after `{"doc_id": "curriculum_docs:maths/spec.md`) # 0",
L71: (inline, after `self.assertEqual(built.chunk_doc_ids, ["curriculum`) # 0"])
L72: # This fixture chunk has no source/source_url (curriculum_docs.py
L73: # chunks predate the attribution feature) — build_attributions
L74: # should degrade cleanly to no citations, not crash.
L85: (inline, after `"doc_id": "isaac_science:cb_carbohydrates__0`) # 0",
L132: (inline, after `explanation_method="interpretive_dance",`) # not in the taxonomy
L222: # The rendered chunk text itself should not exceed the cap
L223: # (plus the small truncation marker's own length).
--- docstring (lines 242-247) ---
Fast, offline coverage of the non-spaCy layers of redaction.py.

    The full redact() pipeline (register + regex + NER + allowlist) needs
    the spaCy model loaded — that's tests/test_redaction.py, kept separate
    per this file's own no-heavy-deps policy (see module docstring).

L278: # Span over "Newton" (index 0-6), as NER would produce.
L294: # Must fail on the missing key, not on a missing google-genai
L295: # install — the import is lazy specifically so this stays true.

================================================================================
FILE: tests/test_stage1_loader.py
================================================================================
--- docstring (lines 1-1) ---
Offline tests for the Stage 1 profile loader — no network/DB imports.


================================================================================
FILE: tests/test_student_state_store.py
================================================================================
--- docstring (lines 1-1) ---
Offline tests for the mastery update rule (EWMA) — no LLM/network.

L54: # EWMA with alpha=0.35: 0.35*1.0 + 0.65*0.0 = 0.35 — moved toward
L55: # the new outcome, but not all the way (not a simple overwrite).
L130: # Real observation must survive untouched — the seed is a no-op
L131: # once real data exists.
L146: # EWMA branch (row already existed), NOT the cold-start
L147: # new_estimate=outcome branch — alpha=0.35:
L148: # 0.35*1.0 + 0.65*0.15 = 0.4475, not a fresh 1.0.
L151: # n_obs counts only the real observation, not the seed.

================================================================================
FILE: tests/test_taxonomy.py
================================================================================
--- docstring (lines 1-1) ---
Offline tests for the subject/topic taxonomy — no vectordb/retriever imports.


================================================================================
FILE: evaluation/__init__.py
================================================================================
(no comments)

================================================================================
FILE: evaluation/expert_review.py
================================================================================
--- docstring (lines 1-30) ---
Structured expert review capture for Stage 3 evaluation.

PROVENANCE — NEW. No helpdesk equivalent; the helpdesk was never formally
evaluated. Stage 3's evaluation method is structured expert review (a
SENCO reviewer, remote), so the instrument needs to exist in code: fixed
scenarios in, per-criterion ratings out, saved verbatim.

Records are appended as JSONL, one object per (scenario, criterion), so
nothing is overwritten and the raw record can be archived as required by
the Research Data Management review.

``CRITERIA`` below is a working draft, not yet signed off with the
supervisor — see docs/TODO.md. The CSV/JSONL schema is generic (criterion
name + 1-5 + comment), so revising the list is a small edit, not a
tooling rebuild.

The reviewer interface is CSV export/import: ``export_review_csv`` turns a
transcript run (``run_scenarios.py``) into one row per (scenario,
criterion) with rating/comment left blank; ``import_review_csv`` reads it
back, validating each row through ``record_rating``. ``generate_report``
produces the descriptive-only summary.

The scenario set lives in ``scenarios.py``/``scenarios.json``, run via
``run_scenarios.py`` — this module owns the rubric and review capture;
those own the scenario/transcript side.

The reviewer is identified by role only (``reviewer_role``); this file,
``scenarios.json``, and every generated artifact must never contain the
reviewer's actual name.

L44: # Transcript fields carried into every CSV row, for the reviewer's context.
L65: (inline, after `rating: int`) # 1-5 (validate in record_rating)
L67: (inline, after `reviewer_role: str`) # role only — never a name
--- docstring (lines 72-72) ---
Append one rating to the JSONL file. Validates criterion and scale.

L82: # Deliberately NOT imported from run_scenarios.py — that module pulls in
L83: # the vectordb/LLM stack (heavy deps) just to generate transcripts; this
L84: # module stays lightweight (stdlib only) and just needs the path both
L85: # modules already agree on (same directory, same filename).
--- docstring (lines 97-99) ---
One row per (scenario, criterion) — transcript fields repeated on
    every row (safer for spreadsheet use than merged cells). ``rating``
    and ``comment`` are left blank for the reviewer to fill in.

L107: # list fields need flattening for a CSV cell
--- docstring (lines 120-123) ---
Read a filled-in review sheet back in. Rows left with an empty
    ``rating`` are skipped (not every criterion has to be rated) — an
    invalid non-empty rating still raises, via ``record_rating``'s own
    validation, rather than being silently dropped.

--- docstring (lines 143-147) ---
Descriptive-only summary: counts, mean, and range per criterion,
    plus every non-empty comment quoted verbatim against its scenario.
    Deliberately no inferential statistics (no significance claims, no
    p-values, no cross-criterion comparison) — a single reviewer's
    ratings don't support that.

L150: (inline, after `lines = ["`) # Expert review — descriptive summary", ""]
L153: (inline, after `lines.append(f"`) # # {criterion}")

================================================================================
FILE: evaluation/run_scenarios.py
================================================================================
--- docstring (lines 1-23) ---
Generate real, grounded transcripts for the fixed scenario set.

PROVENANCE — NEW. Runs each ``evaluation/scenarios.json`` scenario
through the same building blocks a real tutoring turn uses
(``retriever/search.py::search_kb``, ``tutor/context_builder.py::
summarise_state``, ``tutor/prompt_template.py::build_prompt``,
``llm/client.py``'s ``generate``), so the transcript is real evidence of
what the deployed system produces.

Deliberately does not go through ``tutor/chat_session.py::run_chat_turn``:
that function writes real mastery/Thompson-sampling data keyed to a real
student_id, and scenarios are fixed/synthetic on purpose. See
docs/design/FINDINGS_AND_DECISIONS.md §8 for the full reasoning.

A hard LLM failure (``llm.client.LLMGenerationError``) is allowed to
propagate and abort the run. Transcripts are written incrementally
(flushed after each scenario) so an already-succeeded scenario is never
lost to a later failure. Paced with ``SCENARIO_DELAY_SECONDS`` between
calls — see docs/TODO.md for the Gemini free-tier rate limits this works
around.

Usage:  python -m evaluation.run_scenarios

L42: # Confirmed live: Gemini free tier allows 5 requests/minute for
L43: # gemini-3.7-flash. 15s spacing keeps a clean run at ~4/min, leaving
L44: # headroom for a scenario that needs one internal retry.
L65: (inline, after `answer = llm.generate(prompt.user, system=prompt.s`) # LLMGenerationError propagates
--- docstring (lines 91-97) ---
Run every scenario for real, overwriting ``out_path`` at the start
    (a transcript file is a snapshot of one run, not an accumulating log —
    ``expert_review.py``'s ``review_records.jsonl`` is the append-only
    one), then writing each result as it completes, paced ``delay_seconds``
    apart. If a later scenario fails, everything generated before it is
    already safely on disk.


================================================================================
FILE: evaluation/scenarios.py
================================================================================
--- docstring (lines 1-12) ---
Fixed, reproducible scenario definitions for expert review.

PROVENANCE — NEW. Fixed inputs (synthetic knowledge state, synthetic
profile note) so a review session is reproducible and involves no real
student data.

Data lives in ``scenarios.json`` (plain JSON, hand-editable; this loader
stays thin). ``mastery_rows`` is fed through
``tutor/context_builder.py::summarise_state`` at run time rather than
hand-written as a matching string, so a scenario's "knowledge state" text
can never drift from what the real bucketing logic produces.

--- docstring (lines 36-36) ---
Load the scenario set from ``scenarios.json`` (or ``path``).


================================================================================
FILE: scripts/seed_demo_students.py
================================================================================
--- docstring (lines 1-29) ---
Seed a handful of synthetic demo students for UI walkthroughs.

PROVENANCE — NEW. A fresh clone has no students at all — there's no
login, so the only "known students" the searchable picker or mastery
indicator can show is whoever has actually used the system. This script
gives an examiner (or anyone else) opening a fresh clone something to
click through immediately.

Fabricated, synthetic demo data, for UI walkthrough only. Every student id
uses the ``demo-`` prefix so it's never mistaken for a real student, and
every observation uses ``source="demo_seed"`` (reusing the existing
`source` column rather than inventing a parallel one). Not dissertation
evidence, and never conflated with the real scenario runner in
``evaluation/``.

Does not call the live LLM: zero quota cost, deterministic, fast. Instead
this calls the same real store functions a live turn would
(``get_or_create_conversation``, ``add_message``,
``set_diagnostic_progress``, ``record_observation``) with synthetic
inputs, so the seeded rows are produced by the real persistence layer.
Each seeded topic's tutor message also attaches real citations via
``retriever/search.py::search_kb`` + ``tutor/attribution.py::
build_attributions`` (offline/local, no network call beyond the
already-ingested local vectordb).

Usage (from repo root, with requirements installed):
    python scripts/seed_demo_students.py
    python scripts/seed_demo_students.py --reset   # wipe demo-* rows first

L37: # Self-contained: put the repo root on sys.path rather than requiring
L38: # `-m scripts.seed_demo_students` package invocation.
L41: (inline, after `from stage3.conversations.store import (`) # noqa: E402
L47: (inline, after `from stage3.student_state.store import (`) # noqa: E402
L51: (inline, after `from stage3.taxonomy.topics import get_topic`) # noqa: E402
L55: # student_id -> subject -> topic_id -> sequence of outcomes fed through
L56: # record_observation in order (EWMA, alpha=0.35). Varied per student so
L57: # the picker/dashboard has something to look at: student-1 strong in
L58: # biology, weak in CS, chemistry untouched; student-2 balanced across all
L59: # three; student-3 just started. Between them, all four MasteryBar states
L60: # (no data / low / mixed / high) are demoable.
--- docstring (lines 84-85) ---
Delete only demo-* rows, from both DBs. Scoped by the id prefix —
    never touches real data.

--- docstring (lines 109-113) ---
Real citations for a demo message, via the real (local, offline)
    retrieval + attribution pipeline — no LLM call. Fails soft (empty
    list) if the vectordb isn't populated yet (e.g. curriculum hasn't
    been ingested on this clone) — a demo message with no citations is
    fine, a crash isn't.

L120: (inline, after `except Exception as e:`) # pragma: no cover - environment-dependent
L143: # Already seeded by a previous run — idempotent no-op.
L163: # Diagnostic already "done" — clicking this topic in the UI
L164: # goes straight to normal tutoring, not a fresh diagnostic.
