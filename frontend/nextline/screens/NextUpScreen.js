// The Next up tab: features the rider is ready for, with why, never skipping a rung.
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import NextUpList from '../components/NextUpList';
import { ErrorState, Loading } from '../components/ui';
import { syncPendingLogs } from '../utils/logging';
import { colors, ui } from '../theme';

export default function NextUpScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [data, setData] = useState(null);
  const [pending, setPending] = useState(0);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    try {
      const sync = await syncPendingLogs(logout).catch(() => ({ left: 0 }));
      setPending(sync.left);
      setData(await fetchJson('/api/next-up/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, []));

  if (!data && error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Loading />;

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
      <Text style={ui.title}>Next up</Text>
      <Text style={ui.subtitle}>
        For when you're ready. Each one is at most a grade above what you've cleaned, and only after you've cleaned
        the rungs below it twice.
      </Text>
      {pending > 0 && (
        <Text style={[ui.small, { color: colors.warn }]}>
          {pending} log{pending === 1 ? '' : 's'} waiting for signal. They'll send automatically.
        </Text>
      )}
      <View style={ui.card}>
        <NextUpList items={data.next_up}
          empty="Nothing to suggest yet. Open Trails, pick a trail system, and log the features you ride." />
      </View>
      {!data.advanced_features && (
        <Text style={ui.small} onPress={() => navigation.navigate('Settings')}>
          Features above grade {data.advanced_above_grade} aren't suggested unless you turn on advanced features in
          Settings.
        </Text>
      )}
    </ScrollView>
  );
}
