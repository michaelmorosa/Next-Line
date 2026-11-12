// Every points award, newest first, from the ledger.
import { useCallback, useState } from 'react';
import { FlatList, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import LevelBar from '../components/LevelBar';
import XPRow from '../components/XPRow';
import { ErrorState, Header, Loading } from '../components/ui';
import { colors, ui } from '../theme';

export default function XPHistoryScreen() {
  const { logout } = useAuth();
  const [page, setPage] = useState(null);
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchJson('/api/xp/', { logout });
      setPage(data);
      setEntries(data.results);
    } catch (err) {
      setError(err.message);
    }
  }, [logout]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const more = async () => {
    if (!page?.next_before || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await fetchJson(`/api/xp/?before=${page.next_before}`, { logout });
      setPage(data);
      setEntries((cur) => [...cur, ...data.results]);
    } catch {
      // Scrolling again retries.
    } finally {
      setLoadingMore(false);
    }
  };

  if (error && !page) return <ErrorState message={error} onRetry={load} />;
  if (!page) return <Loading />;

  return (
    <FlatList
      style={ui.screen}
      contentContainerStyle={ui.scroll}
      data={entries}
      keyExtractor={(e) => String(e.id)}
      ListHeaderComponent={(
        <View style={{ gap: 14 }}>
          <Header caption="Points" />
          <Text style={ui.title}>Points history</Text>
          <View style={ui.card}><LevelBar level={page.level} streakWeeks={page.streak_weeks} /></View>
        </View>
      )}
      renderItem={({ item }) => <View style={[ui.card, { paddingVertical: 12 }]}><XPRow entry={item} /></View>}
      ListEmptyComponent={<Text style={ui.small}>No points yet. Log the features you ride, or go for a ride.</Text>}
      ListFooterComponent={loadingMore ? <Text style={[ui.small, { textAlign: 'center', color: colors.muted }]}>Loading…</Text> : null}
      onEndReached={more}
      onEndReachedThreshold={0.5}
    />
  );
}
