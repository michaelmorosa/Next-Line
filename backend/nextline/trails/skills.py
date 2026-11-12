"""Skills behind the scenes: features are tagged with skills from progression/content/skills.json. Riders never see a
skill tree; skills show up as "Stuck?" tips on a feature and as strengths on the dashboard."""
import json
from functools import lru_cache
from pathlib import Path

from progression import content

# Skills a feature uses when the team hasn't tagged it yet, by type.
DEFAULT_TAGS = {
    'drop': ['roll_offs', 'small_drops'],
    'jump': ['pumping', 'tabletops'],
    'corner': ['flat_corners', 'berms'],
    'rock_garden': ['roots_and_rocks', 'rock_gardens'],
    'roots': ['roots_and_rocks', 'wet_roots'],
    'steep': ['steep_rolls', 'steeps'],
    'skinny': ['track_stand', 'looking_ahead'],
    'climb': ['climbing_position', 'tech_climbs'],
    'other': ['attack_position'],
}

SAFETY_FILE = Path(__file__).resolve().parent / 'content' / 'safety.json'


@lru_cache
def safety():
    return json.loads(SAFETY_FILE.read_text(encoding='utf-8'))


def tags_for(feature):
    """The feature's skill ids: the team's tags, or the defaults for its type."""
    known = content.skills_by_id()
    tags = feature.skill_tags or DEFAULT_TAGS.get(feature.type, [])
    return [t for t in tags if t in known]


def tips(feature):
    """The "Stuck?" section: for each tagged skill, what it is, why it helps, and optional drills."""
    known = content.skills_by_id()
    return [
        {
            'skill': skill_id,
            'name': known[skill_id]['name'],
            'what': known[skill_id]['description'],
            'why': known[skill_id]['why'],
            'drills': [{'name': d['name'], 'how': d['how']} for d in known[skill_id]['drills']],
            'got_it_when': known[skill_id]['mastery_test'],
        }
        for skill_id in tags_for(feature)
    ]


def branch_names():
    return {b['id']: b['name'] for b in content.skill_tree()['branches']}
