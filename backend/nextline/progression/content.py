"""Skill tree, point rules and challenges, loaded from the JSON files in progression/content/.

The files are the source of truth: edit them and restart (no migration, no app build). validate() checks them, and
runs as a Django system check, so `manage.py check`, `migrate`, `runserver` and `test` refuse bad content.
"""
import json
from functools import lru_cache
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent / 'content'

TIERS = (1, 2, 3, 4, 5, 6)
REQUIRED_SKILL_FIELDS = (
    'id', 'name', 'branch', 'tier', 'prerequisites', 'description', 'why', 'drills', 'mastery_test', 'media', 'tags',
)
MIN_DRILLS, MAX_DRILLS = 2, 3
# A skill's tags link it to trail feature types (trails.models.FeatureType). The tags predate the current types,
# so some map across: a gap is a jump, a berm is a corner.
TAG_TYPES = {
    'drop': 'drop', 'jump': 'jump', 'gap': 'jump', 'rock_garden': 'rock_garden', 'roots': 'roots',
    'berm': 'corner', 'technical': 'other',
}
FEATURE_TAGS = set(TAG_TYPES)
XP_KEYS = (
    'first_clean_per_grade', 'repeat_clean', 'sketchy_per_grade', 'walked', 'trail_complete', 'ladder_complete',
    'drill_session', 'attempt_video', 'mastery_per_tier', 'challenge_complete', 'weekly_streak', 'ride',
    'trail_pr', 'clean_climb_per_weight', 'biggest_air', 'descent_per_100m', 'jump',
)
CAP_KEYS = (
    'repeat_cleans_per_feature_per_week', 'drill_sessions_per_skill_per_day', 'attempt_videos_per_skill_per_day',
    'descent_xp_per_day', 'jump_xp_per_day',
)
POSITIVE_KEYS = (
    ('bonuses', 'min_features'), ('next_up', 'max_suggestions'), ('next_up', 'repeat_cleans_needed'),
    ('next_up', 'advanced_above_grade'), ('verification', 'stale_after_months'),
)
GOAL_TYPES = ('sessions', 'master')


class ContentError(Exception):
    def __init__(self, errors):
        super().__init__('; '.join(errors))
        self.errors = errors


def read(name, directory=None):
    with open(Path(directory or CONTENT_DIR) / name, encoding='utf-8') as f:
        return json.load(f)


def find_cycle(prerequisites):
    """The first prerequisite cycle as a list of ids ending where it started, e.g. ['a', 'b', 'a']; None if none.

    `prerequisites` maps skill id -> list of prerequisite ids. Unknown ids are ignored (reported separately).
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color = {skill: WHITE for skill in prerequisites}
    path = []

    def visit(skill):
        color[skill] = GREY
        path.append(skill)
        for prereq in prerequisites[skill]:
            if prereq not in color:
                continue
            if color[prereq] == GREY:
                return path[path.index(prereq):] + [prereq]
            if color[prereq] == WHITE:
                cycle = visit(prereq)
                if cycle:
                    return cycle
        path.pop()
        color[skill] = BLACK
        return None

    for skill in prerequisites:
        if color[skill] == WHITE:
            cycle = visit(skill)
            if cycle:
                return cycle
    return None


def validate_skills(data):
    """(errors, warnings) for a parsed skills.json."""
    errors, warnings = [], []
    branches = {b.get('id') for b in data.get('branches', [])}
    if not branches:
        errors.append('skills.json: no branches')
    skills = data.get('skills', [])
    if not skills:
        errors.append('skills.json: no skills')

    seen = set()
    for i, skill in enumerate(skills):
        label = skill.get('id') or f'skill #{i + 1}'
        for field in REQUIRED_SKILL_FIELDS:
            value = skill.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f'{label}: missing {field}')
        if skill.get('id') in seen:
            errors.append(f'{label}: duplicate id')
        seen.add(skill.get('id'))
        if skill.get('branch') and skill['branch'] not in branches:
            errors.append(f"{label}: unknown branch '{skill['branch']}'")
        if 'tier' in skill and skill['tier'] not in TIERS:
            errors.append(f'{label}: tier must be one of {TIERS}')
        drills = skill.get('drills') or []
        if not MIN_DRILLS <= len(drills) <= MAX_DRILLS:
            errors.append(f'{label}: needs {MIN_DRILLS}–{MAX_DRILLS} drills, has {len(drills)}')
        for d, drill in enumerate(drills):
            if not (isinstance(drill, dict) and drill.get('name') and drill.get('how')):
                errors.append(f'{label}: drill {d + 1} needs a name and how')
        for tag in skill.get('tags') or []:
            if tag not in FEATURE_TAGS:
                warnings.append(f"{label}: tag '{tag}' doesn't match a trail feature kind")

    by_id = {s['id']: s for s in skills if s.get('id')}
    for skill in by_id.values():
        for prereq in skill.get('prerequisites') or []:
            if prereq == skill['id']:
                errors.append(f"{skill['id']}: requires itself")
            elif prereq not in by_id:
                errors.append(f"{skill['id']}: unknown prerequisite '{prereq}'")
            elif by_id[prereq].get('tier', 0) > skill.get('tier', 0):
                warnings.append(f"{skill['id']}: tier {skill.get('tier')} is easier than its prerequisite {prereq}")
    cycle = find_cycle({s: [p for p in by_id[s].get('prerequisites') or [] if p != s] for s in by_id})
    if cycle:
        errors.append('prerequisite cycle: ' + ' → '.join(cycle))
    elif not errors:
        errors += validate_capstone(by_id)
    return errors, warnings


def validate_capstone(by_id):
    """The capstone (at most one) has to need every other skill, directly or not, so mastering it means the whole
    tree is done."""
    capstones = [s for s in by_id if by_id[s].get('capstone')]
    if len(capstones) > 1:
        return ['only one skill can be the capstone: ' + ', '.join(capstones)]
    if not capstones:
        return []
    below = set()
    todo = list(by_id[capstones[0]]['prerequisites'])
    while todo:
        skill = todo.pop()
        if skill not in below:
            below.add(skill)
            todo += by_id[skill]['prerequisites']
    missing = sorted(set(by_id) - below - {capstones[0]})
    return [f"{capstones[0]}: the capstone doesn't need {', '.join(missing)}"] if missing else []


def validate_rules(rules):
    errors = []
    for section, keys in (('xp', XP_KEYS), ('caps', CAP_KEYS)):
        for key in keys:
            value = rules.get(section, {}).get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f'rules.json: {section}.{key} must be a whole number, 0 or more')
    for section, key in POSITIVE_KEYS:
        value = rules.get(section, {}).get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f'rules.json: {section}.{key} must be a whole number, 1 or more')
    if not isinstance(rules.get('verification', {}).get('second_reviewer_required'), bool):
        errors.append('rules.json: verification.second_reviewer_required must be true or false')
    mastery = rules.get('mastery', {})
    for key in ('min_sessions', 'min_practice_days', 'min_videos'):
        if not isinstance(mastery.get(key), int) or mastery[key] < 0:
            errors.append(f'rules.json: mastery.{key} must be a whole number, 0 or more')
    if isinstance(mastery.get('min_practice_days'), int) and isinstance(mastery.get('min_sessions'), int)             and mastery['min_practice_days'] > mastery['min_sessions']:
        errors.append('rules.json: mastery.min_practice_days can be at most mastery.min_sessions')
    if not isinstance(rules.get('streak', {}).get('practice_days_per_week'), int) \
            or not 1 <= rules['streak']['practice_days_per_week'] <= 7:
        errors.append('rules.json: streak.practice_days_per_week must be 1–7')
    levels = rules.get('levels', {})
    if not (isinstance(levels.get('first_step'), int) and levels['first_step'] > 0):
        errors.append('rules.json: levels.first_step must be a whole number above 0')
    if not (isinstance(levels.get('growth'), (int, float)) and levels['growth'] >= 1):
        errors.append('rules.json: levels.growth must be 1 or more')
    if not (isinstance(levels.get('count'), int) and levels['count'] >= 2):
        errors.append('rules.json: levels.count must be 2 or more')
    if not rules.get('master_title'):
        errors.append('rules.json: master_title is missing')
    titles = rules.get('titles') or []
    starts = [t.get('from_level') for t in titles]
    if not titles or starts[0] != 1:
        errors.append('rules.json: titles must start at from_level 1')
    elif any(not isinstance(s, int) for s in starts) or starts != sorted(set(starts)):
        errors.append('rules.json: titles must have increasing from_level values')
    if any(not t.get('title') for t in titles):
        errors.append('rules.json: every title needs a title')
    return errors


def validate_challenges(data, skill_ids):
    errors = []
    slugs = set()
    for c in data.get('challenges', []):
        label = c.get('slug') or c.get('title') or 'challenge'
        for field in ('slug', 'title', 'skills', 'goal_type', 'goal_count', 'days'):
            if not c.get(field):
                errors.append(f'{label}: missing {field}')
        if c.get('slug') in slugs:
            errors.append(f'{label}: duplicate slug')
        slugs.add(c.get('slug'))
        for skill in c.get('skills') or []:
            if skill not in skill_ids:
                errors.append(f"{label}: unknown skill '{skill}'")
        if c.get('goal_type') and c['goal_type'] not in GOAL_TYPES:
            errors.append(f'{label}: goal_type must be one of {GOAL_TYPES}')
    return errors


def validate(directory=None):
    """(errors, warnings) for all three content files."""
    errors, warnings = [], []
    loaded = {}
    for name in ('skills.json', 'rules.json', 'challenges.json'):
        try:
            loaded[name] = read(name, directory)
        except FileNotFoundError:
            errors.append(f'{name}: not found')
        except json.JSONDecodeError as e:
            errors.append(f'{name}: invalid JSON at line {e.lineno}: {e.msg}')
    if 'skills.json' in loaded:
        e, w = validate_skills(loaded['skills.json'])
        errors += e
        warnings += w
    if 'rules.json' in loaded:
        errors += validate_rules(loaded['rules.json'])
    if 'challenges.json' in loaded:
        skill_ids = {s.get('id') for s in loaded.get('skills.json', {}).get('skills', [])}
        errors += validate_challenges(loaded['challenges.json'], skill_ids)
    return errors, warnings


@lru_cache(maxsize=1)
def _load():
    errors, _ = validate()
    if errors:
        raise ContentError(errors)
    return read('skills.json'), read('rules.json')


def skill_tree():
    return _load()[0]


def rules():
    return _load()[1]


def capstone_id():
    """The skill that means the whole tree is mastered, or None."""
    return next((s['id'] for s in skill_tree()['skills'] if s.get('capstone')), None)


def skills_by_id():
    return {s['id']: s for s in skill_tree()['skills']}


def depths(skills):
    """Column for each skill in the tree view: the longest prerequisite chain below it (Foundations = 0)."""
    by_id = {s['id']: s for s in skills}
    memo = {}

    def depth(skill_id):
        if skill_id not in memo:
            prereqs = by_id[skill_id]['prerequisites']
            memo[skill_id] = 1 + max(depth(p) for p in prereqs) if prereqs else 0
        return memo[skill_id]

    return {s['id']: depth(s['id']) for s in skills}


def unlocks(skills):
    """Skill id -> ids of the skills that list it as a prerequisite."""
    out = {s['id']: [] for s in skills}
    for s in skills:
        for p in s['prerequisites']:
            out[p].append(s['id'])
    return out
