// A trail system: map, next up here, trails with the rider's progress, and the ladders.
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import NextUpList from '../components/NextUpList';
import TrailMap from '../components/TrailMap';
import { ErrorState, Header, Loading, ProgressBar } from '../components/ui';
import { progressLine } from '../utils/features';
import { km } from '../utils/format';
import { DIFFICULTY, colors, ui } from '../theme';

export default function SystemScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [system, setSystem] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    try {
      setSystem(await fetchJson(`/api/systems/${params.id}/`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  if (!system && error) return <ErrorState message={error} onRetry={load} />;
  if (!system) return <Loading />;

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
      <Header caption={system.location || 'Trail system'} />
      <Text style={ui.title}>{system.name}</Text>
      {system.is_demo && <Text style={[ui.small, { color: colors.warn }]}>Demo trail system: made-up trails for trying the app.</Text>}
      {system.description ? <Text style={ui.subtitle}>{system.description}</Text> : null}

      <TrailMap trails={system.trails} features={system.features}
        onFeaturePress={(f) => navigation.navigate('Feature', { id: f.id })} />

      <View style={ui.cardRaised}>
        <Text style={ui.strong}>{progressLine(system.cleaned_count, system.feature_count)}</Text>
        {system.feature_count > 0 && <ProgressBar fraction={system.cleaned_count / system.feature_count} />}
      </View>

      <View style={ui.card}>
        <Text style={ui.label}>Next up when you're ready</Text>
        <NextUpList items={system.next_up} empty="Nothing new to suggest here yet. Log the features you ride and new ones open up." />
      </View>

      <Text style={[ui.label, { marginTop: 6 }]}>Trails</Text>
      {system.trails.map((t) => {
        const difficulty = DIFFICULTY[t.difficulty] || DIFFICULTY.unrated;
        return (
          <TouchableOpacity key={t.id} style={ui.card} onPress={() => navigation.navigate('TrailFeatures', { id: t.id })}>
            <View style={ui.between}>
              <Text style={[ui.label, { color: difficulty.color }]}>{difficulty.label} · {km(t.length_m)} km</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </View>
            <Text style={[ui.strong, { fontSize: 18 }]}>{t.name}</Text>
            <Text style={ui.small}>{progressLine(t.cleaned_count, t.feature_count)}</Text>
            {t.feature_count > 0 && <ProgressBar fraction={t.cleaned_count / t.feature_count} />}
          </TouchableOpacity>
        );
      })}

      {system.ladders.length > 0 && (
        <TouchableOpacity style={ui.card} onPress={() => navigation.navigate('Ladders', { id: system.id })}>
          <View style={ui.between}>
            <Text style={ui.label}>Ladders</Text>
            <Text style={[ui.small, { color: colors.accent }]}>All ›</Text>
          </View>
          {system.ladders.map((l) => (
            <View key={l.type} style={ui.between}>
              <Text style={ui.body}>{l.label}</Text>
              <Text style={ui.small}>
                {l.cleaned} of {l.total}{l.best_grade ? ` · best grade ${l.best_grade}` : ''}
              </Text>
            </View>
          ))}
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}
