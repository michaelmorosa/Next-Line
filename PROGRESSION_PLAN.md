# Progression system plan: skill tree, XP and levels

Status: **approved, in progress.** Decisions are listed at the end.

## 1. What exists today

| Area | What's there | Where |
|---|---|---|
| Backend | Django 5.2, DRF, djoser + simplejwt (JWT auth), PostgreSQL (SQLite for tests). Apps: `users`, `trails`, `rides`. Function views and viewsets, routes in `nextline/urls.py`. | `backend/nextline` |
| App | Expo SDK 58, one native stack navigator (`Navigation.js`), a 4-tab bar in `ScreenContainer.js` (Rides, Record, Trails, Progress), shared components in `components/ui.js` (`Header`, `Button`, `StatTile`, `ProgressBar`, `Chip`, `Loading`, `ErrorState`, `OptionsSheet`), fetch helpers in `api.js`, `react-native-svg` already installed. | `frontend/nextline` |
| Ride logging | Rides are uploaded once with a `client_id` (repeat uploads ignored), analysed for descents, climbs, jumps and flow, then checked in (confidence, crash, features cleaned). | `rides/views.py`, `rides/processing.py` |
| Trail features | `Feature` has a `kind` (drop, jump, gap, rock_garden, roots, berm, technical, other) and a location. `FeatureProgress` tracks locked, almost or cleaned per rider. Pins on shared trails wait for approval. | `trails/models.py` |
| **Rider level (existing)** | Points built from bests and totals: cleaned features × trail difficulty, best descent speeds, biggest air, metres descended, climbing. 10 tiers (Beginner I to Expert), with requirements on harder features, mastered trails and active weeks from Intermediate up. Shown on Progress, explained on "How rider level works", and per ride on the ride summary. | `rides/scoring.py`, `rides/tiers.py`, `rides/level_guide.py`, `ProgressScreen.js`, `LevelGuideScreen.js` |
| Achievements | 17 one-off milestones, saved with the date earned. | `rides/achievements.py` |
| Streak | Consecutive weeks with a ride (`scoring.ride_streak`). | `rides/scoring.py` |
| Media | None: no `MEDIA_ROOT`, no file fields, no uploads. Videos are new. | |
| Tests | Django `TestCase` + DRF `APIClient` (`rides/tests.py`, `trails/tests.py`); `node --test` for pure JS logic (`tests/detectors.test.mjs`). | |

**The main conflict:** the spec says *rider level comes from total XP*. The app already has a different rider
level. Riders shouldn't see two levels, so this plan makes XP the rider level and folds the old point sources into
it as XP events (see §5 and open question 1).

## 2. Design overview

```
content/skills.json ─┐
content/rules.json  ─┼─► progression/content.py (load + validate, cached) ─► API: tree + rules
content/challenges.json ─► seed command ─► Challenge rows (editable in admin)

Rider actions                    progression/xp.py               Derived, never stored
log session ─────────┐          ┌─ apply caps from rules.json    total XP = SUM(ledger)
upload attempt ──────┼─► award ─┤  idempotent source key    ─►   level, XP to next
confirm mastery ─────┤          └─ append XPEntry               skill states
weekly streak, challenge, ride ┘                                 streak, challenge progress
```

- A new Django app **`progression`** holds the models, rules engine and API, so `rides` and `trails` change as
  little as possible.
- **Skill definitions live only in JSON files,** not the database. Rider rows store the skill's string `id` (e.g.
  `manual`). Editing text, drills, prerequisites or point values means editing a file and restarting gunicorn; the
  app reads the tree from the API, so **no app rebuild** is needed.
- I picked JSON over YAML because Python and JS read it with no new dependency. Long text is stored as a list of
  strings where that reads better (drills).
- **Skill states are computed, not stored,** from mastery and practice rows, so they can't drift out of sync.
- **Totals come only from the ledger.** `XPEntry` rows are never updated or deleted. Corrections are new rows
  with negative amounts.

## 3. Content files

All three files live in `backend/nextline/progression/content/`, and each has a `"version"` field.

### `skills.json`

```json
{
  "version": 1,
  "branches": [{"id": "foundations", "name": "Foundations", "color": "#7FB069"}, ...],
  "skills": [
    {
      "id": "small_drops",
      "name": "Small drops",
      "branch": "drops",
      "tier": 3,
      "prerequisites": ["roll_offs", "manual"],
      "description": "...",
      "why": "...",
      "drills": [{"name": "...", "how": "..."}, ...],
      "mastery_test": "You've got it when...",
      "media": [{"type": "video", "url": null, "caption": "..."}],
      "tags": ["drop"],
      "draft": true
    }
  ]
}
```

**Tags** that match a `FeatureKind` (`drop`, `jump`, `gap`, `berm`, `rock_garden`, `roots`, `technical`) link
the skill to trail features. Other tags are allowed and are only used for searching.

### Seed tree (19 skills, 4 tiers, 6 branches)

The spec lists 19 skills, which is close to the ~20 asked for. Columns in the tree view use **depth** (the
longest prerequisite chain), not tier, so lines always run left to right. Tier is the difficulty shown on the
skill and the mastery XP multiplier.

| Skill | Branch | Tier | Prerequisites |
|---|---|---|---|
| Attack position | Foundations | 1 | — |
| Braking control | Foundations | 1 | — |
| Looking ahead | Foundations | 1 | — |
| Flat corners | Cornering | 2 | Attack position, Braking control, Looking ahead |
| Berms | Cornering | 3 | Flat corners, Pumping |
| Switchbacks | Cornering | 3 | Flat corners, Braking control |
| Wheel lift | Wheel lifts | 2 | Attack position |
| Manual | Wheel lifts | 3 | Wheel lift, Pumping |
| Bunny hop | Wheel lifts | 4 | Manual |
| Pumping | Air | 2 | Attack position |
| Rollers | Air | 2 | Pumping |
| Tabletops | Air | 3 | Rollers, Wheel lift |
| Gap jumps | Air | 4 | Tabletops, Bunny hop |
| Roll-offs | Drops | 2 | Attack position, Braking control |
| Small drops | Drops | 3 | Roll-offs, **Manual** |
| Big drops | Drops | 4 | Small drops, Bunny hop |
| Roots and rocks | Technical | 2 | Attack position, Looking ahead |
| Rock gardens | Technical | 3 | Roots and rocks, Wheel lift |
| Steep rolls | Technical | 3 | Roll-offs, Braking control |

A new rider sees the 3 Foundations skills as **ready** and the other 16 as **locked**. Every skill's description,
why it matters, 2–3 drills and mastery test get practical draft text, with `"draft": true`. The app shows a small
"Draft" tag until a coach sets it to `false`. Media URLs start empty, for the coach to fill in.

### `rules.json` (every number in one place)

```json
{
  "version": 1,
  "xp": {
    "drill_session": 10,
    "attempt_video": 15,
    "mastery_per_tier": 100,
    "challenge_complete": 50,
    "weekly_streak": 25,
    "ride": 2,
    "feature_cleaned_per_weight": 20,
    "trail_pr": 10,
    "biggest_air": 10,
    "descent_per_100m": 1,
    "jump": 1
  },
  "caps": {
    "drill_sessions_per_skill_per_day": 3,
    "attempt_videos_per_skill_per_day": 1,
    "descent_xp_per_day": 15,
    "jump_xp_per_day": 10
  },
  "mastery": {"min_sessions": 3, "min_practice_days": 2, "min_videos": 1, "requires_confirmation": true},
  "streak": {"practice_days_per_week": 3},
  "levels": {"first_step": 100, "growth": 1.2, "count": 20},
  "titles": [
    {"from_level": 1, "title": "PQ Punk"},
    {"from_level": 3, "title": "Gravel Grom"},
    {"from_level": 5, "title": "Berm Burner"},
    {"from_level": 7, "title": "Root Rattler"},
    {"from_level": 9, "title": "Flow Fiend"},
    {"from_level": 11, "title": "Drop Dog"},
    {"from_level": 13, "title": "Gap Goblin"},
    {"from_level": 15, "title": "Sedona Shredder"},
    {"from_level": 17, "title": "Whistler Whipper"},
    {"from_level": 19, "title": "Line Legend"}
  ],
  "attempts": {"max_seconds": 60, "max_mb": 100}
}
```

- **Levels:** level 2 needs 100 XP, and each later level needs 20% more than the one before, for 20 levels. The
  thresholds are computed from these three numbers, and the API returns the full table. Totals at a few levels:
  L5 = 537, L10 = 2,080, L15 = 5,920, L17 = 8,744, L20 = 15,474. Mastering the whole tree is worth 4,800 XP
  from masteries plus roughly 3,000–4,000 from practice and streaks, so a full tree lands around level 16–17.
  Challenges and trail progress (§5) fill the rest.
- **The attempt-video daily cap is my addition.** The spec caps sessions but not videos, so without it a rider
  could upload 20 clips for 300 XP.
- **Ride XP (2)** is given for every uploaded ride. "With no skill practice" is read as "a ride on its own is
  worth 2"; practice logged that day earns its own XP on top.
- **Metres descended and jumps earn small XP with daily caps:** 1 XP per 100 m descended (up to 15 a day, so
  1,500 m) and 1 XP per jump (up to 10 a day). Time on the bike and reps count, but a big park day can't outweigh
  one mastered skill. Caps are per calendar day, not per ride, so splitting a day into many short rides doesn't
  help. Jumps use the server's 0.15–3 s airtime filter.
- **Titles:** 10 titles over 2-level ranges, from PQ Punk (levels 1–2) to Line Legend (19–20). Each one is the
  title of every level from its `from_level` up to the next title's. Rename them, or change the ranges, in this
  file.

### `challenges.json`

This seeds the `Challenge` table with a management command. After that, challenges are edited in the Django admin,
because each one has real dates. The seed is the **30-day manual challenge**: target `manual`, goal type
`sessions`, count 10, starting the day it's seeded and lasting 30 days.

### Validation

`python manage.py validate_progression` checks:

- **Skills:** required fields are present and non-empty; ids are unique; branch ids exist; tier is 1–4.
- **Prerequisites:** every prerequisite exists; no skill requires itself; **no cycles** (DFS that reports the
  cycle path, e.g. `manual → small_drops → manual`).
- **Warnings:** a skill whose tier is lower than a prerequisite's; unknown tags.
- **Rules:** every XP value and cap is a non-negative integer; level settings are sane.
- **Challenges:** target skills exist; end date is after start date.

It exits non-zero on any error. The same validation runs in the test suite, so a bad content edit fails `manage.py
test`, and gunicorn refuses to start with invalid content. That's safer than serving a broken tree.

## 4. Data model (new app `progression`)

| Model | Fields | Notes |
|---|---|---|
| `PracticeSession` | user, `skill_id`, `drill_index` (null = general practice), `client_id` (UUID, unique per user), `logged_at`, note, `ride` (FK, null) | `client_id` makes retries safe, the same pattern as `Ride`. Over-cap sessions are still saved and count toward mastery; they just earn no XP. |
| `Attempt` | user, `skill_id`, `video` (FileField), `duration_s`, `client_id`, `created_at`, note | Stored under `MEDIA_ROOT/attempts/<user>/`. Private: served only to the owner (§6). |
| `Mastery` | user, `skill_id`, `mastered_at`, `confirmed_test` (bool), `coach_verified` (bool), `verified_by` (FK, null), `verified_at` | Unique on (user, skill). Coach verification is set in the admin for now. |
| `Challenge` | `slug`, title, description, `skill_ids` (JSON list), `starts_at`, `ends_at`, `goal_type` (`sessions` or `master`), `goal_count` | |
| `ChallengeEntry` | user, challenge, `joined_at`, `completed_at` (null) | Unique on (user, challenge). Only progress made after joining and inside the window counts. |
| `XPEntry` (ledger) | user, `amount` (int, may be negative), `reason` (`session`, `attempt`, `mastery`, `challenge`, `streak`, `ride`, `feature`, `backfill`, `correction`), `skill_id` (null), `challenge` (FK, null), `source` (e.g. `session:812`, `streak:2026-W44`), `rules_version`, `created_at` | **Unique on (user, source),** so an award can never happen twice. `save()` refuses updates, `delete()` raises, and the admin is read-only. |

**Derived values** (in `progression/state.py` and `progression/xp.py`):

- **Skill state:** `mastered` if a `Mastery` row exists; else `in_progress` if any session is logged; else
  `ready` if all prerequisites are mastered; else `locked`. Practice is only accepted for ready or in-progress
  skills, so a locked skill can't be in progress.
- **Mastery eligible:** at least `min_sessions` sessions and `min_videos` attempts. Confirming the test then
  creates the `Mastery` row.
- **Next up:** 1–3 skills, in-progress ones first (closest to mastery), then ready ones by lowest tier. Ties go
  to the skill that unlocks the most other skills.
- **Streak:** a practice week is an ISO week with practice on at least 3 distinct days, in server local time like
  the existing `ride_streak`. The current streak counts back from this week. The 25 XP is awarded the moment a
  week reaches its 3rd practice day (source `streak:<year>-W<week>`).
- **Level:** total = `SUM(amount)` from the ledger; level, XP into the level and XP to the next come from the
  thresholds.
- **Challenge progress:** computed on read; the first time the goal is met, `completed_at` is set and 50 XP awarded.

All awards go through one function, `xp.award(user, amount_key, source, **links)`. It reads the value from the
rules file, checks the caps and the source's uniqueness, and returns the entry or `None`.

## 5. Fitting XP into the existing rider level

Decided:

- **The XP level becomes "Rider level"** everywhere: Progress, the ride summary and "How rider level works".
- **All the old point sources become XP events** in `rules.json`, so trail riding still counts:
  - feature cleaned: 20 × trusted difficulty weight (existing anti-gaming carries over: approved features only,
    rider ratings capped at blue)
  - new PR on a trail: 10
  - biggest air: 10 for each new best
  - metres descended and jumps: small amounts with daily caps (§3)
- **The 10 tiers become catchy titles** over 2-level ranges (PQ Punk → Line Legend), defined in `rules.json`. The
  old tier gates (harder features, active weeks) are dropped, because XP caps and mastery requirements now do
  that job.
- **Backfill:** `manage.py backfill_xp` writes ledger entries for existing riders from their history (rides,
  cleaned features, PRs), with `source` keys so it's safe to re-run.
- `rides/scoring.py`, `tiers.py` and `level_guide.py` are reduced to what's still used (speed rank, flow and
  climbing trends, favourite trails). Achievements stay as they are.

## 6. API

All endpoints require JWT, matching the rest of the API.

| Endpoint | Purpose |
|---|---|
| `GET /api/skills/` | Branches, skills (content + the rider's state, session count, attempts, XP earned), layout depth, next up, content version |
| `GET /api/skills/{id}/` | One skill with practice history, attempts (with video URLs), mastery status, and nearby tagged features (`?lat=&lng=`, else near the rider's latest ride) |
| `POST /api/skills/{id}/sessions/` | Log a session `{client_id, drill_index?, note?, ride?}` → the session, XP awarded (or `capped: true`), new total and level, streak award if any, completed challenges |
| `POST /api/skills/{id}/attempts/` | Multipart video upload → the attempt, XP, mastery eligibility |
| `POST /api/skills/{id}/master/` | `{confirmed_test: true}` → mastery, XP, **newly ready skills**, level before and after (feeds the unlock moment) |
| `GET /api/attempts/{id}/video/` | Owner-only video, served by nginx with `X-Accel-Redirect` so Django checks access but doesn't stream the file |
| `GET /api/xp/` | Ledger, paginated, newest first |
| `GET /api/challenges/`, `POST /api/challenges/{id}/join/` | Active challenges with the rider's progress |
| `GET /api/progress/` (extended) | Adds `xp_level` (level, total, into level, to next, title), practice streak, recent XP, skills mastered, next up, joined challenges |
| `GET /api/level-rules/` (rewritten) | XP values, caps, mastery rules and the level table from `rules.json` |

**Ride upload** (`POST /api/rides/`) also awards ride XP and any feature, PR or air XP. **Check-in** awards
feature XP. These are hooks into the existing views, not rewrites.

**Server changes for video:**

- `MEDIA_ROOT=/srv/nextline/media` (owned by `nextline`)
- in nginx, `client_max_body_size 110M` on the attempts path only, plus an `internal` location for
  `X-Accel-Redirect`
- in Django, size and type checks (`video/mp4`, `video/quicktime`) and the 60 s limit

## 7. App screens

New packages (Expo SDK modules, not new frameworks): **`expo-image-picker`** (record or pick a clip) and
**`expo-video`** (playback). Both work in Expo Go, and need camera, microphone and photo permission strings in
`app.json`.

| Screen | How it's built |
|---|---|
| **Skills tab** (new 5th tab, between Trails and Progress; it's where riders will go most often between rides, so it gets a tab instead of sitting a level deep in Progress) → `SkillTreeScreen` | A 2D scroll area (vertical `ScrollView` with a horizontal one inside): one row per branch, one column per depth. Nodes are cards; prerequisite lines are drawn in a `react-native-svg` layer behind them, including lines across branches (Roll-offs and Manual → Small drops). State colours come from `theme.js`: mastered = accent, in progress = outlined accent, ready = text, locked = muted with a lock icon. The "Next up" strip is pinned above the scroll area; tapping one scrolls to and pulses its node. iOS also gets pinch zoom (`maximumZoomScale`), and Android relies on scrolling. Layout maths lives in `utils/skillTree.js`, a pure module tested with `node --test`. |
| `SkillScreen` | `Header`, draft tag, description, why it matters, drills (each with a **Log session** button; a toast shows the XP, or "daily cap reached"), mastery test, attempts in a 2-wide grid (tap for side-by-side playback of two clips), an **Add attempt** button, practice history, XP earned here, and nearby tagged trail features (tap → `Trail`), with a clean empty state. |
| `MasteryScreen` | Shown when the rider taps **I passed the test** once eligible: the test text, a confirmation step, then the unlock moment: a big "Mastered", XP gained with the level bar filling (a level-up callout if one happened), and cards for the skills that just became ready, each linking to its skill. If the rider isn't eligible yet, it shows what's missing (e.g. "1 more session, 1 attempt video"). |
| `ProgressScreen` (reworked top) | Level card: level number and title, an XP bar using `ProgressBar`, "X XP to level N+1", practice streak, skills mastered (n/19), recent XP (last 5 entries, "All ›" → history), next up, and joined challenges. The existing flow, climbing and favourite-trail sections stay below. |
| `XPHistoryScreen` | `FlatList` of ledger entries: amount, reason in words, skill or challenge name, date. |
| `ChallengesScreen` | Active challenges with **Join** and a progress bar (e.g. "6/10 sessions · 12 days left"). |
| `LevelGuideScreen` (rewritten) | How XP and levels work, read from `/api/level-rules/`, so it always matches `rules.json`. |

Practice logging is **online-only** in this version. Videos are large, and the server enforces the caps. Retries
are safe because of `client_id`.

## 8. Tests

- **Unit (Django `TestCase`):**
  - skill state for each case (including ready only when *all* of several prerequisites are mastered)
  - cycle detection and validator errors (missing prerequisite, missing field, bad branch)
  - every XP rule and the daily caps (4th session = 0 XP)
  - idempotent sources
  - level thresholds and the level boundaries
  - streak (2 days = no award, 3rd day = award once, consecutive-week counting, a gap resets it)
  - ledger totals (with negative corrections)
  - that the ledger can't be updated or deleted
  - challenge progress and the completion award
- **Integration (`APIClient`):**
  - log a session → XP + in progress
  - upload an attempt (small generated file) → XP + eligibility
  - master Roll-offs then Manual → **Small drops becomes ready only after both**
  - level bar changes
  - ride upload awards 2 XP
  - backfill matches what live awards would have given
- **App:** `node --test` for `utils/skillTree.js` (depth columns, edge routing, next up).
- **Content:** a test runs `validate_progression` on the real files.

## 9. Demo rider

`python manage.py seed_progression_demo` creates `demo` (password printed once) with about 6 weeks of history:

- 3 Foundations, Pumping and Roll-offs mastered
- Manual in progress (5 sessions, 1 attempt), and Wheel lift in progress
- a 3-week practice streak, the manual challenge joined at 6/10
- a matching ledger

Attempts use a tiny bundled sample clip (`progression/demo/sample.mp4`, under 100 KB) so the video grid isn't
empty. It's safe to re-run, because it resets the demo user.

## 10. Build phases

Each phase ends with `DATABASE_ENGINE=sqlite python manage.py test`, plus `npm test` once there's app code, and a
commit. **Phase 0** first commits the outstanding deployment changes (bundle ID in `app.json`, `API_URL` in
`eas.json`, `.env.example`) on their own.

| Phase | Contents | Commit |
|---|---|---|
| 1. Content | `progression` app skeleton; `skills.json` (19 skills, draft text), `rules.json`, `challenges.json`; loader, validator, `validate_progression` command; tests for validation, cycles and multiple prerequisites | `Add skill tree content, point rules and validator` |
| 2. Engine | Models + migrations; ledger (append-only); `xp.award` with caps; levels; skill states; streak; challenge progress; admin (read-only ledger, coach-verify action); unit tests | `Add XP ledger, levels, skill states and streaks` |
| 3. API | Skills, sessions, attempts (media + private serving), mastery with unlocks, XP history, challenges; ride-upload XP hook; integration tests | `Add progression API: practice, attempts, mastery, challenges` |
| 4. One rider level | XP becomes rider level; feature, PR and air XP hooks; tier titles; `/api/progress/` and `/api/level-rules/` updated; old point code removed; `backfill_xp`; existing tests updated | `Make XP the rider level and backfill existing riders` |
| 5. App: tree | `expo-image-picker`, `expo-video`; Skills tab, `SkillTreeScreen`, `SkillScreen`, `MasteryScreen`; `utils/skillTree.js` + tests | `Add skill tree, skill detail and mastery screens` |
| 6. App: progress | Progress level card, `XPHistoryScreen`, `ChallengesScreen`, `LevelGuideScreen` rewrite; ride summary shows XP | `Show XP level, history and challenges in the app` |
| 7. Demo + docs | `seed_progression_demo`, sample clip, README section (how it works, where content and rules live, how to edit and validate, deploy notes for media and nginx), final full test run | `Add demo rider and progression docs` |

**Deploying** after phase 7:

- `git pull`, `pip install`, `migrate`, `seed_progression` (challenges), `backfill_xp`, then create
  `/srv/nextline/media` and update nginx (§6).
- The app needs a new EAS build because of the two new native modules.

## 11. Open questions

Decided:

1. **One rider level:** XP, including descent and jumps with daily caps (§3, §5).
2. **Titles:** PQ Punk → Line Legend over 2-level ranges (§3).
3. **Skills tab:** its own tab (§7).
4. **Attempt-video cap:** 1 rewarded video per skill per day.
5. **Video storage:** droplet disk for now. Clips are recorded or picked at 720p (`expo-image-picker`
   `videoQuality`) and limited to 60 s, so most are 10–40 MB. Move to Spaces if storage grows.
6. **Mastery pacing:** sessions on at least 2 different days (`mastery.min_practice_days: 2`), so all 3
   sessions can't be logged in one evening.
