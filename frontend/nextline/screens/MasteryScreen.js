// Confirming a mastery test, then the unlock moment: XP, the level bar filling, and the skills that just opened up.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Animated, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, ErrorState, Header, Loading } from '../components/ui';
import { xp } from '../utils/format';
import { colors, fonts, ui } from '../theme';

// Level bar that fills from the old level to the new one; on a level-up it fills, then restarts from empty.
function FillingBar({ before, after }) {
  const fill = useRef(new Animated.Value(before.fraction)).current;
  useEffect(() => {
    const steps = after.level > before.level
      ? [Animated.timing(fill, { toValue: 1, duration: 700, useNativeDriver: false }),
        Animated.timing(fill, { toValue: 0, duration: 0, useNativeDriver: false }),
        Animated.timing(fill, { toValue: after.fraction, duration: 700, useNativeDriver: false })]
      : [Animated.timing(fill, { toValue: after.fraction, duration: 900, useNativeDriver: false })];
    Animated.sequence([Animated.delay(400), ...steps]).start();
  }, []);
  const width = fill.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });
  return (
    <View style={styles.track}>
      <Animated.View style={[styles.fill, { width }]} />
    </View>
  );
}

function Celebration({ result, skillName }) {
  const navigation = useNavigation();
  const pop = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.spring(pop, { toValue: 1, friction: 4, tension: 60, useNativeDriver: true }).start();
  }, []);
  const level = result.level;
  return (
    <ScrollView contentContainerStyle={[ui.scroll, { paddingTop: 40 }]}>
      <Animated.View style={{ alignItems: 'center', gap: 6, transform: [{ scale: pop }], opacity: pop }}>
        <Ionicons name="trophy" size={64} color={colors.accent} />
        <Text style={[ui.title, { fontSize: 52, lineHeight: 54, color: colors.accent }]}>Mastered</Text>
        <Text style={[ui.strong, { fontSize: 20 }]}>{skillName}</Text>
        <Text style={[ui.number, { color: colors.text }]}>{xp(result.xp_gained)}</Text>
      </Animated.View>

      <View style={ui.card}>
        {result.leveled_up && (
          <Text style={[ui.strong, { color: colors.accent, fontSize: 18 }]}>
            Level up! Level {level.level} · {level.title}
          </Text>
        )}
        <FillingBar before={result.level_before} after={level} />
        <Text style={ui.small}>
          {level.to_next == null ? 'Top level' : `${level.to_next.toLocaleString()} XP to level ${level.level + 1}`}
        </Text>
        {result.challenges_completed.length > 0 && (
          <Text style={[ui.strong, { color: colors.good }]}>Challenge complete: {result.challenges_completed.join(', ')}</Text>
        )}
      </View>

      {result.unlocked.length > 0 ? (
        <>
          <Text style={ui.label}>Now ready to learn</Text>
          {result.unlocked.map((s) => (
            <TouchableOpacity key={s.id} style={[ui.card, styles.unlock]}
              onPress={() => navigation.replace('Skill', { id: s.id })}>
              <Ionicons name="lock-open" size={22} color={colors.accent} />
              <View style={{ flex: 1 }}>
                <Text style={ui.strong}>{s.name}</Text>
                <Text style={ui.small}>Tier {s.tier}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </TouchableOpacity>
          ))}
        </>
      ) : (
        <Text style={ui.small}>Nothing new unlocked yet: some skills need more than one prerequisite.</Text>
      )}
      <Button title="Back to the tree" variant="secondary" onPress={() => navigation.navigate('Skills')} />
    </ScrollView>
  );
}

export default function MasteryScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [skill, setSkill] = useState(null);
  const [error, setError] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSkill(await fetchJson(`/api/skills/${params.id}/`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  }, [params.id, logout]);

  useFocusEffect(useCallback(() => { if (!result) load(); }, [load, result]));

  if (result) return <Celebration result={result} skillName={skill.name} />;
  if (error && !skill) return <ErrorState message={error} onRetry={load} />;
  if (!skill) return <Loading />;

  const confirm = async () => {
    setSaving(true);
    try {
      setResult(await sendJson(`/api/skills/${skill.id}/master/`, 'POST', { confirmed_test: true }, logout));
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={ui.scroll}>
      <Header caption="Mastery test" />
      <Text style={ui.title}>{skill.name}</Text>
      {!skill.eligible ? (
        <View style={ui.card}>
          <Text style={ui.strong}>Not quite yet</Text>
          <Text style={ui.body}>
            {skill.state === 'mastered' ? "You've already mastered this one." : `Still needed: ${skill.missing.join(', ')}.`}
          </Text>
          <Button title="Back" variant="secondary" onPress={() => navigation.goBack()} />
        </View>
      ) : (
        <>
          <View style={[ui.cardRaised, { borderWidth: 1, borderColor: colors.accent }]}>
            <Text style={ui.label}>The test</Text>
            <Text style={[ui.body, { fontFamily: fonts.medium, fontSize: 17, lineHeight: 24 }]}>{skill.mastery_test}</Text>
          </View>
          <Text style={ui.small}>
            Be honest with yourself: mastery unlocks harder skills that build on this one. A coach can verify it later.
          </Text>
          <TouchableOpacity style={styles.check} onPress={() => setConfirmed(!confirmed)}
            accessibilityRole="checkbox" accessibilityState={{ checked: confirmed }}>
            <Ionicons name={confirmed ? 'checkbox' : 'square-outline'} size={26} color={confirmed ? colors.accent : colors.muted} />
            <Text style={[ui.body, { flex: 1 }]}>I passed the mastery test</Text>
          </TouchableOpacity>
          <Button title={`Master ${skill.name}`} disabled={!confirmed} loading={saving} onPress={confirm} icon="trophy" />
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  track: { height: 14, borderRadius: 7, backgroundColor: colors.border, overflow: 'hidden' },
  fill: { height: 14, backgroundColor: colors.accent },
  unlock: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  check: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 },
});
