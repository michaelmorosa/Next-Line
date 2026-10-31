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
| `GET /api/progress/` | Rider level (with tier requirement), ways to level up, flow and climbing trends, favorite descent and climb, totals, streak, achievements |
| `GET /api/level-rules/` | The tiers, point sources and difficulty weights, for the "How rider level works" screen |
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
- **Rider level** (`rides/scoring.py`) only goes up, because it's built from bests and totals:
  - Cleaned features, weighted by trail difficulty
  - Best descent speed, from your **best 10** descents only
  - Biggest air and jump count
  - Metres descended
  - Climbing: 30 points × difficulty for each climb ridden with no foot down, plus a capped share for fitness.
    Your best climb rate gives up to 250 points (at 1,200 m/hour) and your longest non-stop climb up to 150.

  Difficulty weights are green and unrated ×1, blue ×2, black ×4, double black ×6. A rider's rating of their own
  auto trail counts as **blue at most**; black and double-black weights need a shared trail rated in the admin.
  The Progress screen shows the breakdown.
- **Tiers** (`rides/tiers.py`) are meant to take seasons. Points get you close; from Intermediate up, each tier
  also needs skill on harder trails and active weeks (weeks with at least one ride):

  | Tier | Points | Also needs |
  |---|---|---|
  | Beginner I / II / III | 0 / 500 / 1,200 | |
  | Intermediate I | 2,000 | 5 blue+ features cleaned · 4 active weeks |
  | Intermediate II | 3,000 | 10 blue+ features · 6 weeks |
  | Intermediate III | 4,500 | 15 blue+ features · 1 blue+ trail mastered · 10 weeks |
  | Advanced I | 6,500 | 5 black+ features · 16 weeks |
  | Advanced II | 9,000 | 12 black+ features · 1 black+ trail mastered · 22 weeks |
  | Advanced III | 12,000 | 20 black+ features · 3 black+ trails mastered · 30 weeks |
  | Expert | 16,000 | 8 double-black features · 1 double-black trail mastered · 52 weeks |

  "+" means that difficulty or harder. A trail is mastered when every approved feature on it (at least 3) is
  cleaned. Only approved features count, and a rider's own rating counts as blue at most.
- **Achievements** (`rides/achievements.py`) are one-off milestones saved with the date earned. There are 17 of
  them, such as first jump, one second of air, first black-diamond feature, mastering a trail, a clean climb,
  300 m non-stop, a 1,000 m climbing day, 10,000 m descended, 10 laps of one trail, and a 4-week streak. They're
  awarded after uploads, check-ins and feature updates.

## Sharing trails

Riders' auto trails are private: only they see the trail and its features. Shared trails are what let riders
compare times (speed rank), see features others pinned, and reach Advanced and Expert, which need black and
double-black shared trails.

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
  it earns no rider-level points, tier credit or achievements. That stops anyone from pinning made-up features on a
  black trail to level up.
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
npm test                        # jump/crash detector tests
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

- Clip upload and side-by-side comparison
- Instagram summary card (the share button sends text for now)
- Friends confirming milestones, and leaderboards
- Strava, Garmin and Apple Health import
- Precision mode with a watch or bar mount
- A local notification for the crash prompt when the app is in the background
- Email activation screens. Sign-up activates immediately unless `SEND_ACTIVATION_EMAIL=True`.
- App icons and a splash image
