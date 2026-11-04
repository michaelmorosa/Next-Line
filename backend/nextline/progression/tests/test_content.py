import copy
import io
import json
import shutil
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from progression import content
from progression.content import depths, find_cycle, unlocks, validate, validate_challenges, validate_rules, validate_skills


def skill(id, prerequisites=(), tier=1, branch='foundations', **extra):
    return {
        'id': id, 'name': id.title(), 'branch': branch, 'tier': tier, 'prerequisites': list(prerequisites),
        'description': 'd', 'why': 'w', 'drills': [{'name': 'a', 'how': 'x'}, {'name': 'b', 'how': 'y'}],
        'mastery_test': 't', 'media': [], 'tags': [], **extra,
    }


def tree(*skills):
    return {'version': 1, 'branches': [{'id': 'foundations', 'name': 'F'}, {'id': 'drops', 'name': 'D'}],
            'skills': list(skills)}


class CycleDetectionTests(SimpleTestCase):
    def test_no_cycle(self):
        self.assertIsNone(find_cycle({'a': [], 'b': ['a'], 'c': ['a', 'b']}))

    def test_direct_cycle(self):
        self.assertEqual(find_cycle({'a': ['b'], 'b': ['a']}), ['a', 'b', 'a'])

    def test_long_cycle_reports_path(self):
        cycle = find_cycle({'root': [], 'a': ['root', 'c'], 'b': ['a'], 'c': ['b']})
        self.assertEqual(cycle[0], cycle[-1])
        self.assertEqual(set(cycle), {'a', 'b', 'c'})

    def test_shared_prerequisite_is_not_a_cycle(self):
        # Diamond: d needs b and c, both need a.
        self.assertIsNone(find_cycle({'a': [], 'b': ['a'], 'c': ['a'], 'd': ['b', 'c']}))


class SkillValidationTests(SimpleTestCase):
    def test_valid_tree(self):
        errors, _ = validate_skills(tree(skill('a'), skill('b', ['a'], tier=2)))
        self.assertEqual(errors, [])

    def test_missing_prerequisite(self):
        errors, _ = validate_skills(tree(skill('a', ['ghost'])))
        self.assertIn("a: unknown prerequisite 'ghost'", errors)

    def test_cycle_is_an_error(self):
        errors, _ = validate_skills(tree(skill('a', ['b']), skill('b', ['a'])))
        self.assertTrue(any(e.startswith('prerequisite cycle: ') for e in errors))

    def test_self_prerequisite(self):
        errors, _ = validate_skills(tree(skill('a', ['a'])))
        self.assertIn('a: requires itself', errors)

    def test_missing_and_empty_fields(self):
        bad = skill('a')
        del bad['mastery_test']
        bad['why'] = '  '
        errors, _ = validate_skills(tree(bad))
        self.assertIn('a: missing mastery_test', errors)
        self.assertIn('a: missing why', errors)

    def test_drill_count_and_shape(self):
        bad = skill('a', drills=[{'name': 'only one', 'how': 'x'}])
        errors, _ = validate_skills(tree(bad))
        self.assertIn('a: needs 2–3 drills, has 1', errors)
        bad = skill('a', drills=[{'name': 'x'}, {'name': 'y', 'how': 'z'}])
        errors, _ = validate_skills(tree(bad))
        self.assertIn('a: drill 1 needs a name and how', errors)

    def test_duplicate_id_unknown_branch_bad_tier(self):
        errors, _ = validate_skills(tree(skill('a'), skill('a'), skill('b', branch='nope', tier=7)))
        self.assertIn('a: duplicate id', errors)
        self.assertIn("b: unknown branch 'nope'", errors)
        self.assertTrue(any(e.startswith('b: tier must be') for e in errors))

    def test_warnings_dont_fail(self):
        errors, warnings = validate_skills(tree(skill('hard', tier=3), skill('easy', ['hard'], tier=1, tags=['vibes'])))
        self.assertEqual(errors, [])
        self.assertIn('easy: tier 1 is easier than its prerequisite hard', warnings)
        self.assertIn("easy: tag 'vibes' doesn't match a trail feature kind", warnings)


class RulesValidationTests(SimpleTestCase):
    def setUp(self):
        self.rules = copy.deepcopy(content.read('rules.json'))

    def test_real_rules_valid(self):
        self.assertEqual(validate_rules(self.rules), [])

    def test_negative_or_fractional_xp(self):
        self.rules['xp']['drill_session'] = -5
        self.rules['caps']['jump_xp_per_day'] = 2.5
        errors = validate_rules(self.rules)
        self.assertIn('rules.json: xp.drill_session must be a whole number, 0 or more', errors)
        self.assertIn('rules.json: caps.jump_xp_per_day must be a whole number, 0 or more', errors)

    def test_titles_must_start_at_one_and_increase(self):
        self.rules['titles'] = [{'from_level': 3, 'title': 'X'}]
        self.assertIn('rules.json: titles must start at from_level 1', validate_rules(self.rules))
        self.rules['titles'] = [{'from_level': 1, 'title': 'X'}, {'from_level': 1, 'title': 'Y'}]
        self.assertIn('rules.json: titles must have increasing from_level values', validate_rules(self.rules))

    def test_practice_days_cannot_exceed_sessions(self):
        self.rules['mastery']['min_practice_days'] = 5
        self.assertIn('rules.json: mastery.min_practice_days can be at most mastery.min_sessions',
                      validate_rules(self.rules))


class ChallengeValidationTests(SimpleTestCase):
    def test_unknown_skill_and_goal(self):
        data = {'challenges': [{'slug': 'x', 'title': 'X', 'skills': ['ghost'], 'goal_type': 'vibes',
                                'goal_count': 1, 'days': 3}]}
        errors = validate_challenges(data, {'manual'})
        self.assertIn("x: unknown skill 'ghost'", errors)
        self.assertTrue(any('goal_type' in e for e in errors))


class RealContentTests(SimpleTestCase):
    """The shipped files: a bad edit to skills.json or rules.json fails the test suite."""

    def test_content_files_are_valid(self):
        errors, warnings = validate()
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_seed_tree(self):
        skills = content.read('skills.json')['skills']
        by_id = {s['id']: s for s in skills}
        self.assertEqual(len(skills), 19)
        self.assertEqual({s['tier'] for s in skills}, {1, 2, 3, 4})
        self.assertEqual(len({s['branch'] for s in skills}), 6)
        self.assertEqual(sorted(by_id['small_drops']['prerequisites']), ['manual', 'roll_offs'])
        self.assertTrue(all(s['draft'] for s in skills))
        roots = {s['id'] for s in skills if not s['prerequisites']}
        self.assertEqual(roots, {'attack_position', 'braking_control', 'looking_ahead'})

    def test_depths_put_prerequisites_left(self):
        skills = content.read('skills.json')['skills']
        d = depths(skills)
        for s in skills:
            for p in s['prerequisites']:
                self.assertLess(d[p], d[s['id']])
        self.assertIn('small_drops', unlocks(skills)['manual'])


class ValidateCommandTests(SimpleTestCase):
    def test_command_passes_on_real_content(self):
        out = io.StringIO()
        call_command('validate_progression', stdout=out)
        self.assertIn('valid', out.getvalue())

    def test_command_fails_on_cycle(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        for name in ('rules.json', 'challenges.json'):
            shutil.copy(content.CONTENT_DIR / name, folder)
        data = content.read('skills.json')
        by_id = {s['id']: s for s in data['skills']}
        by_id['attack_position']['prerequisites'] = ['small_drops']
        Path(folder, 'skills.json').write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(CommandError):
            call_command('validate_progression', dir=folder, stdout=io.StringIO(), stderr=io.StringIO())


class MigrationsTests(TestCase):
    def test_no_missing_migrations(self):
        out = io.StringIO()
        try:
            call_command('makemigrations', check=True, dry_run=True, stdout=out, stderr=out)
        except SystemExit:
            self.fail(f'Model changes without a migration:\n{out.getvalue()}')
