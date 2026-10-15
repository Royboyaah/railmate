# RailMate — Complete Setup Guide

This guide takes you from the zip file to a running app on your computer and a published GitHub repository.
Every step is written for both **Mac** and **Windows**. Run commands **one at a time**, in the order shown.

**Time needed:** about 30–45 minutes the first time, and about 1 minute on every later run.

---

## Contents

1. [Install the tools you need](#step-1--install-the-tools-you-need)
2. [Unzip the project](#step-2--unzip-the-project)
3. [Open a terminal inside the project folder](#step-3--open-a-terminal-inside-the-project-folder)
4. [Personalise two files](#step-4--personalise-two-files)
5. [Create a virtual environment and install packages](#step-5--create-a-virtual-environment-and-install-packages)
6. [Build the train database and the model](#step-6--build-the-train-database-and-the-model)
7. [Run the app (frontend + backend)](#step-7--run-the-app-frontend--backend)
8. [Run the tests (optional but recommended)](#step-8--run-the-tests-optional-but-recommended)
9. [Push the project to GitHub](#step-9--push-the-project-to-github)
10. [What gets pushed and what doesn't](#step-10--what-gets-pushed-and-what-doesnt)
11. [Check that GitHub is happy](#step-11--check-that-github-is-happy)
12. [Optional: run with Docker](#step-12--optional-run-with-docker)
13. [Optional: put it online with Render](#step-13--optional-put-it-online-with-render)
14. [Daily use cheat sheet](#step-14--daily-use-cheat-sheet)
15. [Troubleshooting](#troubleshooting)

---

## How the project fits together

You do **not** need to run the frontend and backend separately. One command starts the FastAPI **backend**, and that backend
also serves the **frontend** (the HTML, CSS and JavaScript in `frontend/`). You open one address in your browser and get both.

| Part | Folder | What it does |
|---|---|---|
| Backend | `app/` | API, journey planner, login, saved trips |
| Frontend | `frontend/` | The website you see in the browser |
| Data builder | `scripts/` | Downloads and cleans the railway data (run once) |
| ML model | `ml/` | Trains the delay-risk model (run once) |
| Tests | `tests/` | Automatic checks that everything works |

---

## Step 1 — Install the tools you need

You need **Python 3.11 or newer** and **Git**, plus a free **GitHub account** for step 9.

### Mac

**1a. Check whether Python is already installed.** Open the **Terminal** app (press `Cmd + Space`, type *Terminal*, then press Enter):

```
python3 --version
```

If it prints `Python 3.11.x` or higher, you're done with Python. If not, download the latest Python 3 installer from
**https://www.python.org/downloads/** and run it.

> **Important (python.org installer only):** after installing, open **Finder → Applications → Python 3.x** and double-click
> **Install Certificates.command**. Without this, the data download in step 6 fails with a certificate error.

**1b. Check Git:**

```
git --version
```

If Git isn't installed, macOS offers to install the "Command Line Developer Tools". Accept, wait for it to finish, then run the
command again.

### Windows

**1a. Install Python.** Download the latest Python 3 installer from **https://www.python.org/downloads/**.
On the first screen of the installer, **tick "Add python.exe to PATH"**, then click *Install Now*.

**1b. Install Git.** Download it from **https://git-scm.com/download/win** and install with the default options.

**1c. Check both.** Open a **new** Command Prompt (press the `Windows` key, type *cmd*, then press Enter):

```
python --version
```

```
git --version
```

Both should print a version number. If `python` isn't recognised, see [Troubleshooting](#troubleshooting).

### Both

Create a free account at **https://github.com** if you don't have one yet.

---

## Step 2 — Unzip the project

1. Find `railmate.zip` in your Downloads folder.
2. **Mac:** double-click it. **Windows:** right-click it → *Extract All…* → *Extract*.
3. Move the resulting `railmate` folder into your **Documents** folder.

> **Windows tip:** "Extract All" sometimes creates a folder inside a folder (`railmate\railmate`). Open it and make sure the
> folder you move is the one that directly contains `README.md`, `app` and `frontend`.

---

## Step 3 — Open a terminal inside the project folder

**Mac (Terminal):**

```
cd ~/Documents/railmate
```

```
ls
```

**Windows (Command Prompt):**

```
cd %USERPROFILE%\Documents\railmate
```

```
dir
```

You should see `README.md`, `HOW_TO_RUN.md`, `app`, `frontend`, `requirements.txt` and other files.
**Keep this terminal window open.** Every remaining command runs inside this folder.

---

## Step 4 — Personalise two files

Open the project folder in any text editor (VS Code, TextEdit, Notepad) and fill in two placeholders:

| File | Placeholder | Replace with |
|---|---|---|
| `LICENSE` | `YOUR NAME` | Your full name |
| `README.md` (near the top, appears twice) | `YOUR-USERNAME` | Your GitHub username |

Save both files.

---

## Step 5 — Create a virtual environment and install packages

A *virtual environment* is a private Python installation just for this project, so it never conflicts with anything else on
your computer.

**Mac (Terminal):**

```
python3 -m venv .venv
```

```
source .venv/bin/activate
```

```
pip install -r requirements-dev.txt
```

**Windows (Command Prompt):**

```
python -m venv .venv
```

```
.venv\Scripts\activate
```

```
pip install -r requirements-dev.txt
```

After activation, your prompt starts with **`(.venv)`**. That's how you know it worked. The install takes 1–3 minutes.

> Every time you open a **new** terminal to work on the project, run the `cd` command from step 3 and the
> `activate` command again.

---

## Step 6 — Build the train database and the model

These two commands run **once**. They download about 100 MB of public railway data, clean it into a database, and train the
delay-risk model.

Run these on **Mac or Windows** (same command on both, with `(.venv)` showing):

```
python -m scripts.build_dataset
```

```
python -m ml.train_delay_model
```

**What success looks like:** the first command ends with lines like `trains_loaded 5150`. The second ends with
`Metrics: {'roc_auc': 0.66, ...}`.

This creates three things on your computer, and none of them are pushed to GitHub (step 10 explains why):

- `data/raw/`, the downloaded files;
- `data/railmate.db`, the train database;
- `ml/artifacts/delay_model.joblib`, the trained model.

---

## Step 7 — Run the app (frontend + backend)

Run this on **Mac or Windows**:

```
uvicorn app.main:app --reload
```

Wait until you see `Application startup complete`, then open your browser at:

- **http://127.0.0.1:8000**, the RailMate website (the frontend);
- **http://127.0.0.1:8000/docs**, the interactive API documentation (the backend).

**Try these searches:**

| From | To | Class | What you'll see |
|---|---|---|---|
| New Delhi | Agra Cantt | AC Chair Car | Shatabdi as the top pick |
| Mumbai Central | New Delhi | AC 3 Tier | Rajdhani, with a full score breakdown |
| Kharagpur | Jaipur | Sleeper | Connecting journeys with a change of train |

Then try *Create account* → *Save trip* → *My Trips*, plus the *Help* and *Insights* pages.

**To stop the app:** click into the terminal and press `Ctrl + C` (on both Mac and Windows).

> The `--reload` option restarts the server automatically whenever you edit a Python file. To change the website itself,
> edit files in `frontend/` and refresh the browser.

---

## Step 8 — Run the tests (optional but recommended)

If the app is running, stop it with `Ctrl + C` first. Then run these on **Mac or Windows**:

```
pytest --cov
```

```
ruff check .
```

Expected results: **30 passed** with about 89% coverage, then **All checks passed!**

---

## Step 9 — Push the project to GitHub

### 9a. Create an empty repository on GitHub

1. Sign in to **https://github.com** and click the **+** button (top right) → **New repository**.
2. **Repository name:** `railmate`.
3. **Description:** *Indian train journey planner with connections, explainable ranking and an ML delay-risk model.*
4. Choose **Public**, so recruiters can see it.
5. **Do NOT tick** "Add a README", ".gitignore" or "license", because the project already has all three. Ticking them causes a conflict when you push.
6. Click **Create repository**, and keep that page open.

### 9b. Tell Git who you are (first time on this computer only)

Run these on **Mac or Windows**, with your own name and the email address of your GitHub account:

```
git config --global user.name "Your Name"
```

```
git config --global user.email "you@example.com"
```

### 9c. Commit and push

Make sure you're still inside the `railmate` folder (step 3). Then run these on **Mac or Windows**:

```
git init
```

```
git add .
```

```
git status
```

Look through the list `git status` prints. You should see `app/`, `frontend/`, `README.md` and similar files.
You should **not** see `.venv`, `data/railmate.db`, `data/raw` or `ml/artifacts`. If you do, stop and check
[Troubleshooting](#troubleshooting).

```
git commit -m "RailMate: Indian train journey planner"
```

```
git branch -M main
```

Replace `YOUR-USERNAME` in the next command with your GitHub username:

```
git remote add origin https://github.com/YOUR-USERNAME/railmate.git
```

```
git push -u origin main
```

### 9d. Signing in during the push

GitHub no longer accepts your account password for pushing. What happens depends on your system:

- **Windows:** a browser window usually opens asking you to sign in to GitHub. Approve it and the push continues.
- **Mac:** Git asks for a *Username* and *Password*. Enter your GitHub username as the username and a
  **personal access token** as the password:
  1. Go to **https://github.com/settings/tokens** and generate a new **classic** token.
  2. Give it a name like *railmate laptop*, tick the **repo** scope, and generate it.
  3. Copy the token. It's shown only once.
  4. Paste it when Git asks for the password. Nothing appears on screen while you paste; that's normal.

---

## Step 10 — What gets pushed and what doesn't

The `.gitignore` file handles this automatically. You don't have to pick files by hand.

| Pushed to GitHub ✅ | Not pushed ❌ (and why) |
|---|---|
| `app/` — backend code | `.venv/` — your local Python install, which is large and machine-specific |
| `frontend/` — website code | `data/raw/` — 100 MB download that anyone can re-download |
| `scripts/`, `ml/` — data and model code | `data/railmate.db` — rebuilt by step 6 |
| `tests/` — test suite and small test data | `ml/artifacts/` — rebuilt by step 6 |
| `data/faq.json`, `data/running_days.csv` | `var/` — user accounts and saved trips (private data) |
| `docs/screenshots/` — images used in the README | `.env` — secret keys, which must **never** go on GitHub |
| `README.md`, `HOW_TO_RUN.md`, `LICENSE` | `__pycache__/`, `.pytest_cache/` — temporary files |
| `Dockerfile`, `docker-compose.yml`, `render.yaml` | |
| `.github/workflows/ci.yml` — automatic testing | |
| `requirements*.txt`, `pyproject.toml`, `.gitignore`, `.env.example` | |

---

## Step 11 — Check that GitHub is happy

1. Open `https://github.com/YOUR-USERNAME/railmate`. The README shows with screenshots.
2. Click the **Actions** tab. A run called **CI** starts automatically and should turn **green ✓** within about 2 minutes.
   This is GitHub running your tests on Python 3.11 and 3.12.
3. Back on the main page, click the **⚙ gear next to "About"** (right side) and add:
   - **Topics:** `python`, `fastapi`, `machine-learning`, `scikit-learn`, `indian-railways`, `data-engineering`.
4. On your GitHub profile page, choose **Customize your pins** and pin `railmate`.

---

## Step 12 — Optional: run with Docker

This needs **Docker Desktop** (https://www.docker.com/products/docker-desktop/), installed and running.

**12a. Create your settings file.**

**Mac (Terminal):**

```
cp .env.example .env
```

**Windows (Command Prompt):**

```
copy .env.example .env
```

**12b. Generate a secret key.** Run this on **Mac or Windows**:

```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open `.env` in a text editor and paste the printed value straight after `RAILMATE_SECRET_KEY=` on that line. Save the file.

**12c. Build and start.** Run this on **Mac or Windows**. The first build takes a few minutes because it downloads the data
inside the container:

```
docker compose up --build
```

Open **http://127.0.0.1:8000**. Stop it with `Ctrl + C`.

---

## Step 13 — Optional: put it online with Render

A live link in your CV and README is worth a lot. The project includes `render.yaml` for this.

1. Sign up at **https://render.com** using your GitHub account.
2. Create a new **Blueprint** and connect your `railmate` repository.
3. Render reads `render.yaml`, which sets the free plan, Docker, the health check and an auto-generated secret key. Approve it.
4. The first build takes about 5–10 minutes. You then get a link like `https://railmate-xxxx.onrender.com`.
5. Add the link to the README and to the "About" box on GitHub.

> **Good to know about the free plan:** the app goes to sleep after inactivity, so the first visit takes about 30–60 seconds
> to wake it up. It also has no permanent storage, so accounts and saved trips reset when the service restarts. That's fine
> for a portfolio demo.

---

## Step 14 — Daily use cheat sheet

**Start the app on a later day:**

| Mac (Terminal) | Windows (Command Prompt) |
|---|---|
| `cd ~/Documents/railmate` | `cd %USERPROFILE%\Documents\railmate` |
| `source .venv/bin/activate` | `.venv\Scripts\activate` |
| `uvicorn app.main:app --reload` | `uvicorn app.main:app --reload` |

**Push changes after editing code.** These are the same on Mac and Windows, run one per line:

| Command | What it does |
|---|---|
| `pytest` | Make sure nothing broke |
| `git add .` | Stage your changes |
| `git commit -m "Describe what you changed"` | Save a snapshot |
| `git push` | Upload to GitHub, which runs CI again |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Windows:** `'python' is not recognized` | Reinstall Python and tick **"Add python.exe to PATH"**, then open a *new* Command Prompt. Or use `py` instead of `python` in step 5 (`py -m venv .venv`). |
| **Mac:** `command not found: python` | Use `python3` until the virtual environment is active. After `source .venv/bin/activate`, `python` works. |
| **Windows PowerShell:** "running scripts is disabled" when activating | Use **Command Prompt** (cmd) instead of PowerShell, as this guide does. |
| `CERTIFICATE_VERIFY_FAILED` during step 6 (Mac) | Run **Install Certificates.command** from *Applications → Python 3.x* (see step 1), then repeat step 6. |
| Step 6 download fails or times out | Check your internet connection and run the command again; finished downloads are reused. On restrictive networks (college or office Wi-Fi), try a mobile hotspot. |
| Website says *"Timetable not loaded"* | You skipped step 6. Stop the app, run step 6, then start it again. |
| Insights page says *"heuristic fallback"* | The model wasn't trained. Run `python -m ml.train_delay_model`. |
| `Address already in use` / port 8000 busy | Another app is using the port. Run `uvicorn app.main:app --reload --port 8001` and open http://127.0.0.1:8001. |
| `ModuleNotFoundError: No module named 'fastapi'` | The virtual environment isn't active (no `(.venv)` in the prompt). Run the `activate` command from step 5. |
| `ModuleNotFoundError: No module named 'app'` | You're in the wrong folder. `cd` into the folder that contains `app/` (step 3). |
| `git push` rejected with *"fetch first"* | The GitHub repo was created with a README or licence. For a brand-new repo you can overwrite it with `git push -u origin main --force`. **Only do this on a new, empty repo.** |
| `git status` lists `.venv` or `data/railmate.db` | The `.gitignore` file is missing. It's a hidden file: on Mac press `Cmd + Shift + .` in Finder to show it; on Windows enable *View → Hidden items*. Make sure it's in the project folder, then run `git rm -r --cached .` followed by `git add .` |
| You were logged out of the website after restarting | Expected during development: without a `.env` secret key, a new random key is used on each start. Add `RAILMATE_SECRET_KEY` to `.env` (step 12a–b) to stay logged in. |
| CI badge in the README shows "no status" | The badge updates after the first CI run finishes. Also check that `YOUR-USERNAME` was replaced in the README (step 4). |

---

**Questions about how something works?** Read the README sections on the data pipeline, ranking and delay model, then the
code comments in `app/services/planner.py` and `scripts/build_dataset.py`. Those are the two most interesting files to be
able to explain in an interview.
