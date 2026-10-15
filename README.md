🚆 RailMate — Indian Train Journey Planner





RailMate finds direct and one-change train journeys across 5,150 Indian trains and 7,344 stations.
It ranks every option on speed, cost, reliability and convenience, shows exactly why each option scored the way it did,
and flags delay and missed-connection risk.

Built with FastAPI · SQLite · scikit-learn · vanilla JavaScript. It needs no paid APIs and no API keys.

📘 New here? Follow the step-by-step guide in HOW_TO_RUN.md. It covers installing Python and Git,
running the app on Mac or Windows, and pushing to GitHub.

Search & explainable ranking

Connecting journeys





Train route

Saved trips





Help desk

Dark mode





Data-quality report & model card

Mobile





Data honesty: timetables come from a real public dataset, but it is a historical snapshot (circa 2016–17).
Fares are estimates, and the delay model is trained on synthetic labels. The app says this on screen too.
See Limitations.

Highlights

Real data pipeline. Imports 417,080 raw schedule rows, cleans them and indexes 103,582 real halts. A data-quality report is built in.

Connection search. One-change journeys with 45 min – 6 h layovers. It rejects backtracking and removes duplicate slots.

Explainable, absolute scoring. Four 0–100 sub-scores, so scores are comparable across different searches.

ML delay-risk model. Reproducible training with model selection on held-out data and a calibration report. A missed-connection estimate is shown for transfers.

Accounts and saved trips. PBKDF2 password hashing, JWT sessions and per-user data isolation. Fares are recomputed on the server, never trusted from the browser.

Production hardening. Strict Content Security Policy, security headers, rate limiting, request IDs and structured logs. There are health checks, a Docker image and CI.

Accessible UI. Keyboard autocomplete (ARIA combobox), focus-trapped dialogs, light and dark mode, and a responsive layout.

Quality checks. 30 automated tests (89% coverage) plus a lint check, run on every push.

Quick start

Requirements: Python 3.11 or newer, and an internet connection for the one-time ~100 MB dataset download.
For a detailed walkthrough with troubleshooting, see HOW_TO_RUN.md.

macOS / Linux (Terminal)

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.build_dataset      # downloads + cleans the dataset (~1-3 min)
python -m ml.train_delay_model       # trains the delay model (~10 s)
uvicorn app.main:app --reload

Windows (Command Prompt)

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m scripts.build_dataset
python -m ml.train_delay_model
uvicorn app.main:app --reload

Open http://127.0.0.1:8000 for the app and http://127.0.0.1:8000/docs for the interactive API docs.

Tip: search for "Kharagpur" → "Jaipur" with Sleeper class to see connecting journeys.

Run with Docker

cp .env.example .env                 # then set RAILMATE_SECRET_KEY (see the file for how)
docker compose up --build

The image builds the dataset and model at build time. It runs as a non-root user and keeps accounts on a named volume,
so they survive restarts and rebuilds.

Deploy

render.yaml deploys the Docker image to Render in one step. Note that the free plan has no
persistent disk, so accounts and saved trips reset whenever the service restarts. Attach a disk at /app/var to keep them.

How it works

Architecture

flowchart LR
    subgraph Offline["Offline build (scripts/, ml/)"]
        A[DataMeet JSON<br/>stations · trains · schedules] --> B[build_dataset.py<br/>clean · derive · index]
        B --> C[(railmate.db<br/>timetable, read-only)]
        C --> D[train_delay_model.py]
        D --> E[[delay_model.joblib<br/>+ model card]]
    end
    subgraph Runtime["FastAPI app (app/)"]
        C --> F[In-memory Timetable index]
        E --> G[DelayModel]
        F --> H[Journey planner<br/>direct + 1 transfer]
        G --> H
        H --> I[REST API /api/*]
        J[(users.db<br/>accounts · trips)] <--> I
    end
    I <--> K[Browser UI<br/>HTML · CSS · ES modules]

The timetable and user data live in separate databases, so rebuilding the timetable never touches user accounts.

Data pipeline and quality

The source is the DataMeet Indian Railways dataset (CC0). The raw data has real defects,
and each one is handled explicitly and counted in the Insights page:

Issue in raw data

How it's handled

Count

~75% of schedule rows are pass-through timing points (arrival = departure)

Keep only origin, terminus and stops with dwell time

417,080 rows → 103,582 halts

day field wrong or missing in ~13% of rows

Re-derive day offsets from the clock wrapping past midnight

all trains

Small backward time steps (data-entry glitches)

Clamp instead of misreading as "+1 day"

1,140

Rows with no time at all

Dropped

22,689

No per-stop distances

Haversine over station coordinates, scaled to the official train distance; time-interpolated where coordinates are missing or inconsistent

98 trains time-interpolated

Unusable trains (no distance or times)

Skipped

58

Validation against known routes: New Delhi → Agra on the Shatabdi computes to 197 km (actual ≈ 195 km), and Mumbai → Kota on
the Rajdhani to 914 km (actual ≈ 905 km).

Journey search

Direct trains. Every train halting at the origin and later at the destination. Trains visiting a station twice use the shortest pair.

One-change journeys. All (train₁ → transfer station → train₂) combinations with a 45 min – 6 h layover. Constraints:

Transfer stations must be closer to the destination than the origin is, so there's no backtracking.

At most two options are kept per first train.

When a direct train exists, transfers are shown only if they are within 125% of the fastest direct time.

Running days. These are checked against the train's origin date, not the boarding date, which matters for multi-day trains. The public dataset doesn't include running days, so they can be supplied in data/running_days.csv. Trains without them are labelled "Not in source data" rather than guessed.

Performance. A typical search takes under 10 ms against an in-memory index loaded at startup (about 0.3 s).

Ranking

Every journey gets four absolute sub-scores from 0 to 100:

Sub-score

Based on

Speed

Average speed including layovers (20 km/h → 0, 85 km/h → 100)

Cost

Fare compared with a standard express fare for the same distance and class

Reliability

1 − P(arriving > 30 min late, including missed connections)

Convenience

Penalties for changes, departures and arrivals between 00:00 and 05:00, and long layovers

The selected priority sets the weights:

Priority

Speed

Cost

Reliability

Convenience

Balanced

0.30

0.30

0.25

0.15

Fastest

0.55

0.15

0.15

0.15

Cheapest

0.15

0.55

0.15

0.15

Reliable

0.15

0.15

0.55

0.15

Fare estimates

The fare model follows the general structure of Indian Railways fares:

per-km base rates by class;

tapering for long distances;

minimum chargeable distances;

reservation fees;

superfast surcharges;

premium-train multipliers (Rajdhani, Shatabdi, Duronto) and a discount for Garib Rath.

The results are estimates, and the rates in app/services/fares.py should be recalibrated against an official fare table.

Delay-risk model





Target

Arrival more than 30 minutes late at the alighting station

Features

Train type, zone, season, north-India winter (fog), coastal monsoon, km from origin, leg km, halts before, arrival hour

Candidates

Logistic regression and histogram gradient boosting

Selection

Lowest Brier score on a 20% held-out test set

Result (synthetic)

Logistic regression: ROC-AUC 0.661, Brier 0.186 (constant baseline 0.202), well calibrated

Be clear about this when presenting the project. No licence-clear dataset of historical Indian train delays was available,
so the labels are synthetic. They are generated from a documented rule (synthetic_logit in ml/train_delay_model.py)
applied to real timetable features, plus noise. The metrics show the pipeline works end to end; they do not measure
real-world accuracy.

To train on real data, provide a CSV with the columns train_number, board_code, alight_code, travel_date, delayed:

python -m ml.train_delay_model --labels path/to/real_delays.csv

One honest finding: gradient boosting didn't beat logistic regression. That's expected, because the synthetic rule is additive
in log-odds, and it's exactly why the pipeline selects models on held-out data instead of assuming the complex model wins.

For transfers, the missed-connection risk combines the first leg's delay probability with the layover length. This is a
documented heuristic.

Help desk

The help desk retrieves answers with TF-IDF over a curated FAQ (data/faq.json). It blends word n-grams for meaning with
character n-grams for typos, so "lugage" still finds the luggage answer. Low-confidence questions get "Did you mean" suggestions
instead of a wrong answer.

Security

Area

Implementation

Passwords

PBKDF2-HMAC-SHA256, 390,000 iterations, per-user salt; constant-time comparison

Sessions

JWT (HS256) with expiry. Production refuses to start without a secret of 32+ characters

Authorisation

Every trip query is scoped to the signed-in user. Other users' trips return 404, not 403

Input

Pydantic validation on all inputs; parameterised SQL everywhere

Integrity

Saved trips are rebuilt and re-priced on the server from train numbers and stations only

Browser

Strict CSP (no inline scripts or styles), X-Frame-Options, nosniff, Referrer-Policy; all dynamic text is HTML-escaped

Abuse

Per-IP rate limit (120/min API, 10/min login/register); login timing is equalised for unknown emails

Known trade-offs:

Token storage. The token is kept in localStorage, which is simple but readable by injected scripts. The strict CSP mitigates this, and an httpOnly cookie would be stronger.

Rate limiting. The limiter keeps state in process memory, so use Redis or a gateway limiter when running several instances.

API

Interactive docs are at /docs.

Method

Endpoint

Auth

Description

GET

/api/health

—

Liveness, data and model status

GET

/api/stations?q=

—

Station autocomplete

GET

/api/journeys?from=&to=&date=&class=&priority=&transfers=

—

Ranked journeys

GET

/api/trains/{number}

—

Full timetable for a train

POST

/api/auth/register · /api/auth/login

—

Returns a JWT

GET

/api/auth/me

✔

Current user

GET / POST

/api/trips

✔

List or save trips

DELETE

/api/trips/{id}

✔

Delete own trip

GET

/api/helpdesk?q=

—

Help-desk answer

GET

/api/insights

—

Dataset stats, data quality, model card

Testing and quality

pytest --cov          # 30 tests, ~89% coverage
ruff check .          # lint (includes security rules)

Fixture dataset. The tests build a tiny dataset in the exact DataMeet format, with deliberate defects (pass-through rows, wrong day fields, a time glitch, a row without times, a zero-distance train), and run it through the real importer.

Planner tests. Running days, class filters, connections and protection against tampered trips.

API tests. Validation, authentication, cross-user isolation, security headers, rate limiting, and graceful degradation when data is missing.

GitHub Actions runs the lint check and the tests on Python 3.11 and 3.12 for every push.

Configuration

Settings come from environment variables or a .env file (see .env.example).

Variable

Default

Purpose

RAILMATE_ENV

development

production enforces a strong secret

RAILMATE_SECRET_KEY

random in dev

JWT signing key

RAILMATE_RATE_LIMIT

120

API requests per minute per IP (0 = off)

RAILMATE_TOKEN_MINUTES

120

Session length

RAILMATE_CORS_ORIGINS

empty

Allowed cross-origin callers

RAILMATE_DB_PATH / RAILMATE_USER_DB_PATH / RAILMATE_MODEL_PATH

see .env.example

File locations

Project structure

railmate/
├── app/
│   ├── main.py              # app factory, middleware, error handling
│   ├── config.py            # settings + .env loader
│   ├── db.py                # schemas (timetable / users), connections
│   ├── security.py          # password hashing, JWT
│   ├── middleware.py        # security headers, logging, rate limiting
│   ├── schemas.py           # request validation
│   ├── routers/             # stations, journeys, auth, trips, info
│   └── services/            # timetable index, planner, fares, delay model, help desk
├── scripts/build_dataset.py # download + clean + index the dataset
├── ml/train_delay_model.py  # training, model selection, model card
├── frontend/                # index.html, css/, js/ (ES modules, no build step)
├── data/                    # faq.json, running_days.csv (generated DBs are git-ignored)
├── tests/                   # pytest suite + DataMeet-format fixtures
├── docs/screenshots/        # images used in this README
├── HOW_TO_RUN.md            # step-by-step setup and GitHub guide
├── Dockerfile · docker-compose.yml · render.yaml
└── .github/workflows/ci.yml

Limitations

Historical timetable. The data dates from around 2016–17. Trains, timings and codes have changed (Mumbai CST appears as CSTM, for example). Always confirm on official channels.

No running days in the source. Running days are enforced only when supplied in data/running_days.csv.

Synthetic delay labels. The model demonstrates the pipeline, not real-world accuracy.

Estimated fares. No dynamic pricing, quotas or concessions.

At most one change. Transfers happen only within the same station, so walking between nearby stations isn't covered.

No live data. There's no seat availability or live running status, since those need official or partner APIs.

Roadmap

Load a current timetable (for example GTFS, where available) and running days.

Train on real delay records; add weather and fog features.

Multi-change routing (RAPTOR algorithm) and walking transfers between nearby stations.

httpOnly cookie sessions, Postgres, and a Redis-backed rate limiter for multi-instance deployments.

Frontend end-to-end tests in CI (Playwright).

Data licence and attribution

Railway data: DataMeet Indian Railways dataset, released under CC0 1.0 (public domain), by DataMeet contributors.
RailMate is an independent portfolio project and is not affiliated with Indian Railways or IRCTC.

License

MIT