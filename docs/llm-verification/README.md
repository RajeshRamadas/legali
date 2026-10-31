# LLM document verification

Documentation for the LLM features that read and check property documents.

- [requirements.md](requirements.md): what the feature must do, with IDs and status (built / planned).
- [design.md](design.md): how it works and why: models per step, quote grounding, verdict, failure handling, planned accuracy work.
- [implementation.md](implementation.md): what is on `main`, file by file: schemas, stored JSON, API, configuration, limits, tests, known gaps.

The operator guide (setup, workflow, verdict meanings) stays in [../property-verification.md](../property-verification.md),
and the customer document journey in [../document-journey.md](../document-journey.md).
