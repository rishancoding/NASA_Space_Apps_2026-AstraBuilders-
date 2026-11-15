# AI-assisted development disclosure

Draft factual disclosure for the project's description and AI/SI-use field.
The team should verify it against its final implementation and add any other
tools it uses. This document does not attest to the origin of the team's idea.

OpenAI Codex assisted with interpreting the team's supplied plan, locating and
checking NASA PSI resources, writing data-download and processing scripts,
transcribing selected NASA report tables, reviewing experimental notes,
annotating test and stage outcomes, producing tests and documentation, and
auditing model readiness. Code, annotation files and processing metadata record
this assistance. Numeric transformations and data checks are performed by
reproducible Python code.

NASA experimental measurements and research text retain their original source
references. AI-produced outcome interpretations are derived annotations, not
NASA-supplied ground-truth labels or human scientific approvals. Some outcomes
and conditions remain unresolved. The source files are not replaced with
generated measurements. The ground-report transcription should be credited as
AI-assisted transcription checked against the cited NASA tables.

As of Steps 1–2, no predictive model has been trained, no generated imagery or
audio has been included in the project, and no chatbot API has been implemented.
The repository records the sources and open-source processing dependencies.

After Steps 1–2, Anthropic's Claude (via Claude Code) assisted with writing the
model training script (`model/train_flex.py`), the backend API (`api/`), its tests
and the API documentation. The research-assistant chat calls a language model at run
time (DeepSeek-V4.1-Flash by default, or Claude): the model chooses which backend
function to call and writes the explanation, while the tools supply numerical results from NASA data or trained models. Generated explanations still need source checking.

Before submission, the team must accurately describe its own concept-development
contribution, follow the official restrictions on AI-originated ideas and NASA
branding, and disclose any later model, chatbot, writing, image or video assistance.

OpenAI Codex also assisted with correcting joint input-coverage checks, separating solid-event protocols, revising unsupported scientific wording, implementing and testing independent grouped interval calibration, and redesigning the repository web UI. No generated imagery or audio was added in that work.

Outcome-label verification was subsequently recorded by the project team in `data/annotations/team_verification.json`; this does not make the derived labels NASA certification. Codex assisted with choosing the official React/FastAPI entry point, synchronizing packaged database provenance, sharing input-domain checks with the experimental app, and adding assistant/tool failure tests. Live external AI-provider testing was omitted at the project owner's request; offline tests simulate provider responses and execute the local data tools.
