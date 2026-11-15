# Step 1 — competition-wide requirements

Checked November 14, 2026 against the official 2026 pages below. Location-specific
logistics are intentionally deferred at the user's request. This is a project
requirements review, not confirmation of account registration or final award eligibility.

**Result:** no published project-format restriction was identified that prevents
continuing this NASA-data dashboard and its disclosed AI-assisted development.
Step 2 may proceed. Original concept ownership and final submission declarations
must be confirmed by the team; they cannot be established from repository files.

## Official sources

- [Flame in Freefall challenge](https://www.spaceappschallenge.org/2026/challenges/flame-in-freefall/)
- [2026 Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/)
- [2026 Judging and Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide/)
- [Participant FAQs](https://www.spaceappschallenge.org/resources/participant-faqs/)
- [Participant terms](https://www.spaceappschallenge.org/legal/)

The official pages' full text was retrieved directly, including the site's
embedded content, because the browsing tool intermittently returned HTTP 502.
Old guides and local-event pages were not treated as current global rules.

## Challenge fit

The objective is an interactive dashboard that summarizes, ranks and interprets
combustion investigations. PSI is the stated source, with BASS, Saffire, FLEX and
smoke studies directly relevant. Predictive modeling is an optional direction,
not a requirement to produce a generic material-safety classifier. Evidence
relevance ranking can meet the ranking objective without a safety certification.

The repository contains the PSI investigations and NASA report references.
The dashboard, ranking interface, research assistant and final demo remain
future implementation steps. The current data package alone is not the finished
interactive deliverable. Partial-gravity predictions are not established by the
available microgravity observations.

## Submission restrictions to carry into the implementation

From the **Project Submission Guide**:

- Use NASA data/resources and describe that use; list external code, data, text and image sources.
- Provide public demo and final-project links that require no login or permission.
- Demo limit: 30 seconds of video **or** seven slides total, including introductory slides.
- Use English in submission materials; a non-English demo video needs English subtitles.
- Disclose AI/SI assistance, including code/data in descriptions and metadata.
- AI tools may assist development; the guide says they should not originate the solution idea.
- Mark generated audiovisual content as instructed; do not generate or modify NASA branding with AI.
- Demo/project materials must not include under-18 participants' likenesses or audio.
- Complete required fields and declarations, then actually submit for judging; saving progress is insufficient.

The official general closing time is November 15, 2026 at 11:59 p.m. in the
registered event's timezone, or the Team Owner's residence timezone for the
Universal Event. Earlier local judging cutoffs are possible and remain outside
this review's scope.

From the **Judging and Awards Guide / FAQ**: teammates must be accepted into the
same event, appear on the team page, and respect the six-member maximum. Local
teams may have one or more members; Universal teams require at least two for
global judging. Work must be original and sources credited. The team must check
the remaining participant terms and any eligibility declarations itself.

## Implementation implications

Use a seven-slide English demo as the low-effort default; a compliant video is
also possible. Preserve direct NASA citations and AI-label provenance in the UI
and exports. Keep model predictions distinguishable from NASA measurements.
Do not call the prototype NASA-approved or claim fire-safety certification.
Published judging criteria include impact, creativity, validity, relevance and
presentation; unsupported scientific claims would weaken validity.

See [AI_USE.md](AI_USE.md) for a factual disclosure of the work already done.
No registration declarations were made and nothing was submitted to the competition.

Implementation status, November 15: the React/FastAPI dashboard, models, explorer and assistant tool wiring now exist; the earlier implementation notes above record the Step 1 review. The official launch path and current limitations are in the root README. Live AI-provider testing was omitted in the current local check at the project owner's request. No public deployment or competition submission was performed in this work.
