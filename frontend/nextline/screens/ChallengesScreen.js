// Challenges: join one, then see progress toward its goal.
import { useCallback, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { fetchJson, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, ErrorState, Header, Loading, ProgressBar } from '../components/ui';
import { dateOnly } from '../utils/format';
import { colors, ui } from '../theme';

// The server describes each goal; older servers didn't, for the skill goals.
function goalText(c) {
  if (c.goal_text) return c.goal_text;
  const skills = (c.skills || []).map((s) => s.name).join(' or ');
  return c.goal_type === 'sessions'
    ? `Log ${c.goal_count} ${skills} session${c.goal_count === 1 ? '' : 's'}`
    : `Master ${skills}`;
}

export default function ChallengesScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [challenges, setChallenges] = useState(null);
  const [error, setError] = useState(null);
  const [joining, setJoining] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setChallenges(await fetchJson('/api/challenges/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  }, [logout]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const join = async (c) => {
    setJoining(c.id);
    try {
      await sendJson(`/api/challenges/${c.id}/join/`, 'POST', undefined, logout);
      await load();
    } catch (err) {
      Alert.alert("Couldn't join", err.message);
    } finally {
      setJoining(null);
    }
  };

  if (error && !challenges) return <ErrorState message={error} onRetry={load} />;
  if (!challenges) return <Loading />;

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header caption="Challenges" />
      <Text style={ui.title}>Challenges</Text>
      {challenges.length === 0 && <Text style={ui.small}>No challenges are running right now. Check back soon.</Text>}
      {challenges.map((c) => (
        <View key={c.id} style={ui.card}>
          <View style={ui.between}>
            <Text style={[ui.strong, { fontSize: 17, flex: 1 }]}>{c.title}</Text>
            <Text style={[ui.small, { color: colors.good }]}>+{c.xp} pts</Text>
          </View>
          <Text style={ui.body}>{goalText(c)}</Text>
          {c.description ? <Text style={ui.small}>{c.description}</Text> : null}
          <Text style={ui.small}>
            {dateOnly(c.starts_on)} – {dateOnly(c.ends_on)}{c.open ? ` · ${c.days_left} day${c.days_left === 1 ? '' : 's'} left` : ''}
          </Text>
          {c.joined ? (
            <>
              <ProgressBar fraction={c.progress / c.goal_count} color={c.completed_at ? colors.good : colors.accent} />
              <Text style={[ui.strong, c.completed_at && { color: colors.good }]}>
                {c.completed_at ? 'Complete!' : `${c.progress} of ${c.goal_count}`}
              </Text>
              {!c.completed_at && (
                <Button title="See what's next up" variant="secondary" onPress={() => navigation.navigate('NextUp')} />
              )}
            </>
          ) : (
            <Button title="Join" loading={joining === c.id} onPress={() => join(c)} />
          )}
        </View>
      ))}
      <Text style={ui.small}>Only features you log after you join count toward a challenge.</Text>
    </ScrollView>
  );
}
