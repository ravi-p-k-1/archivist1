# Archivist

Archivist turns Google Meet transcripts into reviewable action-item reports.
A capture person's browser captures the meeting and a Cloudflare Worker
(in the companion `cloudroot` repo) opens a pull request here with the raw
transcript. This repo's GitHub Actions workflow then extracts action items
with Claude and commits the result back to the same PR for a human to
review and merge.

## Where this fits

```text
Capture person's Chrome (TranscripTonic extension)
        |  posts JSON when the meeting ends
        v
Cloudflare Worker (cloudroot repo)
        |  opens a PR: cloudflare/<date>-<HHMM> -> main
        v
archivist1  <-- you are here
        |  process-transcripts.yml extracts action items
        v
A person reviews the PR and merges it
```

Setting up the capture extension and the Worker is covered in the
`cloudroot` repo's `transcript-intake/README.md`. This document only covers
the archivist1 side: the workflow that turns a submitted transcript into a
reviewed report.

## How it works

```text
transcripts/<date>/meet/transcript.json   (arrives via a Worker-opened PR)
                  |
                  v
          prepare (Python): validate, build a compact numbered view
                  |
                  v
     claude-code-action: read-only extraction, schema-checked output
                  |
                  v
          verify (Python): check every excerpt against its cited entry
                  |
         (failed?) -- retry once with the error appended to the prompt
                  |
                  v
          finalize (Python): add speaker/time, render, archive
                  |
          +-------+-------+
          |               |
          v               v
output/<date>/<model>/   archived/<date>/meet/
action-items.txt          transcript.json
action-items.json
                  |
                  v
   committed to the PR branch, with a summary comment
```

Claude never edits, pushes, or browses the web. Its tool access is limited
to `Read` and `Bash(python -m archivist check-evidence:*)` — the latter
lets it test an excerpt against the transcript mid-run, before submitting.
Its final answer is schema-checked against `ReportSubmission`'s JSON Schema
(`--json-schema`), and every submitted excerpt is independently re-checked
by Python afterward in `verify`, since a schema-valid excerpt can still be
fabricated or paraphrased rather than copied. If verification fails, the
workflow retries once with the specific failure appended to the prompt; if
the retry also fails, the job ends with a failing check and no commit.

Claude cites a compact-view entry id (`e12`) rather than being shown the
raw JSON or being trusted to copy a speaker/timestamp correctly — `finalize`
fills in the real speaker and timestamp from the cited entry afterward.

## Input contract

- **Path:** `transcripts/<YYYY-MM-DD>/meet/transcript.json`. Exactly one
  pending transcript at a time; the workflow rejects a second one.
- **Shape:** the TranscripTonic "advanced" webhook body, stored as received:
  `webhookBodyType: "advanced"`, `meetingStartTimestamp` and
  `meetingEndTimestamp` (ISO 8601), and a non-empty `transcript` list of
  `{personName, timestamp, transcriptText}` entries. Unknown extra fields
  (such as `chatMessages`) are allowed and ignored.
- **The date in the path must match the meeting.** `meetingStartTimestamp`
  is converted to `America/Los_Angeles`; the folder's `YYYY-MM-DD` must
  equal that date.
- **`prepare` also rejects:** invalid UTF-8 or JSON, a body type other than
  `"advanced"`, an empty transcript, an entry missing a required field or
  with an empty name/text, a non-ISO-8601 timestamp, an end time before the
  start time, and an existing archive at the destination.

Entries are numbered `e1..eN` in transcript order. Each entry's time is
reported as elapsed `HH:MM:SS` from the meeting's start — that's what both
the compact view Claude reads and the evidence lookup key off of.

## Setup

### 1. Add the repository secret

Generate a token locally with a Claude Pro, Max, Team, or Enterprise
subscription:

```powershell
claude setup-token
```

This requires the Claude Code CLI — see the
[install guide](https://code.claude.com/docs/en/setup) if you don't have it.

In GitHub, navigate to:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

Create a secret named `CLAUDE_CODE_OAUTH_TOKEN` and paste the token into
the **Secret** field. It's passed straight through to `claude-code-action`
as `claude_code_oauth_token`. Don't also set a repository-wide
`ANTHROPIC_API_KEY` — check `claude-code-action`'s own docs for its current
token precedence before setting both.

### 2. Repo settings

The workflow declares its own `permissions: { contents: write,
pull-requests: write }`, so no change to **Settings -> Actions -> General
-> Workflow permissions** is required. The workflow never opens a pull
request itself (the Worker does that), so **Allow GitHub Actions to create
and approve pull requests** isn't needed either.

### 3. Trigger a run

In normal operation, the Worker in `cloudroot` opens the PR and the
workflow starts automatically: it triggers on `pull_request` (`opened`,
`reopened`) touching `transcripts/**/transcript.json`, filtered to branches
named `cloudflare/*`.

To reprocess an existing PR by hand — for example after a transient
failure, or while testing without the Worker — open the repository's
**Actions** tab, select **Process transcripts**, choose **Run workflow**,
and give it the PR number. `workflow_dispatch` runs regardless of the
branch name.

The Claude model defaults to the repository variable `ARCHIVIST_MODEL`
(itself defaulting to `sonnet`). Set it under **Settings -> Secrets and
variables -> Actions -> Variables** to switch models without editing the
workflow.

## Successful result

For `transcripts/2026-06-30/meet/transcript.json`, Archivist writes:

```text
output/2026-06-30/sonnet/action-items.txt
output/2026-06-30/sonnet/action-items.json
```

and moves the source transcript to:

```text
archived/2026-06-30/meet/transcript.json
```

If the `2026-06-30/` directory under `transcripts/` is empty after the
move, it's removed; the top-level `transcripts/` directory remains.

The text report contains, per action: the action, owner (or
`Unassigned`), due date (or `Not specified`), a verbatim evidence excerpt,
the speaker, and the elapsed timestamp — followed by decisions and open
questions. All results are committed directly to the PR branch, and a
summary is posted as a PR comment.

## Failure behavior

If the transcript fails validation, both extraction attempts fail
verification, or output writing fails:

- the job ends with a failing check, and nothing is committed;
- the original transcript remains under `transcripts/` for the next run;
- no partial report is published; and
- logs get sanitized, file-and-reason error messages — never the OAuth
  token, the prompt, Claude's raw response, or transcript contents.

Existing reports and archived transcripts are never silently overwritten.
If a report was written but archiving failed, rerunning `finalize` retries
only the archive step without calling Claude again.

## Common errors

Most of these come from `archivist prepare` (the input contract above) or
`archivist verify` (grounding), and appear in that step's log.

| Error | Cause |
| --- | --- |
| `No pending transcript found under transcripts/<date>/meet/transcript.json.` | No matching file, or it's at the wrong path. |
| `Only one pending transcript is supported per run.` | More than one `transcripts/*/meet/transcript.json` exists. |
| `Transcript date must use YYYY-MM-DD.` | The folder name under `transcripts/` isn't a valid ISO date. |
| `Folder date ... does not match the meeting start time in America/Los_Angeles (...)` | The path's date and `meetingStartTimestamp` disagree once converted to Pacific time. |
| `Transcript webhookBodyType must be "advanced".` | The JSON isn't TranscripTonic's advanced body shape. |
| `Transcript must have a non-empty transcript list.` | `transcript` is missing, not a list, or empty. |
| `Transcript entry N is missing <field>.` / `has an empty personName` / `has empty transcriptText` | One entry is malformed. |
| `meetingEndTimestamp must not be before meetingStartTimestamp.` | The two timestamps are out of order. |
| `Archive destination already exists: ...` | That date has already been processed; Archivist refuses to overwrite it. |
| `Action cites unknown entry id: eN.` / `evidence excerpt is absent from entry eN` | Claude's submitted report failed grounding (`verify`); this triggers the one automatic retry. |
| `Model must be a filesystem-safe lowercase name...` | `ARCHIVIST_MODEL` contains uppercase letters, spaces, or other unsafe characters. |

## Local development

There is no supported local mode for the `claude-code-action` step itself,
but the surrounding Python is ordinary and fully testable offline:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The test suite makes no Claude or GitHub API calls and doesn't touch the
repository's real transcripts, so no token is needed to develop or review
changes. You can also exercise the pipeline's Python side end-to-end
against a fixture by running `python -m archivist prepare`, `check-evidence`,
`verify` (with a hand-written `REPORT` env var), and `finalize` from a
scratch directory containing a sample `transcripts/<date>/meet/transcript.json`.

## Current limitations

Archivist currently processes one transcript per meeting date, sourced
only from Google Meet via TranscripTonic. Multiple sources per date, and
other meeting platforms, aren't supported.
