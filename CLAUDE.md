# Working conventions for this repo

- The user is the sole developer of this app. After making any change to
  the site (code, templates, static assets, the sleepiness tracker, etc.),
  commit it and push to GitHub immediately, without waiting to be asked.
  Don't leave finished work sitting uncommitted or unpushed locally —
  history should never be at risk of being lost.
- Push directly to the current working branch (no pull request needed)
  unless the user explicitly asks for a PR.

## Sleepiness tracker data

- Live entries are logged by users into the Claude.ai Artifact's own `db`
  (https://claude.ai/code/artifact/d16b472b-a6ff-436f-b916-21a1fafc4fbe,
  collection "entries") — that's the source of truth while the app is in use.
- A daily Routine ("Sleepiness Log daily GitHub sync", trig_019eaFNZDuwXXhXWKZai8BZK)
  fires once every 24 hours into this session. It reads all entries from
  that artifact db, writes them to sleepiness-tracker/data/entries.json,
  and commits + pushes only if the file actually changed — no commit per
  button click, just a daily check-in so the logged data has a durable
  git history and isn't only stored in the artifact.
