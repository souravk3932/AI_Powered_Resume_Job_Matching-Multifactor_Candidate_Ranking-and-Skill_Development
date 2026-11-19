# Updated Phase 0 Plan (v2) — with Multiple Resume Comparison & Recommendation

Status: PLAN ONLY. Nothing from this feature is implemented yet.
Nothing from the original blueprint has been removed; this version only adds to it.

---

## 1. Updated introduction and objectives

**English.** The system is a student-only web platform that (a) checks how well a resume fits a job description (JD),
(b) explains the score, (c) shows skill gaps, (d) offers an OPTIONAL learning roadmap, (e) verifies skills through
assessments and (f) recalculates the score. **New:** if a student has several resume versions, the system analyses
each one against the same JD, compares them fairly, and recommends the most suitable one with reasons. The student
can always override the recommendation.

**Hinglish.** Ye sirf students ke liye website hai. Pehle jaisa: resume aur JD match karo, score samjhao, skill gap
batao, optional roadmap do, assessment lo, score dobara nikalo. **Naya:** agar student ke paas kai resumes hain, to
system har resume ko same JD se compare karega, fair tarike se rank karega aur batayega kaun sa resume best hai aur
kyun. Student chahe to koi bhi resume khud choose kar sakta hai.

### Objectives (original 20 kept; 6 added)
21. Support two modes: Single Resume Analysis and Multiple Resume Comparison.
22. Keep resume versions immutable and independent (a new upload = a new version).
23. Analyse every resume against the same JD with the same rules, weights and pipeline.
24. Produce a comparison report: scores, strengths, weaknesses, evidence, ranking.
25. Recommend a best resume *for that specific JD*, with an explanation the student can audit.
26. Let the student pick any resume and continue into gaps → roadmap → assessment → recalculation.

---

## 2. Updated architecture

| Layer | Technology | Role in the new feature |
|---|---|---|
| Frontend | React + Tailwind + Recharts | Mode chooser, resume picker, comparison table, radar/bar charts, "choose this resume" button |
| Backend | Node + Express | The ONLY gate to data. Auth, ownership checks, saving, orchestration, calls AI service |
| AI service | Python + FastAPI | Extraction, matching, scoring engine, comparison engine. Private: accepts calls only from backend |
| LLM | Configurable provider behind one wrapper | Contextual extraction, relevance interpretation, explanations. Never decides scores |
| MCP server | MCP SDK (separate process) | Controlled tools for AI assistants; calls the BACKEND API with the student's own token |
| Data | MongoDB + file storage | Immutable resume versions, independent analyses, comparisons, audit log |

**Restaurant analogy (Hinglish).** Manager (Node) ke bina kisi ko godown (MongoDB) ya kitchen (Python) tak access
nahi. MCP "service window" hai: wo bhi manager se hi baat karta hai, seedha godown se nahi. LLM salahkaar hai: wo
bata sakta hai "ye project relevant lagta hai", par final marks calculator (scoring engine) deta hai.

```
 React ──► Node/Express ──► Python AI service ──► LLM wrapper ──► provider
              │  ▲               │ (scoring engine = pure maths)
              ▼  │               ▼
          MongoDB / files   structured JSON back (validated)
              ▲
 AI assistant ► MCP server ──(student's JWT)──► Node/Express  (never direct DB/AI access)
```

### Golden rules (apply everywhere)
1. LLM output is a *claim*, never a score and never verified evidence.
2. Scores come only from the deterministic scoring engine.
3. Every extracted claim must carry a source quote that exists in the resume text (checked by code).
4. Missing = "Not provided", never "lacks".
5. Everything written is a new record; nothing is overwritten.

---

## 3. Updated workflow

```
Register/Login → Add JD → choose mode
   ├─ A) SINGLE:   pick/upload 1 resume ─┐
   └─ B) MULTIPLE: pick/upload 2–5 resumes ─┤  (single mode = the same pipeline with N = 1)
                                            ▼
   For each resume version (independent):
     text → sections → LLM extraction (cached per resume version, JD-independent)
          → validation (quote check, schema) → skill matching vs JD
          → LLM relevance interpretation (projects/funding vs JD) → validation
          → SCORING ENGINE (role weights) → analysis record saved
                                            ▼
   B only: comparison engine → ranking → LLM explanation (constrained to engine numbers)
          → comparison record → student sees report → student selects a resume (any)
                                            ▼
   Skill gaps → OPTIONAL roadmap (follow / learn externally / skip)
          → assessment → proficiency saved (verified) → recalculate (new score snapshot)
          → updated report → apply with chosen resume → history saved
```

**Hinglish.** Single mode matlab "1 resume ki comparison" — wahi pipeline, isliye dono modes ka code same rahega.
Multiple mode mein har resume alag se analyse hota hai, phir sab ko ek table mein rakh kar rank kiya jata hai.

---

## 4. Database design (MongoDB collections)

Relationships: `student 1—n resumes 1—n resume_versions`; `analysis = (student, resume_version, jd)`;
`comparison 1—n analyses`.

| Collection | Key fields |
|---|---|
| `students` | _id, name, email, passwordHash, profile |
| `resumes` | _id, studentId, name (e.g. "Full Stack"), targetRole?, createdAt, currentVersionNo |
| `resume_versions` | _id, resumeId, studentId, versionNo, filePath, fileHash, uploadedAt, extractedText, extraction {skills, education, experience, projects, certifications, achievements, funding}, claimStatus per item, extractorVersion |
| `job_descriptions` | _id, studentId, title, organization?, source (pdf/text), text, fileHash, requirements {...}, createdAt |
| `analyses` | _id, studentId, jdId, resumeId, resumeVersionId, versionNo, roleProfileId + weightsSnapshot, profileSnapshot, skillMatch {matched, partial, missing}, evidence[], factorScores[{factor, score, weight, contribution, evidenceStatus}], projectEval[], achievementEval[], fundingEval[], overallScore, scoreSnapshots[] (append-only: initial, after_assessment…), assessmentIds[], roadmapId?, status, engineVersion, llmModel, createdAt |
| `comparisons` | _id, studentId, jdId, resumeIds[], resumeVersionIds[], analysisIds[], ranking[{analysisId, rank, score, strengths, weaknesses}], closeCall (bool), recommendedResumeId, explanation, selectedResumeId?, selectedAt?, status, createdAt |
| `skill_proficiencies` | studentId, skill, level, source (assessment/self-claimed), assessmentAttemptId, verifiedAt |
| `learning_roadmaps` / `learning_progress` | analysisId, skills[], steps[], choice (follow/external/skip), progress |
| `assessments` / `assessment_attempts` | skill, questions, answers, score, level, attemptNo |
| `role_weight_profiles` | role, weights per factor (versioned, sum = 100) |
| `audit_logs` | actor (student / mcp-tool), action, resource ids, time (no secrets) |

Design choices:
- **Immutability:** editing = upload a new `resume_version`; old analyses keep pointing at the old version.
- **Recalculation** appends to `scoreSnapshots`; the initial score is never edited. History = the snapshots.
- **Weights are snapshotted** in each analysis so later weight changes never rewrite history.
- **Cache key:** `fileHash + extractorVersion` for extraction; `resumeVersionId + jdId + engineVersion + weightsVersion`
  for analysis. Same inputs → same output (consistency, and saves LLM cost).
- All queries filter by `studentId` (ownership).

---

## 5. API design

### Node backend (public, JWT required except auth)
| Area | Endpoints |
|---|---|
| Auth/profile | POST /api/auth/register, /login · GET/PUT /api/profile |
| Resumes | POST /api/resumes (new resume) · POST /api/resumes/:id/versions · GET /api/resumes · GET /api/resumes/:id · PATCH (rename) · DELETE (needs confirm) |
| JDs | POST /api/jds (pdf or text) · GET /api/jds · GET /api/jds/:id · DELETE |
| Analysis | POST /api/analyses {resumeVersionId, jdId} · GET /api/analyses · GET /api/analyses/:id · POST /api/analyses/:id/recalculate |
| Comparison | POST /api/comparisons {jdId, resumeIds[2..5]} · GET /api/comparisons · GET /api/comparisons/:id · POST /api/comparisons/:id/select {resumeId} |
| Gaps/roadmap | GET /api/analyses/:id/gaps · POST /api/analyses/:id/roadmap · PUT /api/roadmaps/:id/choice · PATCH progress |
| Assessment | POST /api/assessments {skill} · POST /api/assessments/:id/attempts · GET results |
| Assistant | POST /api/assistant/ask |

### Python AI service (internal only, shared service key, not exposed to browsers)
`/internal/extract/resume` · `/extract/jd` · `/match` · `/score` · `/compare` · `/gaps` · `/roadmap` ·
`/assessment/generate` · `/assessment/evaluate` · `/explain`. Pure input → output; it does not touch MongoDB.

### MCP tools (final names; tool → backend endpoint)
Your 11 proposed tools are all kept; the original 22 are merged where they overlapped.

| MCP tool | Type | Backend call | Notes |
|---|---|---|---|
| `list_my_resumes`, `get_resume_details` | read | GET /resumes | own data only |
| `analyze_job_description` (+ `get_job_requirements`) | compute+write | POST/GET /jds | |
| `extract_resume_evidence` | compute | POST /analyses (extraction stage) | returns claims + quotes |
| `analyze_resume` | compute+write | POST /analyses | one resume × one JD |
| `calculate_compatibility` | compute | analysis score stage | engine only |
| `identify_skill_gaps` | read | GET /analyses/:id/gaps | |
| `compare_resume_versions` | compute+write | POST /comparisons | 2–5 resumes, one JD |
| `recommend_best_resume` | read | GET /comparisons/:id | returns engine ranking + explanation |
| `get_comparison_report` | read | GET /comparisons/:id | |
| `select_resume_for_job` | write | POST /comparisons/:id/select | needs explicit confirmation |
| `generate_learning_roadmap` (+ `get_learning_resources`, `update_learning_progress`) | compute/write | roadmap endpoints | |
| `generate_skill_assessment`, `evaluate_skill_assessment`, `determine_skill_proficiency` | compute/write | assessment endpoints | |
| `recalculate_compatibility` | compute+write | POST /analyses/:id/recalculate | appends snapshot |
| `get_analysis_history`, `get_student_profile` | read | GET | no password/token fields |

MCP rules: every tool call carries the student's token; strict input schemas (ids, max 5 resumes); delete/overwrite-type
tools need `confirm: true`; no file-system or raw DB tools; each call written to `audit_logs`; rate limits.

---

## 6. Updated phase-wise roadmap (Phases 8+ renumbered)

| Phase | Content | Where the new feature appears |
|---|---|---|
| 0 | Planning (this document) | design of everything |
| 1 | Setup: frontend, backend, AI service, MongoDB (in progress: backend + DB code done) | |
| 2 | Student auth and profile | ownership model (`studentId` everywhere) |
| 3 | Multiple resume management | **resumes + immutable `resume_versions`, hashing** |
| 4 | JD management | JD chosen before mode |
| 5 | Document extraction and structured data | **first small LLM wrapper**; quote-validation; per-version extraction cache |
| 6 | Skill extraction and semantic matching | runs per resume version |
| 7 | Multi-factor evaluation | **funding/project relevance evaluation, evidence statuses, dedup ledger**; engine used by both modes |
| **8 (new)** | **Multiple Resume Comparison and Recommendation** | comparison engine, ranking, tie/close-call rule, report, selection, `comparisons` collection, single mode = N=1 |
| 9 | Skill gap + optional roadmap (was 8) | works on the selected resume's analysis |
| 10 | Skill assessment engine (was 9) | |
| 11 | Recalculation and progress tracking (was 10) | score snapshots |
| 12 | LLM integration and AI assistant (was 11) | consolidation; comparison explanations, Q&A, hallucination tests |
| 13 | MCP server (was 12) | all tools above incl. comparison tools |
| 14 | Frontend dashboard and integration (was 13) | mode chooser, comparison page, charts |
| 15 | Testing, security, finalization (was 14) | fairness + ownership + MCP tests |

Rule unchanged: one phase at a time, your approval before the next.

---

## 7. How existing features connect to the new one

- **Resume management (Ph3)** supplies versions; comparison picks 2–5 of them.
- **JD extraction (Ph4–5)** gives one shared requirement set for all resumes.
- **Skill matching (Ph6)** and **multi-factor engine (Ph7)** are reused unchanged for each resume; comparison adds nothing to scoring rules.
- **Gap / roadmap / assessment / recalculation (Ph9–11)** start from whichever resume the student selects (recommended or not).
- **Dashboard** shows analyses *and* comparisons; **history** keeps both.
- **LLM and MCP** are used by both modes; the MCP comparison tools simply call the same backend endpoints as the UI.

---

## 8. Technical flow: many resumes vs. one JD

1. Backend checks ownership of the JD and every resume version; limit 2–5; creates a `comparison` (status `running`).
2. For each version, reuse cached extraction or run: PDF text → sections → remove personal identifiers (name, photo, gender,
   age, address) from what goes to the LLM/engine → LLM structured extraction → Pydantic validation → quote check
   (claim text must appear in resume) → items failing checks become `needs_review`, not facts.
3. Match skills vs the JD (alias catalogue + Sentence Transformer cosine similarity + thresholds → matched / partial / missing).
4. LLM relevance step per project/experience/funding item: returns `{relevance 0–3, role_of_candidate, outcome, reasoning, quote}` validated.
   The engine converts these into numbers with fixed rules; the LLM score-like words are inputs, not final marks.
5. Scoring engine with the JD's role weights (same weights for all resumes) → factor scores → overall; saves an `analysis` per resume.
6. Comparison engine: rank by overall score. If top two differ by less than a margin (e.g. 3 points), mark `closeCall` and say so.
   Per-factor differences give strengths/weaknesses ("Resume B leads on projects +18, Resume A leads on technical +12").
7. LLM writes the explanation from a JSON of engine results only; a checker confirms every number/resume name it mentions
   matches the data; otherwise a template explanation is used (deterministic fallback).
8. Save comparison; student views, optionally selects a resume (`selectedResumeId`, may differ from recommended).
9. Student continues to gaps → roadmap → assessment on that resume's analysis.

---

## 9. Explainability, evidence, security, fairness

**Explainability:** every factor shows score × weight = contribution; weights snapshot stored; every claim links to a quote;
comparison shows per-factor deltas; engine/LLM/model versions recorded.

**Evidence validation:** statuses `not_provided → claimed → supported (link/document) → verified (assessment or document check)`.
Claims never become "verified" through the LLM. Funding score = relevance × evidence level × student's contribution × outcome;
the amount has at most a tiny capped effect, so ₹2 crore cannot outweigh an irrelevant or unsupported claim. Each achievement is
assigned to ONE primary factor (dedup ledger) to prevent double counting.

**Security:** JWT + `studentId` filter on every query; MCP uses the student's token and talks only to the backend; AI service is
private; file validation (PDF type/size, hash); no arbitrary file or DB tools; secrets only in `.env`; audit log; rate limits;
confirmation for destructive actions; PII minimised before sending text to an LLM provider.

**Fairness:** identical rules and weights for all resumes; sensitive attributes removed from scoring input; "Not provided"
is shown as insufficient evidence and is not scored as zero skill (factor weight is redistributed or flagged per documented rule);
more skills or bigger funding do not auto-win; close calls are disclosed; test: same resume with different names/formatting must score within a small tolerance; the score is never described as hiring probability.

---

## Open decisions for you
1. Maximum resumes per comparison: proposed 5.
2. Close-call margin: proposed 3 points (configurable).
3. LLM provider: decide in Phase 5 (first use), configurable.
