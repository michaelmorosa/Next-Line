# Next Line

A mountain bike app for riders who keep their phone in a pocket. Tap Record, ride, and Next Line finds your
descents, jumps, airtime, PRs and flow, then tracks how you progress on each trail. The design is in
`MTB Progress App.html`.

- `backend/nextline`: Django REST API with PostgreSQL. Ride processing, trails, scoring and crash alerts.
- `frontend/nextline`: React Native app with Expo (SDK 58). Recording, ride summary, trails and progress screens.

## Backend

Requires Python 3.12 and PostgreSQL.

```bash
# From the repo root
python -m venv env
env/Scripts/activate            # macOS/Linux: source env/bin/activate
pip install -r backend/nextline/requirements.txt

# Create the database (psql as the postgres superuser)
psql -U postgres -c "CREATE ROLE nextline LOGIN PASSWORD 'change-me';"
psql -U postgres -c "CREATE DATABASE nextline_db OWNER nextline;"

cd backend/nextline
cp .env.example .env            # then set DJANGO_SECRET_KEY, DATABASE_PASSWORD, and HOST
python manage.py migrate
python manage.py createcachetable
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

`HOST` must include your computer's LAN IP so a phone can reach it.

Tests run on Postgres by default. To run them without a database server:

```bash
DATABASE_ENGINE=sqlite python manage.py test
```

### API

All endpoints need a JWT (`Authorization: Bearer …`) except sign-up and log-in.

| Endpoint | What it does |
|---|---|
| `POST /api/auth/users/`, `POST /api/auth/jwt/create/`, `/jwt/refresh/` | Sign up, log in, refresh (djoser + simplejwt) |
| `GET/PATCH /api/user/me/` | Account and crash-alert contact |
| `POST /api/rides/` | Upload a recording: `{client_id, started_at, elapsed_s, track: [[t, lat, lng, alt, speed]], jumps: [{t, airtime_s}]}`. Repeat uploads with the same `client_id` are ignored. |
| `GET /api/rides/`, `GET/DELETE /api/rides/{id}/` | Ride list and summary (stats, efforts, PRs, speed rank, features for check-in) |
| `POST /api/rides/{id}/checkin/` | Confidence 1–5, crashed, and features cleaned or almost cleaned |
| `GET /api/trails/`, `GET/PATCH /api/trails/{id}/` | Your trails with times and feature mastery. You can rename and rate auto-detected trails. |
| `POST /api/trails/{id}/features/` | Pin a feature (it must be within 100 m of the trail) |
| `PUT /api/features/{id}/progress/`, `DELETE /api/features/{id}/` | Set a feature to cleaned, almost or locked. Remove a pin you made. |
| `GET /api/progress/` | Rider level (XP, title, bar), practice streak, skills mastered and next up, challenges, recent XP, trail goals worth XP, flow and climbing trends, favorite descent and climb, totals, ride streak, achievements |
| `GET /api/level-rules/` | XP sources and caps, difficulty weights and the level/title table, for the "How rider level works" screen |
| Skills, XP history, challenges | See [Progression](#progression-skill-tree-xp-and-levels) |
| `POST /api/crash-alerts/` | Text the emergency contact (Twilio; see `.env.example`) |

### How rides are scored

- **Climb/descent and moving time** come from the GPS track (`rides/analysis.py`). Altitude is smoothed and
  changes under 3 m are ignored. Time spent below 1 m/s doesn't count, which acts as auto-pause.
- **Descents and climbs** are elevation changes of 30 m or more over at least 200 m. A descent must last 20
  seconds and a climb 30 seconds. Reversals of up to 8 m don't split one. A climb that spans a GPS gap, or rises
  faster than 2,000 vertical m/hour, is treated as a shuttle or chairlift and not counted.
- **Segments** (`rides/segments.py`): each descent and climb is matched to a trail whose start and end the track
  passes within 40 m of. Trails have a direction (`descent` or `climb`). Anything that doesn't match becomes a
  private auto trail ("Unnamed climb 3"), and auto trails appear in the app once ridden twice. Shared trails are
  added in the Django admin. Climb laps get a climb rate instead of a flow score, and PRs are counted separately
  for descents and climbs.
- **Climbing stamina** (`analysis.climbing_stamina`):
  - **Climb rate:** vertical metres per hour on climbs.
  - **Pace held:** the climb rate over the second half of the ride's climbing as a % of the first half. It needs
    at least 4 minutes of climbing.
  - **Longest non-stop climb:** the most vertical gained without a rest, which is a stop of 15 s or more.
  - **Rests:** the number of rest stops on climbs.

  Progress shows 8-week trends of these.
- **Full laps** are complete start-to-finish runs of a trail; partial runs don't count. Riding a descent twice in
  one ride is 2 laps on one trail, and loop trails (start = finish) count each time round.
- **Touchdowns** (times you put a foot down) are estimated, because a pocketed phone can't feel your foot. The
  count is stops on descents and timed laps, climbs included: speed under about 3 km/h, back to riding within 15
  seconds. Longer stops count as rests, and stopping at the bottom isn't counted. A lap with none is a
  **clean lap**. Riders can correct the ride's count in the check-in.
- **Flow** is 100 × (1 − coefficient of variation of speed) on descents. It's shown as your own trend, never ranked.
- **Jumps** are detected on the phone, because raw accelerometer data is too big to upload. The server keeps
  airtimes between 0.15 and 3 s.
- **XP from rides** (`progression/ride_xp.py`): each ride earns a little XP. There's XP for the ride, for metres
  descended and jumps (both capped per day), for trail PRs, a new biggest air and a first clean climb, and for
  features cleaned in the check-in. See [Progression](#progression-skill-tree-xp-and-levels) for the values.
- **Achievements** (`rides/achievements.py`) are one-off milestones saved with the date earned. There are 17 of
  them, such as first jump, one second of air, first black-diamond feature, mastering a trail, a clean climb,
  300 m non-stop, a 1,000 m climbing day, 10,000 m descended, 10 laps of one trail, and a 4-week streak. They're
  awarded after uploads, check-ins and feature updates.

## Progression: skill tree, XP and levels

The skill tree is the map: what a rider has mastered, what's ready to learn next and what's still locked. XP is
the fuel: riders earn most of it by practising and mastering skills, so they feel progress during the weeks a hard
skill takes. Rider level comes from total XP. The code is in `backend/nextline/progression/`.

### Skills

- There are 50 skills in 9 branches (Foundations, Climbing, Cornering, Wheel lifts, Air, Drops, Technical, Speed
  and lines, Mastery), across tiers 1–6. The longest chain is 8 skills, from Attack position to MTB Master.
- **MTB Master** is the final skill (`"capstone": true`). It needs the last skill of every branch, so a rider can
  only master it once they've mastered the whole tree. The validator checks this whenever the tree changes. Riders
  who master it get the `master_title` from `rules.json` ("MTB Master") in place of their level title.
- Each skill has:
  - a description and why it matters
  - 2–3 drills
  - a mastery test ("You've got it when…")
  - example media
  - tags that match trail feature kinds (`drop`, `jump`, `berm`…)
- A skill can need prerequisites from other branches. For example, Small drops needs Roll-offs **and** Manual.
- The text is a **draft** for a coach to review. Each skill has `"draft": true`, and the app shows a Draft tag
  until it's set to `false`.

A skill is in one of four states for each rider:
- **locked:** a prerequisite isn't mastered yet
- **ready:** every prerequisite is mastered
- **in progress:** at least one practice session or attempt video is logged
- **mastered**

A new rider sees the three Foundations skills as ready and everything else as locked. Locked skills can't be
practised.

**To master a skill**, the rider needs:
- 3 practice sessions, on at least 2 different days
- 1 attempt video
- to confirm in the app that they passed the mastery test

Staff can also mark a mastery **coach verified** in the admin (Masteries → "Mark as coach verified"). That shows a
badge, but it's never required.

### XP and levels

Every award goes into an append-only ledger (`XPEntry`). Each entry records the rider, the amount, the reason, the
skill or challenge, a source key and when it was earned. Totals and levels are always added up from the ledger;
nothing stores a total.

- Each source key (`session:812`, `ride:40:descent`, `streak:2026-W44`) can only pay out once.
- Entries can't be edited or deleted. A mistake is fixed with a negative `correction` entry, which you can add in
  the admin.
- Deleting a ride adds corrections for everything that ride earned.

| Earned for | XP | Limit |
|---|---|---|
| Logging a drill session | 10 | 3 per skill per day (more still count toward mastery) |
| Uploading an attempt video | 15 | 1 per skill per day |
| Mastering a skill | 100 × tier | once |
| Completing a challenge | 50 | once |
| A practice week (practice on 3+ days) | 25 | once a week |
| Cleaning a feature | 20 × trail difficulty | once per feature, approved features only |
| Trail PR | 10 | each time you beat your best |
| First clean climb of a trail | 15 × trail difficulty | once per climb |
| New biggest air | 10 | each new best |
| Metres descended | 1 per 100 m | 15 a day |
| Jumps | 1 each | 10 a day |
| A ride | 2 | |

- **Getting better pays more than riding more.** Riding volume is capped: metres and jumps add at most 25 XP a
  day, plus 2 per ride. PRs, a bigger air and cleaned features pay because they mean you improved. One tier-3 skill
  is worth 300.
- **Trail difficulty weights** are green and unrated ×1, blue ×2, black ×4, double black ×6. A rider's own rating
  of their auto trail counts as blue at most.
- **Levels:** level 2 needs 100 XP, and each level after that needs 22% more than the one before (20 levels).
  Level 20 (about 19,400 XP) is roughly what mastering the whole tree earns.
  Titles cover two levels each: PQ Punk, Gravel Grom, Berm Burner, Root Rattler, Flow Fiend, Drop Dog, Gap Goblin,
  Sedona Shredder, Whistler Whipper, Line Legend.
- **Practice streak:** consecutive weeks with practice on 3 or more days. Days are the rider's local date, sent by
  the app. The ride streak (any ride that week) is separate.

### Challenges

A challenge has:
- target skills
- start and end dates
- a goal: log N sessions, or master the skills

Riders join a challenge, and only practice after they join counts toward it. The example is the **30-day manual
challenge**: log 10 Manual sessions in 30 days. Challenges are created from `content/challenges.json` with
`seed_progression`, then edited in the admin.

### Editing skills, points and challenges

The content is three JSON files in `backend/nextline/progression/content/`:

| File | What's in it |
|---|---|
| `skills.json` | Branches and skills: text, drills, mastery test, tier, prerequisites, media, tags, draft flag |
| `rules.json` | Every XP value, daily caps, mastery requirements, streak rule, level curve and titles, video limits |
| `challenges.json` | Challenges to seed |

1. Edit the file. Bump its `"version"` when you change point values, since each ledger entry records the rules
   version it was earned under.
2. Validate it:
   ```bash
   python manage.py validate_progression
   ```
   This checks for missing fields, unknown prerequisites, prerequisite cycles (it prints the cycle path), bad tiers
   and branches, the number of drills, sane rules and valid challenges. It also warns about unknown tags, or a skill
   that's easier than its prerequisite. The same checks run as a Django system check and in the test suite, so
   invalid content stops `migrate`, `runserver` and `test`.
3. Restart the server (`systemctl restart nextline`). The app reads the tree from the API, so it doesn't need a new
   build.

Skills are identified by their `id`. Don't rename an id once riders have practised it; change its `name` instead.
Changing point values doesn't change XP that was already earned.

### Commands

```bash
python manage.py validate_progression     # check the content files
python manage.py seed_progression         # create or update challenges from challenges.json
python manage.py backfill_xp              # give existing riders the XP their rides and cleaned features earned (safe to re-run)
python manage.py seed_progression_demo    # demo rider "demo" with 6 weeks of history; prints the password
```

The demo rider has:
- 6 skills mastered
- Manual ready for its mastery test, and Flat corners started
- a 5-week practice streak
- the manual challenge at 6/10
- three rides

Running the command again recreates the demo rider from scratch.

### API

| Endpoint | What it does |
|---|---|
| `GET /api/skills/` | The tree: branches, every skill with the rider's state and counts, layout depth, next up (1–3 skills), level and streak |
| `GET /api/skills/{id}/` | One skill: content, state, mastery requirements, `history` (sessions), `attempt_videos`, what it unlocks, and nearby trail features with matching tags (`?lat=&lng=`, otherwise near the rider's latest ride) |
| `POST /api/skills/{id}/sessions/` | Log a drill session `{client_id, practiced_on, drill_index?, note?}`. Returns the XP earned (or `capped`), the skill's new state, level and streak. Repeats with the same `client_id` are ignored. |
| `POST /api/skills/{id}/attempts/` | Upload an attempt video (multipart: `video`, `client_id`, `practiced_on`, `duration_s?`). MP4 or MOV, up to 100 MB and 60 s. |
| `POST /api/skills/{id}/master/` | `{confirmed_test: true}` once eligible. Returns the XP, newly unlocked skills, and the level before and after. |
| `GET /api/attempts/{id}/video/` | The rider's own attempt video; other riders get a 404 |
| `GET /api/xp/` | The XP ledger, newest first, 50 at a time (`?before=<id>` for more) |
| `GET /api/challenges/`, `POST /api/challenges/{id}/join/` | Running challenges with the rider's progress |

### Deploying it

After pulling, on the server:

```bash
sudo -u nextline env/bin/pip install -r backend/nextline/requirements.txt
cd backend/nextline
sudo -u nextline ../../env/bin/python manage.py migrate
sudo -u nextline ../../env/bin/python manage.py seed_progression
sudo -u nextline ../../env/bin/python manage.py backfill_xp
sudo -u nextline mkdir -p /srv/nextline/media
```

Then add these to `backend/nextline/.env`:

```
MEDIA_ROOT=/srv/nextline/media
USE_X_ACCEL_REDIRECT=True
```

Attempt videos need two changes to the nginx site:

- a larger upload limit, for the upload path only
- an internal location, so nginx serves video files after Django has checked that the rider owns them

```nginx
location ~ ^/api/skills/[^/]+/attempts/$ {
    client_max_body_size 110M;
    proxy_pass http://unix:/run/nextline/nextline.sock;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
}

location /protected-media/ {
    internal;
    alias /srv/nextline/media/;
}
```

Finish with `nginx -t && systemctl reload nginx` and `systemctl restart nextline`. Videos are stored on the droplet's
disk; a 60 s clip at 720p is roughly 10–40 MB.

The app added `expo-image-picker` and `expo-video`, so installed builds need a new EAS build. Expo Go works as it is.

## Sharing trails

Riders' auto trails are private: only they see the trail and its features. Shared trails are what let riders
compare times (speed rank) and see features others pinned. Their difficulty counts in full toward XP: black and
double-black weights need a shared trail.

To share a trail, ride it with the app yourself. Then in the Django admin, go to **Trails**, select it, and run
**"Make shared, merging riders' copies of it"** (`trails/sharing.py`). This:

- makes the trail shared (no owner)
- finds every rider's private copy: same direction, both ends within 60 m, similar length
- moves their laps onto the shared trail, drops laps counted twice, and recalculates PRs
- moves their features across; features within 15 m of an existing one are merged, keeping each rider's best
  progress and fixing up their check-ins
- deletes the empty copies

Afterwards, set the trail's name and difficulty and review any features that were moved in. Riders who ride it
later are timed on the shared trail directly.

### Approving features

Riders can pin features on any trail they can see.

- **On their own private trail,** a pin is live at once, since only they see that trail.
- **On a shared trail,** a rider's pin waits for approval. Until then only that rider sees it and can track it, and
  it earns no XP or achievements. That stops anyone from pinning made-up features on a black trail to level up.
  Once it's approved, riders who already cleaned it get the XP the next time they open Progress.
- **Pins by staff accounts** are live at once.

To review them, go to **Admin → Features** and filter by *approved = No*. From there:

- **Approve:** the feature goes live for everyone and starts counting.
- **Merge into the nearest approved feature** (within 40 m) for duplicates. The rider's progress and check-ins
  move to the existing feature.
- **Delete** to reject it.

Sharing a trail also marks riders' pins on it as waiting for approval.

## App

Requires Node 20+.

```bash
cd frontend/nextline
npm install
cp .env.example .env            # API_URL=http://<your LAN IP>:8000
npx expo start
npm test                        # jump/crash detector and skill tree layout tests
```

**Expo Go vs. a development build.** In Expo Go, recording only works while the app is open; on iPhone, Expo Go
can't record in the background at all. To record with the phone in your pocket, make a development build
(`eas build --profile development`) and allow location "Always". It's the same setup as Burrito Index.

### Recording

`recording/recorder.js` runs outside React, so GPS points from the background task keep arriving with the screen
off.

- GPS is sampled at about 1 Hz with fitness activity type. Fixes less accurate than 35 m are dropped.
- The accelerometer runs at 50 Hz. It uses total acceleration (orientation-agnostic), which feeds
  `recording/detectors.js`:
  - **Jump**: free fall below 0.4 g for 0.15–2.5 s, then a landing spike above 1.6 g, while moving.
  - **Crash**: an impact above 4.5 g, then 8 seconds of stillness. The app asks "You OK?" and counts down 60 s,
    then texts the contact.
- The in-progress ride is saved to a file every 15 s. If the app is killed, it comes back as "interrupted" so you
  can resume or save it.
- Finished rides wait in an offline queue and upload when there's signal.

### Validate jump detection first

Pocket jump detection is the riskiest assumption. Before trusting jump counts, go to **Settings → Sensor lab**,
log a ride with jumps you can count, and share the CSV. It holds every accelerometer sample with GPS, plus what the
detector found. Tune the thresholds in `recording/detectors.js` and re-run `npm test`.

## Not built yet

These are from the MVP plan:

- Video clips from rides (attempt videos on skills, compared side by side, are built)
- Coach and team accounts (coach verification is an admin action for now)
- Logging practice offline (sessions and attempts need a connection; retries are safe)
- Instagram summary card (the share button sends text for now)
- Friends confirming milestones, and leaderboards
- Strava, Garmin and Apple Health import
- Precision mode with a watch or bar mount
- A local notification for the crash prompt when the app is in the background
- Email activation screens. Sign-up activates immediately unless `SEND_ACTIVATION_EMAIL=True`.
- App icons and a splash image
