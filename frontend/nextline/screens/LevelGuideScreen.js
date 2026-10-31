// "How rider level works": the rules (from the server, so they always match the scoring), where your points come
// from, and concrete ways to level up next.
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import SuggestionRow from '../components/SuggestionRow';
import { ErrorState, Header, Loading, ProgressBar } from '../components/ui';
import { DIFFICULTY, colors, fonts, ui } from '../theme';

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
  const tierIndex = rules.tiers.findIndex((t) => t.name === level.tier);
  const next = rules.tiers[tierIndex + 1];
  const requirements = level.requirements || [];
  const suggestions = progress.suggestions || [];

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header caption="Rider level" />
      <Text style={ui.title}>How it works</Text>
      <Text style={ui.subtitle}>
        Your rider level is one number that only goes up. It's built from your bests and totals, so a bad day never
        costs you anything.
      </Text>

      <View style={ui.cardRaised}>
        <View style={ui.between}>
          <Text style={ui.label}>You</Text>
          <Text style={ui.strong}>{level.tier}</Text>
        </View>
        <Text style={styles.points}>{level.points.toLocaleString()} points</Text>
        {next && (
          <>
            <ProgressBar fraction={next.points ? Math.min(1, level.points / next.points) : 1} />
            <Text style={ui.small}>
              {level.to_next > 0
                ? `${level.to_next.toLocaleString()} points to ${next.name}`
                : `You have the points for ${next.name}`}
            </Text>
            {requirements.map((r) => (
              <View key={r.kind} style={[ui.row, { gap: 8 }]}>
                <Ionicons name={r.met ? 'checkmark-circle' : 'ellipse-outline'} size={16}
                  color={r.met ? colors.good : colors.warn} />
                <Text style={[ui.small, { flex: 1, color: r.met ? colors.muted : colors.text }]}>{r.label}</Text>
                <Text style={ui.small}>{r.have}/{r.needed}</Text>
              </View>
            ))}
          </>
        )}
      </View>

      {suggestions.length > 0 && (
        <View style={ui.card}>
          <Text style={ui.label}>Ways to level up</Text>
          {suggestions.map((s) => <SuggestionRow key={`${s.kind}-${s.title}`} suggestion={s} />)}
        </View>
      )}

      <View style={ui.card}>
        <Text style={ui.label}>Where points come from</Text>
        {rules.sources.map((s) => (
          <View key={s.key} style={{ gap: 2 }}>
            <View style={ui.between}>
              <Text style={ui.strong}>{s.label}</Text>
              <Text style={[ui.strong, { color: colors.accent }]}>{level.parts[s.key] ?? 0}</Text>
            </View>
            <Text style={ui.small}>{s.how}</Text>
          </View>
        ))}
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Trail difficulty multiplies points</Text>
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
          by Next Line, count in full: the harder the trail, the more each feature and fast run is worth.
        </Text>
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Tiers</Text>
        <Text style={ui.small}>
          Levels take seasons, not weeks. Points get you close to a tier; from Intermediate up you also need
          features cleaned and trails mastered on harder trails, and active weeks (weeks you rode at all). Points
          alone won't get you there.
        </Text>
        {rules.tiers.map((t, i) => {
          const reached = i <= tierIndex;
          return (
            <View key={t.name} style={[ui.row, { gap: 10 }]}>
              <Ionicons name={reached ? 'checkmark-circle' : 'ellipse-outline'} size={20}
                color={reached ? colors.good : colors.muted} />
              <View style={{ flex: 1 }}>
                <Text style={[ui.strong, !reached && { color: colors.muted }]}>{t.name}</Text>
                {t.requirements.length > 0 && <Text style={ui.small}>{t.requirements.join(' · ')}</Text>}
              </View>
              <Text style={[ui.body, { color: reached ? colors.text : colors.muted }]}>{t.points.toLocaleString()}</Text>
            </View>
          );
        })}
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Good to know</Text>
        <Text style={ui.small}>• After every ride, the summary shows the points it earned and why.</Text>
        <Text style={ui.small}>• Mark features you cleaned in the 10-second check-in: it's the biggest source of points.</Text>
        <Text style={ui.small}>• Achievements are separate milestones. They don't add points, but they mark firsts.</Text>
        <Text style={ui.small}>• A trail is mastered when you've cleaned every one of its features (at least 3).</Text>
        <Text style={ui.small}>• Flow and climbing stamina are trends for you to follow; only your bests feed the level.</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  points: { fontFamily: fonts.display, fontSize: 40, lineHeight: 44, color: colors.text },
  weight: {
    flexGrow: 1, minWidth: '22%', padding: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center',
  },
});
