// "How rider level works": the points rules (from the server, so they always match rules.json), where your points came from,
// the levels and titles, and concrete ways to earn more next.
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import LevelBar from '../components/LevelBar';
import SuggestionRow from '../components/SuggestionRow';
import { ErrorState, Header, Loading } from '../components/ui';
import { DIFFICULTY, colors, ui } from '../theme';

export default function LevelGuideScreen() {
  const { logout } = useAuth();
  const [rules, setRules] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    setError(null);
    try {
      const [r, p] = await Promise.all([
        fetchJson('/api/level-rules/', { logout }),
        fetchJson('/api/progress/', { logout }),
      ]);
      setRules(r);
      setProgress(p);
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, []));

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rules || !progress) return <Loading />;

  const { level } = progress;
  const earned = Object.fromEntries(progress.xp_by_reason.map((r) => [r.reason, r.xp]));
  const suggestions = progress.suggestions || [];

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header caption="Rider level" />
      <Text style={ui.title}>How it works</Text>
      <Text style={ui.subtitle}>
        Your rider level comes from points. Most points are for cleaning graded features, the first time especially,
        and harder features are worth more. Riding earns a little too, with daily caps: getting better counts more than
        riding more.
      </Text>

      <View style={ui.cardRaised}>
        <LevelBar level={level} streakWeeks={progress.practice_streak_weeks} />
      </View>

      {suggestions.length > 0 && (
        <View style={ui.card}>
          <Text style={ui.label}>Riding goals</Text>
          {suggestions.map((s) => <SuggestionRow key={`${s.kind}-${s.title}`} suggestion={s} />)}
        </View>
      )}

      <View style={ui.card}>
        <Text style={ui.label}>Where points come from</Text>
        {rules.sources.map((s) => (
          <View key={s.key} style={{ gap: 2 }}>
            <View style={ui.between}>
              <Text style={ui.strong}>{s.label}</Text>
              <Text style={[ui.strong, { color: colors.accent }]}>{(earned[s.key] ?? 0).toLocaleString()}</Text>
            </View>
            <Text style={ui.small}>{s.how}</Text>
          </View>
        ))}
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Trail difficulty multiplies clean-climb points</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {rules.difficulty_weights.map((d) => (
            <View key={d.difficulty} style={styles.weight}>
              <Text style={[ui.strong, { color: DIFFICULTY[d.difficulty]?.color || colors.text }]}>{d.label}</Text>
              <Text style={[ui.number, { fontSize: 22 }]}>×{d.weight}</Text>
            </View>
          ))}
        </View>
        <Text style={ui.small}>
          Trails you discover are rated by you, so they count as {rules.rider_rated_max} at most. Shared trails, rated
          by Next Line, count in full.
        </Text>
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Levels</Text>
        {rules.levels.map((l) => {
          const reached = l.level <= level.level;
          const newTitle = l.level === 1 || rules.levels[l.level - 2].title !== l.title;
          return (
            <View key={l.level} style={[ui.row, { gap: 10 }]}>
              <Ionicons name={reached ? 'checkmark-circle' : 'ellipse-outline'} size={18}
                color={l.level === level.level ? colors.accent : reached ? colors.good : colors.muted} />
              <Text style={[ui.strong, { width: 64 }, !reached && { color: colors.muted }]}>Level {l.level}</Text>
              <Text style={[ui.body, { flex: 1, color: newTitle ? colors.text : colors.muted }]}>
                {newTitle ? l.title : ''}
              </Text>
              <Text style={[ui.small, reached && { color: colors.text }]}>{l.xp.toLocaleString()} pts</Text>
            </View>
          );
        })}
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Good to know</Text>
        <Text style={ui.small}>• Points never go down, except when you delete a ride or a log: what it earned is taken back.</Text>
        <Text style={ui.small}>• Points use the grade a feature had when you rode it, so regrading never changes them.</Text>
        <Text style={ui.small}>• Walking a feature earns nothing, and that's fine: it's logged so you can see your progress.</Text>
        <Text style={ui.small}>• Achievements are separate milestones. They don't add points, but they mark firsts.</Text>
        <Text style={ui.small}>• Flow and climbing stamina are trends for you to follow; they don't feed the level.</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  weight: {
    flexGrow: 1, minWidth: '22%', padding: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center',
  },
});
