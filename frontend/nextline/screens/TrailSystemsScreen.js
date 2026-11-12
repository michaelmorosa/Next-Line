// The Trails tab: trail systems with the rider's progress, and a way to their own timed trails.
import { useCallback, useState } from 'react';
import { FlatList, RefreshControl, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import { ErrorState, Loading, ProgressBar } from '../components/ui';
import { progressLine } from '../utils/features';
import { syncPendingLogs } from '../utils/logging';
import { colors, ui } from '../theme';

export default function TrailSystemsScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [systems, setSystems] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    try {
      await syncPendingLogs(logout).catch(() => {});
      setSystems(await fetchJson('/api/systems/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, []));

  if (!systems && error) return <ErrorState message={error} onRetry={load} />;
  if (!systems) return <Loading />;

  return (
    <FlatList
      style={ui.screen}
      contentContainerStyle={ui.scroll}
      data={systems}
      keyExtractor={(s) => String(s.id)}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      ListHeaderComponent={(
        <View style={{ gap: 4, marginBottom: 2 }}>
          <Text style={ui.title}>Trails</Text>
          <Text style={ui.subtitle}>Every feature here is photographed and graded by the Next Line team.</Text>
        </View>
      )}
      ListEmptyComponent={(
        <View style={ui.card}>
          <Text style={ui.strong}>No trail systems yet</Text>
          <Text style={ui.small}>Our team is out grading features. They'll show up here once they're certified.</Text>
        </View>
      )}
      ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
      renderItem={({ item: s }) => (
        <TouchableOpacity style={ui.card} onPress={() => navigation.navigate('System', { id: s.id })}>
          <View style={ui.between}>
            <Text style={ui.label} numberOfLines={1}>{s.location || 'Trail system'}{s.is_demo ? ' · demo' : ''}</Text>
            <Text style={ui.small}>{s.trail_count} trail{s.trail_count === 1 ? '' : 's'}</Text>
          </View>
          <Text style={[ui.strong, { fontSize: 20 }]} numberOfLines={1}>{s.name}</Text>
          <Text style={ui.small}>{progressLine(s.cleaned_count, s.feature_count)}</Text>
          {s.feature_count > 0 && <ProgressBar fraction={s.cleaned_count / s.feature_count} />}
        </TouchableOpacity>
      )}
      ListFooterComponent={(
        <TouchableOpacity style={[ui.card, ui.row, { marginTop: 12 }]} onPress={() => navigation.navigate('TimedTrails')}>
          <Ionicons name="stopwatch-outline" size={20} color={colors.accent} />
          <View style={{ flex: 1 }}>
            <Text style={ui.strong}>Your timed trails</Text>
            <Text style={ui.small}>Laps, PRs and climbs from your recorded rides.</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.muted} />
        </TouchableOpacity>
      )}
    />
  );
}
