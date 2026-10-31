import { useCallback, useState } from 'react';
import { FlatList, RefreshControl, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import { ErrorState, Loading, ProgressBar } from '../components/ui';
import { directionLabel, duration, km } from '../utils/format';
import { DIFFICULTY, colors, ui } from '../theme';

export default function TrailsScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [trails, setTrails] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    try {
      setTrails(await fetchJson('/api/trails/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, []));

  if (!trails && error) return <ErrorState message={error} onRetry={load} />;
  if (!trails) return <Loading />;

  return (
    <FlatList
      style={ui.screen}
      contentContainerStyle={ui.scroll}
      data={trails}
      keyExtractor={(t) => String(t.id)}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      ListHeaderComponent={(
        <View style={{ gap: 4, marginBottom: 2 }}>
          <Text style={ui.title}>Trails</Text>
          <Text style={ui.subtitle}>Descents and climbs you ride more than once become timed segments automatically.</Text>
        </View>
      )}
      ListEmptyComponent={(
        <View style={ui.card}>
          <Text style={ui.strong}>No trails yet</Text>
          <Text style={ui.small}>Ride the same descent or climb twice and it shows up here with your times.</Text>
        </View>
      )}
      ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
      renderItem={({ item: t }) => {
        const difficulty = DIFFICULTY[t.difficulty] || DIFFICULTY.unrated;
        return (
          <TouchableOpacity style={ui.card} onPress={() => navigation.navigate('Trail', { id: t.id })}>
            <View style={ui.between}>
              <Text style={[ui.label, { color: difficulty.color }]}>
                {directionLabel(t.direction)} · {difficulty.label} · {km(t.length_m)} km
              </Text>
              <Text style={ui.small}>best {duration(t.best_s)}</Text>
            </View>
            <Text style={[ui.strong, { fontSize: 18 }]} numberOfLines={1}>{t.name}</Text>
            <Text style={ui.small}>
              {t.laps} full lap{t.laps === 1 ? '' : 's'} · {t.clean_laps} clean
              {t.feature_count ? ` · ${t.cleaned_count} / ${t.feature_count} features` : ''}
            </Text>
            {t.feature_count > 0 && <ProgressBar fraction={t.cleaned_count / t.feature_count} />}
          </TouchableOpacity>
        );
      }}
    />
  );
}
