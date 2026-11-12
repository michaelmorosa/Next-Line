# Next Line

A mountain bike app for riders who keep their phone in a pocket. Tap Record, ride, and Next Line finds your
descents, jumps, airtime, PRs and flow, then tracks how you progress on each trail. The design is in
`MTB Progress App.html`.

Progress is measured on real trail features (drops, jumps, corners, rock gardens…) that the Next Line team
photographs, grades and certifies. Riders log how each one went and get "next up when you're ready" suggestions.
See [Trail features and progression](#trail-features-and-progression).

- `backend/nextline`: Django REST API with PostgreSQL. Ride processing, trails, graded features, certification,
  points, scoring and crash alerts.
- `frontend/nextline`: React Native app with Expo (SDK 58). Recording, trail systems, feature pages, logging,
  next up, progress, and the trail team's capture and review screens.

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
| `GET/PATCH /api/user/me/` | Account, crash-alert contact, `advanced_features`, safety notice acceptance (`safety_version`), and whether the rider is on the trail team |
| `POST /api/rides/` | Upload a recording: `{client_id, started_at, elapsed_s, track: [[t, lat, lng, alt, speed]], jumps: [{t, airtime_s}]}`. Repeat uploads with the same `client_id` are ignored. |
| `GET /api/rides/`, `GET/DELETE /api/rides/{id}/` | Ride list and summary (stats, efforts, PRs, speed rank, the features on the trails ridden, points earned) |
| `POST /api/rides/{id}/checkin/` | Confidence 1–5, crashed, touchdowns, notes. Features are logged separately. |
| `GET /api/trails/`, `GET/PATCH /api/trails/{id}/` | Your timed trails with laps and times. You can rename and rate auto-detected trails. |
| `GET /api/progress/` | Rider level (points, title, bar), `features` (next up, cleaned by type, strengths, recent activity), challenges, riding goals, flow and climbing trends, favorite descent and climb, totals, ride streak, achievements |
| `GET /api/level-rules/` | Point sources and caps and the level/title table, for the "How points work" screen |
| Trail systems, features, logging, next up, the trail team | See [API](#api-1) under Trail features |
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
- **Points from rides** (`progression/ride_xp.py`): each ride earns a few points: for the ride, for metres
  descended and jumps (both capped per day), for trail PRs, a new biggest air and a first clean climb. Most points
  come from features. See [Points and levels](#points-and-levels) for the values.
- **Achievements** (`rides/achievements.py`) are one-off milestones saved with the date earned. There are 17 of
  them, such as first jump, one second of air, first black-diamond feature, mastering a trail, a clean climb,
  300 m non-stop, a 1,000 m climbing day, 10,000 m descended, 10 laps of one trail, and a 4-week streak. They're
  awarded after uploads, check-ins and feature logs.

## Trail features and progression

Progress is measured on real trail features: one specific drop, jump, corner, rock garden or steep section. The
Next Line team photographs and grades each one. Riders log how each feature went with one tap, and the app
suggests what to ride next. There's no skill tree in the app; skills work behind the scenes as tags, tips and
strengths.

- **Trail systems** group shared trails (Admin → Trail systems; set each trail's system on the trail page).
- **Features** belong to a shared trail and have a type (drop, jump, corner, rock garden, roots, steep, skinny,
  climb, other) and a **grade from 1 to 10 within that type**. They also have measurements, a GPS point, riding
  order, how to ride it, what can go wrong, an optional ride-around with its own grade, skill tags, photos
  (approach, feature, landing or exit) and a POV clip.
- **Ladders:** every feature of one type at a trail system, in grade order. Each grade is a rung.
- **Logs:** a rider's "cleaned it", "rode it, sketchy" or "walked it" on a feature, with a date and an optional
  note. Clean counts, first cleans, statuses and strengths are all worked out from logs.

The code is in `backend/nextline/trails/` (features, certification, ladders, logging, share cards) and
`backend/nextline/progression/` (points, levels, challenges).

### Certifying features

A feature is only shown to riders once it's **certified**, and certifying takes a second person.

1. **Add it on site** (app → Trails → *Add a feature*). GPS starts when the screen opens and keeps the most
   accurate fix; wait for ±30 m or better. Tap to take the approach, feature and landing photos, pick a type and a
   grade, add the drop height, gap or steepness if it applies, and save. The nearest trail is used unless you pick
   one. The draft and photos are saved on the phone first and upload when there's signal, so poor reception never
   loses a capture. Each upload step is safe to retry. Captures the server rejects (for example, too far from any
   trail) stay in the review queue with the reason, for you to fix or remove.
2. **Fill in the rest later**, from the app (*Review* → the feature) or the admin (Admin → Features): how to ride
   it, what can go wrong, the ride-around, skill tags, and the **POV clip, which you upload from a computer** in
   the admin's media section on the feature.
3. **Submit it for review** (app or admin action).
4. **Certify it.** This needs a grade, at least one photo, the *certify* permission and, with
   `verification.second_reviewer_required` on (the default, in `rules.json`), someone who neither added nor
   submitted it. Certifying sets the verified date. Certified grades and types are locked.
5. **Keep it current.**
   - **Changed** (rebuilt, storm damage): riders still see it, with a "changed since we graded it" notice. It isn't
     suggested in next up, and it can be regraded. Then submit and certify it again; the second-reviewer rule
     applies again.
   - **Closed:** hidden from riders. *Reopen* makes it a draft again.
   - **Mark verified:** someone checked it and it's as graded. Features not verified in
     `verification.stale_after_months` (12) show "Not recently verified" to riders and appear in the review queue.
   - **Rider reports:** riders tap *Report a change* on a feature page (with an optional note). Reports go to the
     review queue and Admin → Feature reports; they don't change the feature. Resolve or dismiss each one after
     looking.

**Setting up the team.** Add people to the **Trail team** group (Admin → Users → the user → Groups). That gives
them the team screens in the app and the permissions to add, edit and certify features. Also tick *Staff status*
if they'll use the admin from a computer. To let someone add features but not certify them, remove the
"Can certify features" permission from their account or make a second group without it.

**Bulk trail view.** Admin → Trails → *Order and ladders* (in the trail list) shows a trail's features in riding
order with up and down buttons, and the trail system's ladders with warnings. It warns when a grade is skipped
("no grade 4 between 3 and 5: riders will stall at 3"), when a ladder doesn't start at grade 1 (new riders only
get grade 1 suggested), and when a feature has no grade.

### Grading guidelines

One shared document so grades stay consistent between team members: Admin → Grading guidelines. It's Markdown.
The team can read it in the app (*Add a feature* → Guidelines) and beside every feature in the admin. It starts
from `trails/content/grading_guidelines.md` the first time it's opened; after that, the admin copy is the one
that counts.

### Logging, ladders and next up

- **One tap per feature** on its page, or **Log this trail** to mark every feature in riding order after a ride
  (ride summaries link to it for each trail ridden). Logs made without signal wait on the phone and send later;
  each has a `client_id`, so sending one twice keeps one.
- **Next up** (`trails/ladders.py`) suggests up to 3 features. A feature is suggested only when:
  1. it's certified (not changed, closed or draft) and the rider hasn't cleaned it;
  2. it's at most **one grade above** the highest grade the rider has cleaned in that type, anywhere;
  3. for **every rung below it** in its ladder, the rider has cleaned some feature of that grade **at least
     twice** (repeat cleans of one feature count), so rungs are never skipped;
  4. it's **grade 7 or below**, unless the rider turned on *Advanced features* in Settings.

  Features the rider rode sketchy come first, then step-ups, then trails they've ridden. Suggestions are spread
  over different types. Each one says why, in plain words, and the copy is "next up when you're ready". A test
  checks that the reasons never use pushy phrases.
- **Strengths** (`trails/strengths.py`): each log counts toward the skills its feature is tagged with (or the
  defaults for its type), weighted by grade: cleaned 1, sketchy ½, walked 0. Skills roll up to areas (Drops,
  Cornering…). Progress shows the strongest and weakest once an area has 3 logs, and the weakest names skills to
  look up under "Stuck?" on feature pages.
- **"Stuck?" tips** on a feature page come from its skill tags in `progression/content/skills.json`: what the
  skill is, why it helps, optional drills, and "you've got it when". The 50 skills are kept as they were.

### Points and levels

Every award goes into an append-only ledger (`XPEntry`, shown as "points"). Totals and levels are always added up
from it. Each entry records the feature and log that earned it and the rules version. Entries can't be edited or
deleted; deleting a log or a ride adds correction entries.

| Earned for | Points | Limit |
|---|---|---|
| First clean of a feature | 20 × grade | once per feature |
| Cleaning it again | 5 | 3 per feature per week (ISO week of the ride date) |
| Rode it, sketchy | 5 × grade | once per feature |
| Walked it | 0 | logged, no judgment |
| Every certified feature on a trail (3+) | 100 | once per trail |
| Every certified feature of one type at a trail system (3+) | 150 | once per ladder |
| Completing a challenge | 50 | once |
| Trail PR | 10 | each time you beat your best |
| First clean climb of a trail | 15 × trail difficulty | once per climb |
| New biggest air | 10 | each new best |
| Metres descended | 1 per 100 m | 15 a day |
| Jumps | 1 each | 10 a day |
| A ride | 2 | |

- Points use the grade **when the log was made** (`grade_at_log`), so regrading a feature never changes past
  points. Ladders and next up use the current grade.
- Logs on a feature that isn't live yet earn points once it's certified (the next time the rider opens Progress).
- Drill sessions, attempt videos, skill mastery and practice weeks are worth 0 now. Their code and API are kept
  (`/api/skills/…`) but the app doesn't use them. Points already earned from them stay in the ledger.
- **Levels:** level 2 needs 100 points, and each level after needs 22% more (20 levels). Titles cover two levels
  each: PQ Punk, Gravel Grom, Berm Burner, Root Rattler, Flow Fiend, Drop Dog, Gap Goblin, Sedona Shredder,
  Whistler Whipper, Line Legend.

### Editing point rules

Everything is in `backend/nextline/progression/content/rules.json`:

| Section | What's in it |
|---|---|
| `xp` | Every point value: `first_clean_per_grade`, `repeat_clean`, `sketchy_per_grade`, `walked`, `trail_complete`, `ladder_complete`, ride values |
| `caps` | `repeat_cleans_per_feature_per_week` and the daily ride caps |
| `bonuses` | `min_features` a trail or ladder needs before completing it pays |
| `next_up` | `max_suggestions`, `repeat_cleans_needed`, `advanced_above_grade` |
| `verification` | `second_reviewer_required`, `stale_after_months` |
| `levels`, `titles` | The level curve and titles |

1. Edit the file and bump `"version"` if you change point values. Each ledger entry records the version it was
   earned under, and points already earned don't change.
2. Run `python manage.py validate_progression`. The same checks run on `migrate`, `runserver` and `test`, so a
   broken file stops them.
3. Restart the server (`systemctl restart nextline`). The app doesn't need a new build.

### Safety notice

The wording is in `backend/nextline/trails/content/safety.json` and is marked **needs legal review**
(`"needs_legal_review": true`). It shows on every feature page and trail page, and riders accept it when they sign
up. Only the trail team sees the "needs legal review" note in the app.

- After legal review, edit the text and set `needs_legal_review` to `false`.
- If the meaning changes, bump `version`. Every rider then has to accept the new notice before using the app.

The ride-around is always shown on a feature page when there is one, and nothing above grade 7 is suggested
without the rider turning on advanced features.

### Share cards and feature of the week

- Every **first clean** opens a share card: the feature photo, its name, a grade badge, type and trail, the
  rider's level, and a small Next Line mark. It comes in two sizes: 1080×1920 for Stories and TikTok, and
  1080×1350 for Instagram posts. It's drawn on the server (`trails/share.py`, Pillow, Barlow fonts under the OFL in
  `trails/fonts/`) at `GET /api/logs/{id}/share-card/?size=story|feed`.
- **Feature of the week:** Admin → Features → select one → *Export as feature of the week*. You get a zip with the
  card in both sizes, the original photo, and `post.txt`: name, grade, trail, how to ride it, ride-around, the POV
  clip link and a safety line.

### Challenges

A challenge has dates and a goal:
- **next_features:** clean N features you hadn't cleaned before joining ("Clean your next three features").
- **features:** clean every certified feature matching a trail system, a type and a grade range ("Clean every
  grade 3 corner at Cedar Hollow"). The goal count is however many features match.

Only cleans logged after joining and inside the dates count. Challenges show in the app up to 45 days before they
start. They're seeded from `progression/content/challenges.json` with `seed_progression`, then edited in the
admin (Admin → Challenges: set the system, feature type and grade range there). The launch challenge,
**"Clean your next three features"**, runs from 1 to 31 January 2027.

### Demo data

```bash
python manage.py seed_features_demo                    # Cedar Hollow (demo) + demo rider; prints the password
python manage.py seed_features_demo --password secret  # choose the rider's password
python manage.py seed_features_demo --remove           # remove all of it
```

This creates a made-up trail system, **Cedar Hollow (demo)**, with 3 trails (green, blue, black) and 31 certified
features. They cover 8 types and grades 1–8, have placeholder photos marked DEMO, and include ride-arounds, one
changed feature and one not verified in over a year. It also creates two demo team members and a rider, `demo`,
with eight weeks of logs: cleans, sketchy goes and walks, a completed trail, and suggestions waiting.

`--remove` deletes the demo trail system, its trails, features and photo files, and the demo users with their
logs and points. Nothing else is touched. Running the command without `--remove` recreates everything from
scratch.

### Commands

```bash
python manage.py validate_progression   # check the content files
python manage.py seed_progression       # create or update challenges from challenges.json
python manage.py backfill_xp            # points for past rides and logs on features certified since (safe to re-run)
python manage.py seed_features_demo     # demo data; --remove to delete it
```

### API

Rider endpoints:

| Endpoint | What it does |
|---|---|
| `GET /api/systems/`, `GET /api/systems/{id}/` | Trail systems with "cleaned N of M"; one system with trails (paths for the map), feature pins, ladder summary and next up there |
| `GET /api/systems/{id}/ladders/` | Each type's rungs, with the rider's status on every feature |
| `GET /api/trails/{id}/features/` | A trail's features in riding order |
| `GET /api/features/{id}/` | A feature page: photos, POV clip, measurements, ride-around, notices, the rider's history, "Stuck?" tips, safety notice |
| `POST /api/features/{id}/log/` | `{outcome: cleaned\|sketchy\|walked, ridden_on?, note?, client_id?, ride?}`. Returns points, `first_clean`, the level before and after, new achievements. Repeats with the same `client_id` return the first. |
| `POST /api/logs/batch/` | "Log this trail": `{ridden_on?, ride?, logs: [{feature, outcome, client_id?, note?}]}` |
| `PATCH/DELETE /api/logs/{id}/` | Edit a log's note, or delete it (its points are corrected) |
| `GET /api/logs/{id}/share-card/?size=story\|feed` | The share card JPEG for one of the rider's cleans |
| `POST /api/features/{id}/report/` | Report a change: `{note?}` or multipart with `photo` |
| `GET /api/next-up/` | Next up (`?system=` for one system) with reasons |
| `GET /api/safety/` | The safety notice |
| `GET /api/xp/` | The points ledger, newest first (`?before=<id>` for more) |
| `GET /api/challenges/`, `POST /api/challenges/{id}/join/` | Challenges with the rider's progress |

Trail team endpoints (team members only):

| Endpoint | What it does |
|---|---|
| `GET /api/team/features/` | The review queue: awaiting review, drafts, changed, reported, stale |
| `POST /api/team/features/` | Capture a draft `{client_id, type, grade, lat, lng, trail?, name?, drop_height_m?, …}` |
| `GET/PATCH/DELETE /api/team/features/{id}/` | One feature with what's stopping it being certified; edit it; delete a draft |
| `POST /api/team/features/{id}/media/` | Multipart `kind` (approach, feature, exit, pov), `file`, `client_id`, `caption?`. Photos are resized to 2048 px with a 640 px thumbnail, and their location data is removed. |
| `POST /api/team/features/{id}/submit/`, `/certify/`, `/flag/` `{status: changed\|closed}`, `/reopen/`, `/verify/` | The workflow |
| `POST /api/team/reports/{id}/resolve/` | `{status: resolved\|dismissed}` |
| `GET /api/team/trails/?lat=&lng=` | Shared trails, nearest first |
| `GET /api/team/guidelines/` | The grading guidelines |

### Deploying it

After pulling, on the server:

```bash
cd /srv/nextline
sudo -u nextline git pull
sudo -u nextline env/bin/pip install -r backend/nextline/requirements.txt   # adds Pillow
cd backend/nextline
sudo -u nextline ../../env/bin/python manage.py migrate
sudo -u nextline ../../env/bin/python manage.py seed_progression
sudo -u nextline ../../env/bin/python manage.py collectstatic --noinput
sudo -u nextline mkdir -p /srv/nextline/media
systemctl restart nextline
```

The migration turns existing features into drafts with the new types (gap → jump, berm → corner, technical →
other) and copies riders' old feature progress into logs. Give each feature a grade and certify it before riders
see it again.

`backend/nextline/.env` needs:

```
MEDIA_ROOT=/srv/nextline/media
USE_X_ACCEL_REDIRECT=True
```

Add these to the nginx site's `server` block for the API (the one with `listen 443`), then run
`nginx -t && systemctl reload nginx`:

```nginx
# Feature photos and POV clips are public; riders' own videos stay private (below).
location /media/features/ {
    alias /srv/nextline/media/features/;
    expires 7d;
}

# Photos from the team's phones and POV clips from the admin need a bigger upload limit.
location ~ ^/api/team/features/[0-9]+/media/$ {
    client_max_body_size 300M;
    proxy_pass http://unix:/run/nextline/nextline.sock;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
}
location ~ ^/(admin|[^/]+)/trails/feature/ {
    client_max_body_size 300M;
    proxy_pass http://unix:/run/nextline/nextline.sock;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
}
location ~ ^/api/features/[0-9]+/report/$ {
    client_max_body_size 30M;
    proxy_pass http://unix:/run/nextline/nextline.sock;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Riders' private videos: served after Django checks who's asking.
location /protected-media/ {
    internal;
    alias /srv/nextline/media/;
}
```

The admin rule matches `ADMIN_URL`, whatever you set it to. Photos and clips are stored on the droplet's disk.
Phone photos are resized to about 0.5 MB, and POV clips are the main cost (roughly 20–40 MB each).

**The app needs no new native modules** (camera, files, sharing and maps were already in it), so an existing
development or TestFlight build only needs the new JavaScript: restart `npx expo start`, or push a new build as
usual.

## Sharing trails

Riders' auto trails are private: only they see them. Shared trails are where features live, and what lets riders
compare times (speed rank).

To share a trail, ride it with the app yourself. Then in the Django admin, go to **Trails**, select it, and run
**"Make shared, merging riders' copies of it"** (`trails/sharing.py`). This:

- makes the trail shared (no owner)
- finds every rider's private copy: same direction, both ends within 60 m, similar length
- moves their laps onto the shared trail, drops laps counted twice, and recalculates PRs
- moves any features on the copies across as drafts. Features within 15 m of an existing one are merged, and
  riders' logs move with them.
- deletes the empty copies

Afterwards, set the trail's name, difficulty and trail system, then grade and certify its features.

## App

Requires Node 20+.

```bash
cd frontend/nextline
npm install
cp .env.example .env            # API_URL=http://<your LAN IP>:8000
npx expo start
npm test                        # detectors, logging and capture queues, feature helpers
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

- Video clips from rides, and riders attaching their own video to a log (the API field exists; the app doesn't
  offer it yet)
- Coach accounts
- Share cards for whole rides (feature first cleans have them; the ride share button sends text)
- Editing skill tags from the app (the admin has them)
- Friends confirming milestones, and leaderboards
- Strava, Garmin and Apple Health import
- Precision mode with a watch or bar mount
- A local notification for the crash prompt when the app is in the background
- Email activation screens. Sign-up activates immediately unless `SEND_ACTIVATION_EMAIL=True`.
- App icons and a splash image
