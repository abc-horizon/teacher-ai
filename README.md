# BTEC AI Assessment Assistant

This is the official repository for the BTEC AI Assessment Assistant project.

## Status

Project skeleton only (Task T0.2). No application functionality has been
implemented yet.

## Project structure

```
app/
  main.py          # application entry point (placeholder)
  models.py        # data models (placeholder)
  moodle_api.py    # Moodle API integration (placeholder)
  extractor/       # document/content extraction (empty)
  grading/         # grading logic (empty)
  rag/             # retrieval-augmented generation logic (empty)
portal/            # user-facing portal (empty)
prompts/           # prompt templates (empty)
queries/           # stored queries (empty)
references/        # reference materials (empty)
sample_data/       # non-sensitive sample data (empty)
scripts/           # utility/dev scripts (empty)
tests/             # test suite (empty)
docs/              # project documentation (empty)
```

## Setup

Copy `.env.example` to `.env` and fill in local values. Never commit a real
`.env` file or real credentials.

Dependencies are not yet defined; `requirements.txt` will be populated in a
later task.

## Running

Run these from the project root after activating the virtual environment
(`.venv`):

```
uvicorn app.main:app --reload
streamlit run portal/Home.py
```
