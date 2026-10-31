import { useCallback, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import { listPending } from '../recording/storage';
import { uploadPending } from '../recording/uploads';
import { Button, CircleButton, ErrorState, Loading } from '../components/ui';
import { day, feetDown, km, metres, shortDuration } from '../utils/format';
import { colors, fonts, ui } from '../theme';

function RideRow({ ride, onPress }) {
  return (
    <TouchableOpacity style={[ui.card, { gap: 6 }]} onPress={onPress}>
      <View style={ui.between}>
        <Text style={ui.label}>{day(ride.started_at)} · {shortDuration(ride.elapsed_s)}</Text>
        {!ride.checked_in_at && <Text style={[ui.small, { color: colors.accent }]}>Check in</Text>}
      </View>
      <Text style={styles.rideTitle} numberOfLines={1}>{ride.title || 'Ride'}</Text>
      <Text style={ui.small}>
        {km(ride.distance_m)} km · {metres(ride.climb_m)} m up · {metres(ride.descent_m)} m down · {ride.jump_count} jumps
        {ride.lap_count ? ` · ${ride.lap_count} lap${ride.lap_count > 1 ? 's' : ''}` : ''}
        {ride.lap_count ? ` · ${feetDown(ride.touchdowns)}` : ''}
        {ride.flow_score != null ? ` · flow ${Math.round(ride.flow_score)}` : ''}
        {ride.pr_count ? ` · ${ride.pr_count} PR${ride.pr_count > 1 ? 's' : ''}` : ''}
      </Text>
    </TouchableOpacity>
  );
}

export default function RidesScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [rides, setRides] = useState(null);
  const [pending, setPending] = useState([]);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async ({ upload = true } = {}) => {
    setError(null);
    if (upload && listPending().length) await uploadPending(logout);
    setPending(listPending());
    try {
      setRides(await fetchJson('/api/rides/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  };

  useFocusEffect(useCallback(() => {
    load();
  }, []));

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (!rides && error) return <ErrorState message={error} onRetry={load} />;
  if (!rides) return <Loading />;

  return (
    <FlatList
      style={ui.screen}
      contentContainerStyle={ui.scroll}
      data={rides}
      keyExtractor={(r) => String(r.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.accent} />}
      ListHeaderComponent={(
        <View style={{ gap: 14 }}>
          <View style={ui.between}>
            <Text style={ui.title}>Rides</Text>
            <CircleButton icon="settings-outline" label="Settings" onPress={() => navigation.navigate('Settings')} />
          </View>
          {pending.length > 0 && (
            <View style={ui.cardRaised}>
              <Text style={ui.strong}>
                {pending.length} ride{pending.length > 1 ? 's' : ''} waiting to upload
              </Text>
              <Text style={ui.small}>Saved on your phone. They upload automatically when you have signal.</Text>
              <Button title="Upload now" variant="secondary" onPress={refresh} />
            </View>
          )}
          {error && <Text style={ui.error}>{error}</Text>}
        </View>
      )}
      ListEmptyComponent={(
        <View style={[ui.card, { alignItems: 'flex-start' }]}>
          <Text style={ui.strong}>No rides yet</Text>
          <Text style={ui.small}>Tap Record, put your phone in your pocket, and go ride.</Text>
          <Button title="Record a ride" onPress={() => navigation.navigate('Record')} style={{ alignSelf: 'stretch' }} />
        </View>
      )}
      renderItem={({ item }) => (
        <RideRow ride={item} onPress={() => navigation.navigate('RideSummary', { id: item.id })} />
      )}
      ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
    />
  );
}

const styles = StyleSheet.create({
  rideTitle: { fontFamily: fonts.display, fontSize: 26, color: colors.text, textTransform: 'uppercase' },
});
