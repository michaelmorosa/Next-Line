// "Log this trail": after a ride, mark how each feature went in a few taps, then save them together.
// Opened from a trail page, or from a ride summary (then the logs are linked to that ride and dated the ride's day).
import { useEffect, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import { FeatureThumb } from '../components/FeatureRow';
import OutcomeButtons from '../components/OutcomeButtons';
import { Button, ErrorState, Header, Loading } from '../components/ui';
import { announceAchievements } from '../utils/achievements';
import { batchBody, featureMeta, localDay, pickedSummary, points, uuid } from '../utils/features';
import { logBatch } from '../utils/logging';
import { ui } from '../theme';

export default function LogTrailScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [trail, setTrail] = useState(null);
  const [error, setError] = useState(null);
  const [picked, setPicked] = useState({});
  const [saving, setSaving] = useState(false);

  const load = () => {
    setError(null);
    fetchJson(`/api/trails/${params.id}/features/`, { logout }).then(setTrail).catch((err) => setError(err.message));
  };
  useEffect(load, [params.id]);

  const save = async () => {
    setSaving(true);
    try {
      const body = batchBody(trail.features, picked, { riddenOn: params.date || localDay(), rideId: params.rideId, makeId: uuid });
      const result = await logBatch(body, logout);
      if (result.queued) {
        Alert.alert('Saved for later', "No signal right now. Your logs will send when you're back in range.");
        navigation.goBack();
        return;
      }
      const firsts = result.logs.filter((l) => l.first_clean).map((l) => l.feature_name);
      const lines = [result.points ? `${points(result.points)} for this trail.` : 'Logged. Every go counts.'];
      if (firsts.length) lines.push(`First clean${firsts.length > 1 ? 's' : ''}: ${firsts.join(', ')}`);
      if (result.leveled_up) lines.push(`Level up! Level ${result.level.level} · ${result.level.title}`);
      Alert.alert('Logged', lines.join('\n'), [{ text: 'OK', onPress: () => announceAchievements(result.new_achievements) }]);
      navigation.goBack();
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };

  if (!trail && error) return <ErrorState message={error} onRetry={load} />;
  if (!trail) return <Loading />;

  const summary = pickedSummary(picked);
  return (
    <View style={ui.screen}>
      <ScrollView contentContainerStyle={ui.scroll}>
        <Header caption="Log this trail" />
        <Text style={ui.title}>{trail.name}</Text>
        <Text style={ui.subtitle}>Tap how each one went. Skip any you didn't ride.</Text>
        {trail.features.map((f) => (
          <View key={f.id} style={ui.card}>
            <View style={ui.row}>
              <FeatureThumb feature={f} size={44} />
              <View style={{ flex: 1 }}>
                <Text style={ui.strong} numberOfLines={1}>{f.name}</Text>
                <Text style={ui.small}>{featureMeta(f)}{f.has_ride_around ? ' · ride-around' : ''}</Text>
              </View>
            </View>
            <OutcomeButtons compact selected={picked[f.id]}
              onPick={(outcome) => setPicked((p) => ({ ...p, [f.id]: outcome }))} />
          </View>
        ))}
      </ScrollView>
      <View style={{ padding: 20, paddingTop: 8 }}>
        <Button
          title={summary.picked ? `Save ${summary.picked} feature${summary.picked === 1 ? '' : 's'}` : 'Pick at least one'}
          disabled={!summary.picked} loading={saving} onPress={save} />
      </View>
    </View>
  );
}
