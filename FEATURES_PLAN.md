# Features plan: progression built on real trail features

Status: **draft for review**. Nothing below has been built yet. Step 1 stops here.

The goal: progress means a specific drop, jump or corner on a real trail, graded by our team, and not a skill
tree. Riders log how each feature went with one tap, climb ladders of similar features, and get "next up when
you're ready" suggestions. The existing skill content stays and becomes tags and tips behind the scenes.

Decisions marked **(confirm)** are ones I made so the plan is complete. Each has a default; tell me if you want
a different one.

---

## 1. What exists today

**Stack.** Django 5.2 + DRF + Postgres, JWT auth through djoser, deployed with gunicorn and nginx on the
droplet. The app is Expo SDK 58 / React Native 0.88 with a single native-stack navigator and a custom bottom
tab bar (`ScreenContainer.js`). Backend tests use Django's test runner (about 150 tests). Frontend tests use
`node --test` (detectors, skill tree layout).

**Auth and roles.** `users.CustomUser` adds email and crash-contact fields. `is_staff` is the only role. Staff
pins skip approval, and staff use the Django admin.

**Trails (`trails/`).**
- `Trail`: name, direction (descent/climb), difficulty (green to double black), start/end points, length,
  drop, simplified path. Trails are either *shared* (`owner` empty, added in the admin) or *auto* (per-rider,
  detected from rides). There is no trail-system grouping.
- `Feature`: trail, name, kind (drop, jump, gap, rock garden, roots, berm, technical, other), lat/lng,
  created_by, `approved`. Riders pin these from the app, and pins on shared trails wait for admin approval.
- `FeatureProgress`: per rider and feature, a status (locked/almost/cleaned), clean count, first clean date and
  note. Updated from the ride check-in.
- Admin actions: make a trail shared (merging riders' copies, `sharing.py`), approve features, and merge
  duplicate features.

**Rides (`rides/`).** Ride upload with GPS track, jump/airtime detection, flow score, touchdowns and climbing
stats. Efforts are timed on trails, with PRs. Post-ride check-in (confidence, crashed, touchdowns, cleaned
features). Crash alerts by SMS. Achievements. `scoring.progress()` and `level_guide.suggestions()` feed the
Progress screen.

**Progression (`progression/`).**
- `content/skills.json`: 50 skills in 9 branches, each with a description, "why", 2–3 drills, a mastery test,
  media placeholders and tags (drop, jump, gap, berm, roots, rock_garden, technical). Validated on startup
  (`content.py`) and with `validate_progression`.
- `content/rules.json`: every XP value, cap, mastery requirement, level curve (20 levels) and title.
- `content/challenges.json`: one challenge (30-day manual).
- Models: `PracticeSession` (drill logs), `Attempt` (private skill videos, served through nginx
  X-Accel-Redirect), `Mastery`, `Challenge` / `ChallengeEntry` (goal types: sessions, master), and **`XPEntry`,
  an append-only ledger** with unique `(user, source)` so nothing pays out twice, plus correction entries.
- XP sources: drills, videos, mastery, challenges, practice streaks, rides, descent, jumps, features, PRs,
  clean climbs and biggest air.
- Commands: `seed_progression`, `seed_progression_demo` (demo rider), `backfill_xp`, `validate_progression`.

**App screens.** Rides, Record, Trails, Trail, PinFeature, RideSummary (with the cleaned-features check-in),
**Skills (skill tree), Skill, Mastery**, Progress, LevelGuide, XPHistory, Challenges, Settings, SensorLab,
Login and Register. Tabs: Rides · Record · Trails · Skills · Progress.

**Offline.** Finished rides are saved to files (`recording/storage.js`) and queued for upload
(`recording/uploads.js`). Retries are safe because the server ignores repeated `client_id`s. The same pattern
fits queued feature captures.

**Media.** `MEDIA_ROOT` on the droplet's disk. Rider attempt videos are private and nginx serves them after
Django checks ownership. Pillow isn't installed yet.

---

## 2. Keep, repurpose, remove or hide

### Keep as is
- Ride recording, upload queue, jump/flow/climb analysis, timed efforts, PRs, crash alerts.
- Auth, djoser/JWT, the user model (gains two fields).
- The `XPEntry` ledger: append-only, unique source, corrections. It becomes the **points** ledger. Only the
  wording changes from "XP" to "points" in the app and the admin. The model and table names stay, so there is
  no risky rename migration.
- `content/` JSON-plus-validation pattern, levels, titles and `level_for()`.
- Challenge and ChallengeEntry models, the join flow, and the screen.
- Achievements, updated to read rider logs instead of `FeatureProgress`.

### Repurpose
| Existing | Becomes |
|---|---|
| `skills.json` (all 50 skills, unchanged) | **Skill tags** on features. Descriptions, "why" text, drills and mastery tests become the feature page's **"Stuck?"** section. Branches become the **strength types** on the dashboard. |
| `Feature` model | The graded, certified feature, with new fields (section 3). |
| `PinFeatureScreen` (GPS capture already works) | Team-only **Add feature on site** screen. |
| `TrailScreen` | Trail page: features in riding order with photo, type, grade and the rider's status. |
| `TrailsScreen` | Trail systems list leading to the system page (map + trails + progress). |
| `SkillScreen` | The feature page's "Stuck?" view: tips and optional drills for one tag. No mastery button. |
| RideSummary's cleaned-features check-in | A **"Log this trail"** button for each shared trail ridden, opening the multi-feature log screen. |
| `level_guide.suggestions()` | Replaced by the **next-up** engine. Climb, PR and air goals stay as secondary suggestions. |
| `FeatureProgress` rows | Migrated into `FeatureLog` entries, then the table is dropped (phase 8). |
| Challenge goal types | Gain `next_features` and `features`. |
| `seed_progression_demo` | Seeds the demo trail system and a demo rider with log history. |
| `XPHistoryScreen`, `LevelGuideScreen` | Points history and "how points work", reading the new rules. |

### Remove or hide
- **Skill tree in the app:** delete `SkillTreeScreen`, `MasteryScreen`, `utils/skillTree.js` and its test, and
  the Skills tab. The skill content stays in `skills.json`.
- **Drill and video points:** set `drill_session`, `attempt_video`, `mastery_per_tier` and `weekly_streak` to
  0 in the rules. `xp.award()` already skips 0 amounts, so the code stays and nothing pays out. The
  sessions/attempts/master endpoints stay on the server, unlinked from the app. Points already in the ledger
  stay: it's append-only, and totals are derived.
- **Rider pinning:** riders no longer add features. The team does. Riders get "Report a change" instead.
  Existing rider pins become `draft` features, visible only to the team, who can grade and certify them or
  delete them.
- The old `feature_cleaned_per_weight` trail-difficulty multiplier is replaced by grade-based points.

### (confirm) Ride-based points
The spec lists only feature points, but rides also earn points today: the ride itself, descent, jumps, PRs,
clean climbs and biggest air. **Default: keep them,** at their current small values, because they reward
riding without pressuring anyone to hit features. Setting them to 0 in the rules file is a one-line change if
you'd rather points come only from features.

---

## 3. Data model changes

All in `trails/` unless noted. Migrations are additive first. Old fields are dropped only after data has moved
(phase 8).

### New: `TrailSystem`
`name`, `slug`, `location` (text), `lat`/`lng` (map centre), `description`, `is_demo` (bool, for one-command
removal).

### `Trail` (changed)
- `system` → FK `TrailSystem`, nullable. Auto trails have none.
- `difficulty` stays as the **official difficulty rating** (unrated if none).
- `length_m`, `direction` already exist.
- Rider-facing trail pages show shared trails that belong to a system. Auto trails stay for timing only.

### `Feature` (changed)
| Field | Notes |
|---|---|
| `trail`, `name`, `lat`, `lng` | Existing. `lat`/`lng` is the GPS point. |
| `type` | Replaces `kind`: drop, jump, corner, rock_garden, roots, steep, skinny, climb, other. Migration maps gap→jump, berm→corner, technical→other. |
| `grade` | 1–10, within its type. Nullable only while a draft. |
| `drop_height_m`, `gap_length_m`, `steepness_deg` | Optional measurements, shown when relevant to the type. |
| `position` | Riding order on the trail, an integer, reordered in the bulk view. On capture it defaults to the GPS point projected onto the trail path. |
| `description`, `how_to_ride`, `what_can_go_wrong` | Text. |
| `has_ride_around`, `ride_around_grade`, `ride_around_note` | Always shown when present. |
| `skill_tags` | JSON list of skill ids from `skills.json`, validated against it. |
| `status` | draft, certified, changed or closed. Replaces `approved`. |
| `created_by` | Existing. |
| `submitted_by`, `submitted_at` | Who marked it ready for review. |
| `certified_by`, `certified_at` | The second reviewer. |
| `last_verified_at` | Set on certification and by "Mark verified". More than 12 months ago (configurable) shows "Not recently verified". |
| `client_id` | UUID from the app, so a queued capture that's retried can't create two features. |
| `is_demo` | For demo cleanup. Also implied by the system. |

Custom permissions: `certify_feature` and `edit_feature`. A **Trail team** group gets both, so you can add
riders to the team without making them superusers.

### New: `FeatureMedia`
`feature`, `kind` (approach_photo, feature_photo, exit_photo, pov_clip), `file`, `caption`, `position`,
`client_id`, `uploaded_by`, `created_at`. Photos are resized on the server to a 2048 px long edge plus a
640 px thumbnail (Pillow). Feature media is visible to every signed-in rider, so nginx serves `/media/features/`
directly. Private rider videos stay behind X-Accel.

### New: `FeatureLog` (rider log entry)
`user`, `feature`, `outcome` (cleaned, sketchy, walked), `ridden_on` (rider's local date), `logged_at`,
`note`, optional `video`, optional `ride` FK, `client_id` (safe retries), and `grade_at_log` (snapshot, so
regrading a feature doesn't rewrite a rider's history or points). Riders can edit the note and delete their own
logs. Deleting a log adds correction entries for its points.

Derived per rider and feature, never stored: first clean date, clean count, best outcome, last outcome.

### New: `FeatureReport` (rider "this changed")
`feature`, `user`, `note`, optional `photo`, `created_at`, `status` (open, resolved, dismissed), `resolved_by`,
`resolved_at`. One tap in the app. Notes and photos are optional. Shown in the review queue.

### New: `GradingGuidelines` (single editable document)
One row: `body` (Markdown), `updated_at`, `updated_by`. Edited in the admin. Shown on the admin index and
beside the feature form, and in the app's team screens. Seeded from `trails/content/grading_guidelines.md`
(a first draft per type: what grade 1, 4, 7 and 10 look like for drops, jumps and so on).
**(confirm)** It's stored in the database, so non-developers can edit it without a deploy. Points rules stay in
a file, as the spec asks.

### `CustomUser` (users/, changed)
- `advanced_features` (bool, default False): unlocks suggestions above grade 7.
- `safety_accepted_at` and `safety_version`: when the rider accepted the safety notice at signup.

### Rules file (`progression/content/rules.json`, version 3)
```jsonc
"points": {
  "first_clean_per_grade": 20,
  "repeat_clean": 5,
  "repeat_cleans_per_feature_per_week": 3,
  "sketchy_per_grade": 5,          // once per feature
  "walked": 0,
  "trail_complete_bonus": 100,
  "ladder_complete_bonus": 150,
  "challenge_complete": 50,
  "drill_session": 0, "attempt_video": 0, "mastery_per_tier": 0, "weekly_streak": 0,
  "ride": 2, "descent_per_100m": 1, "jump": 1, "trail_pr": 10, "clean_climb": 15, "biggest_air": 10
},
"next_up": { "max_suggestions": 3, "repeat_cleans_needed": 2, "advanced_above_grade": 7 },
"verification": { "stale_after_months": 12, "second_reviewer_required": true },
"levels": { ... unchanged, retuned in phase 2 ... }
```
New ledger reasons: `first_clean`, `repeat_clean`, `sketchy`, `trail_complete`, `ladder_complete`. Sources:
`log:<id>`, `trail_complete:<trail>`, `ladder_complete:<system>:<type>`, so each pays out at most once.
Repeat-clean weeks are ISO weeks of the rider's local `ridden_on` date.

**(confirm)** Trail and ladder bonuses pay once. If the team later adds a feature, the rider doesn't lose the
bonus and doesn't get a second one.

---

## 4. Key rules, precisely

**Ladder.** For a trail system and type: certified and changed features, ordered by grade, then trail name,
then position. Closed features are hidden. Drafts are never shown to riders. A *rung* is a grade that exists in
the ladder.

**Rider's level in a type.** `H` = highest grade the rider has cleaned in that type, across all systems.
Grades are comparable everywhere thanks to the guidelines. A rider with no cleans has `H = 0`.

**Next up.** A feature is eligible when all of these hold:
1. It's certified (not changed, closed or draft), and the rider hasn't cleaned it.
2. `grade ≤ H + 1`. Never more than one grade above the rider's best.
3. **No skipped rungs:** for every rung below its grade in that system's ladder, the rider has cleaned *some*
   feature of that grade (in that type) **at least twice**. Repeat cleans of the same feature count.
4. `grade ≤ 7`, unless the rider has turned on advanced features.

Ranking: the type the rider is closest to finishing a rung in first, then trails they've ridden, then the
lowest grade. At most one suggestion per type is preferred, so the three suggestions are varied.

Each suggestion carries a plain reason, for example "You've cleaned grade 3 drops twice (Root Step, Ledge
Drop). This is a grade 4 drop on Lower Gully." Copy always says "Next up when you're ready". A test checks
suggestion text against banned phrases ("you should", "you need to", "easy", "just send it").

**(confirm)** Rule 3 reads "rungs below" as *grades* below, not *every feature* below. Requiring every grade-3
corner cleaned twice before any grade-4 corner would stall riders whose home trails don't include them all.

**Strengths.** Each log adds to every skill tag on its feature: cleaned = 1, sketchy = 0.5, walked = 0,
weighted by grade. A tag's score = earned / possible. Tags roll up to their skill branch (Drops, Air,
Cornering, Technical…). Strongest and weakest branches are shown once a branch has at least 3 logs. The weakest
links to "Stuck?" tips for its tags.

**Certification.**
- Draft → *submit for review* (any trail-team member) → *certify* (needs `certify_feature`, and with
  `second_reviewer_required` the certifier must be neither the creator nor the submitter).
- Certified → *flag changed* or *flag closed* (anyone on the team).
- Changed → re-certified (the second-reviewer rule applies again) or closed.
- Changed features stay visible with a "Changed since it was graded" notice. They can be logged but are left
  out of next-up.
- *Mark verified* updates `last_verified_at` without re-review.
- A rider report on a certified feature doesn't change its status. It goes in the review queue, and the team
  decides.

---

## 5. Screens

### Rider (tabs: Rides · Record · **Trails** · **Next up** · Progress)
1. **Trail systems** list, leading to the **system page**: map with trail lines and feature pins, the trail
   list with "cleaned 7 of 12 features", and links to ladders.
2. **Trail page:** features in riding order with thumbnail, type, grade chip and the rider's status (cleaned
   ×n, sketchy, walked, not yet), plus a "Log this trail" button.
3. **Feature page:** photo carousel (approach, feature, exit), POV clip, grade, measurements, how to ride it,
   what can go wrong, **ride-around (always shown when present)**, the rider's history, **Stuck?** (tips and
   optional drills from the tagged skills), "Report a change", and the **safety notice**. Shows "Not recently
   verified" when stale and the changed notice when changed.
4. **Log:** three big buttons on the feature page (Cleaned it · Rode it, sketchy · Walked it). "Log this trail"
   lists every feature with the same three buttons and saves in one request. Logs queue offline like rides.
5. **Ladders:** pick a system and type to see the rungs in grade order with the rider's status.
6. **Next up:** 1–3 suggestions with reasons, plus the secondary climb/PR/air goals.
7. **Progress:** level and points, features cleaned by type, strongest and weakest skill areas, recent
   activity, and points history.
8. **Share card:** after a first clean, a sheet with the generated card and Share (expo-sharing).
9. **Settings:** an "Advanced features (above grade 7)" toggle with a short safety note.
10. **Signup:** the safety notice with an "I understand" checkbox.

### Team (shown only to Trail team members)
1. **Add feature on site** (target: under 3 minutes). It picks the nearest trail automatically and captures the
   GPS point with an accuracy readout. Three photo buttons (approach, feature, exit) use the camera through
   expo-image-picker at reduced quality. Then type and grade chips, measurement fields for the chosen type,
   and Save draft. Everything else (how to ride, tags, ride-around) is optional on site and filled in later.
2. **Offline queue:** the draft and photos are saved to files and uploaded when there's signal. The feature
   uses its `client_id` and each photo has its own. A queue badge shows "2 features waiting to upload".
3. **Review queue:** drafts awaiting certification, changed features, open rider reports, and stale features.
   Actions: certify, flag changed or closed, mark verified, resolve a report.
4. The grading guidelines, readable in the app.

### Admin (computer)
- Feature form with media inline (**POV clip upload** happens here), skill-tag picker, and the guidelines
  beside it.
- **Bulk trail view** at `/admin/trails/trail/<id>/features/`: features in riding order with up/down reorder,
  a per-type grade ladder, and warnings for missing rungs and draft or changed features.
- Report queue, the "Feature of the week" export action (zip: card image, photo, POV link, grade, how-to text),
  and the editable guidelines.

---

## 6. Sharing
- **Share cards** are generated on the server with Pillow on a first clean and cached per log. Two sizes:
  1080×1920 (Stories, TikTok) and 1080×1350 (Instagram feed). They show the feature photo, name, grade chip,
  trail, the rider's level and title, and a small Next Line mark in a corner. Fonts: Barlow, bundled (OFL
  licence).
- **Feature of the week:** an admin action that downloads the card, original photo and a text file with the
  name, grade, trail, how-to-ride text and the POV clip link.

## 7. Challenges
- New goal types: `next_features` ("clean N features you hadn't cleaned before, during the challenge") and
  `features` (clean every feature matching a filter: system, type, grade range).
- Seed **"Clean your next three features"**, 1–31 January 2027.
- The 30-day manual challenge is retired (end date in the past), and the sessions/master goal types are hidden
  in the app.

## 8. Safety
- Draft notice, marked **NEEDS LEGAL REVIEW** in `trails/content/safety.md` and in the admin:
  > Grades are our team's opinion of each feature on the day we rode it. Trails change with weather, wear and
  > rebuilds. You are responsible for judging every feature yourself, and for riding within your ability and
  > with the right gear. Look before you ride, and use the ride-around whenever you're unsure.
- Shown on every feature page and at signup. Acceptance is recorded with a version, and a new version asks
  again.
- Ride-around always shown when present. No pressure language (enforced by the copy test). Nothing above
  grade 7 is suggested unless advanced features are turned on.

---

## 9. Build phases

Each phase ends with all tests passing and one commit. I'll stop and report at the end of each.

| # | Phase | Main work | Tests |
|---|---|---|---|
| 1 | **Data model** | TrailSystem, Feature fields, status, FeatureMedia, FeatureLog, FeatureReport, GradingGuidelines, user fields, permissions and Trail team group. Data migration: kind→type, approved→status, FeatureProgress→FeatureLog, Ride.cleaned_features→FeatureLog. Basic admin. Add Pillow. | Migration mapping, ladder ordering, status visibility |
| 2 | **Points** | Rules v3, awards from logs (first clean, repeat with weekly cap, sketchy once, walked 0), trail and ladder bonuses, corrections on log delete, drill/video points off, levels retuned | Points and caps, ledger totals, bonuses pay once, append-only |
| 3 | **Certification (server)** | Team API: create draft (idempotent), media upload, submit, certify with the second-reviewer rule, flag changed/closed, verify, reports. Stale flag. Bulk trail admin view, guidelines in admin | Second-reviewer rules, setting off, changed/closed handling, stale, report queue |
| 4 | **Rider API** | Systems, trails, feature detail with Stuck? tips, single and batch logging, ladders, next-up, dashboard strengths, advanced setting, safety acceptance | Next-up (no skipping, repeat-clean requirement, grade-7 gate, changed excluded), strengths |
| 5 | **App: rider** | New tabs and screens from section 5, safety at signup and on features, skill tree removed | `node --test` for pure helpers (grade/status formatting, log batching) |
| 6 | **App: team** | On-site capture, offline feature/media queue, review queue | Offline queue tests (queue, retry, idempotent client_ids, partial photo failure) |
| 7 | **Sharing & challenges** | Share cards, feature-of-the-week export, new goal types, January challenge | Card renders at both sizes, challenge progress |
| 8 | **Demo, cleanup, docs** | Demo system (3 trails, about 30 features, generated placeholder images) and demo rider; `seed_features_demo` / `seed_features_demo --remove`; drop FeatureProgress and Ride.cleaned_features; README on certification, guidelines, rules and demo removal | Seed then remove leaves nothing behind |

### Deploy notes
- Server: `pip install` (Pillow), `migrate`, `seed_progression`, and an nginx `location /media/features/`
  block plus a larger upload limit for the team media endpoint and the admin (for POV clips).
- App: **no new native modules are planned.** Camera (expo-image-picker), files (expo-file-system), sharing
  (expo-sharing) and maps are already installed, so existing dev and TestFlight builds keep working over the
  air. If a phase needs a new native module, I'll call it out first.

### Risks
- **Grades drifting between team members.** The guidelines and the bulk ladder view mitigate this. The second
  reviewer is the main guard.
- **Next-up being too strict on small trail systems.** If a system lacks a rung, rule 3 only checks rungs that
  exist, so a missing grade doesn't block anyone.
- **Media storage on the droplet's disk.** Photos are resized, and POV clips are the main cost (about 20–40 MB
  each). Fine for a few hundred features. Moving to object storage (DigitalOcean Spaces) later is a settings
  change.
