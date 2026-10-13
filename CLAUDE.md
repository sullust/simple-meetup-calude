# Working conventions for this repo

- The user is the sole developer of this app. After making any change to
  the site (code, templates, static assets, the sleepiness tracker, the
  pill tracker, etc.), commit it and push to GitHub immediately, without
  waiting to be asked.
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

## Pill tracker data

- Live entries are logged by users into the Claude.ai Artifact itself
  (https://claude.ai/artifact/Dqva53kPru2xVQ13TwNnTG, a "Wanted a Pill"
  craving log) — that's the source of truth while the app is in use. Unlike
  the sleepiness tracker, this one uses the `artifact` capability (the page
  republishes its own full HTML with the updated entry list embedded in a
  `<script id="entries-data">` tag) rather than the `db` capability.
- A daily Routine ("Pill Log daily GitHub sync", trig_01X7tNGTArPapQMdmVx1zRif)
  fires once every 24 hours into a dedicated session
  (session_014YUs1j8VmJv7NxzNn1UkHb). It reads the artifact's live HTML,
  extracts the entries-data JSON, writes it to
  pill-tracker/data/entries.json, and commits + pushes only if the file
  actually changed — no commit per button tap, just a daily check-in so the
  logged data has a durable git history and isn't only stored in the
  artifact.

## Drink log

- Live entries are logged into the Claude.ai Artifact itself
  (https://claude.ai/artifact/53oDJzYMn6i1K5jqJxiiyu) using the `artifact`
  capability, same as the pill tracker. Source: drink-log/index.html.
- Home Screen icon: the Pages workflow serves drink-log/launcher.html at
  /drink-log/ with the apple-touch-icon. It is only a shortcut: opening it with
  ?go (the address Safari saves when adding to Home Screen) redirects to the
  artifact, so all data stays in the artifact. Not a standalone web app, so it
  opens in Safari where the user is signed in to claude.ai. A Pages copy of the
  app itself is NOT acceptable (it would store entries only on the device).
  To use a custom icon, replace drink-log/icons/*.png (180, 192, 512 px, opaque).
- A daily Routine ("Drink Log daily GitHub sync", trig_01PxrQHdaJYPQZonDaujtm7C)
  fires once every 24 hours into this session (session_015TxFtoeTbvUGnAhqGBwvEB).
  It reads the artifact's live HTML, extracts the entries-data JSON, writes it to
  drink-log/data/entries.json, and commits + pushes only if the file changed.
