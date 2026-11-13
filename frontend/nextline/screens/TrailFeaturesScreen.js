// A trail's page: every feature in riding order with a photo and the rider's status, and "Log this trail".
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import FeatureRow from '../components/FeatureRow';
import SafetyNote from '../components/SafetyNote';
import { Button, ErrorState, Header, Loading, ProgressBar } from '../components/ui';
import { progressLine } from '../utils/features';
import { miles } from '../utils/format';
import { DIFFICULTY, colors, ui } from '../theme';

export default function TrailFeaturesScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [trail, setTrail] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    try {
      setTrail(await fetchJson(`/api/trails/${params.id}/features/`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  if (!trail && error) return <ErrorState message={error} onRetry={load} />;
  if (!trail) return <Loading />;

  const cleaned = trail.features.filter((f) => f.my_status === 'cleaned').length;
  const difficulty = DIFFICULTY[trail.difficulty] || DIFFICULTY.unrated;

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
      <Header caption={trail.system_name || 'Trail'} />
      <Text style={ui.title}>{trail.name}</Text>
      <Text style={[ui.label, { color: difficulty.color }]}>{difficulty.label} · {miles(trail.length_m)} mi</Text>

      <View style={ui.cardRaised}>
        <Text style={ui.strong}>{progressLine(cleaned, trail.features.length)}</Text>
        {trail.features.length > 0 && <ProgressBar fraction={cleaned / trail.features.length} />}
      </View>

      {trail.features.length > 0 && (
        <Button title="Log this trail" icon="list" onPress={() => navigation.navigate('LogTrail', { id: trail.id })} />
      )}

      <View style={ui.card}>
        <Text style={ui.label}>Features in riding order</Text>
        {trail.features.length === 0 && <Text style={ui.small}>No graded features on this trail yet.</Text>}
        {trail.features.map((f, i) => (
          <View key={f.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={[ui.small, { width: 18, textAlign: 'right' }]}>{i + 1}</Text>
            <View style={{ flex: 1 }}><FeatureRow feature={f} /></View>
          </View>
        ))}
      </View>

      <Button title="Times and laps on this trail" variant="secondary"
        onPress={() => navigation.navigate('Trail', { id: trail.id })} />
      <SafetyNote text={trail.safety} />
    </ScrollView>
  );
}
