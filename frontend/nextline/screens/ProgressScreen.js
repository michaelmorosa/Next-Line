import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import Sparkline from '../components/Sparkline';
import SuggestionRow from '../components/SuggestionRow';
import { ErrorState, Grid, Loading, StatTile } from '../components/ui';
import { climbRate, delta, duration } from '../utils/format';
import { colors, fonts, ui } from '../theme';

// Achievements earned this recently get a NEW tag.
const NEW_ACHIEVEMENT_MS = 7 * 86400000;

// Where rider level points come from, in the order shown under the level.
const LEVEL_PARTS = [
  ['features', 'Features'], ['speed', 'Speed'], ['air', 'Air'], ['descent', 'Descending'], ['climbing', 'Climbing'],
];

// Weekly bars for one value of `weeks` (latest week highlighted). Empty weeks get a stub.
function WeekBars({ weeks, field = 'flow' }) {
  const scored = weeks.map((w) => w[field]).filter((v) => v != null);
  const floor = Math.max(0, Math.min(...scored, 100) - 15);
  const top = Math.max(...scored, floor + 1);
  const last = weeks.length - 1;
  return (
    <View style={styles.bars}>
      {weeks.map((w, i) => (
        <View key={w.week_start} style={styles.barCol}>
          <Text style={styles.barValue}>{w[field] ?? ''}</Text>
          <View style={[
            styles.bar,
            {
              height: w[field] == null ? 2 : 10 + ((w[field] - floor) / (top - floor)) * 80,
              backgroundColor: i === last ? colors.accent : colors.barMuted,
            },
          ]} />
        </View>
      ))}
    </View>
  );
}

export default function ProgressScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    try {
      setData(await fetchJson('/api/progress/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, []));

  if (!data && error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Loading />;

  const { level, totals, favorite_trail: fav, favorite_climb: favClimb } = data;
  // Missing from servers older than climb tracking.
  const climbing = data.climbing || { weeks: [], latest: null, best_climb_rate: null, longest_nonstop_m: 0 };
  const hasFlow = data.flow_weeks.some((w) => w.flow != null);
  const achievementList = data.achievements || [];
  const suggestions = data.suggestions || [];
  const earned = achievementList.filter((a) => a.earned_at);
  const locked = achievementList.filter((a) => !a.earned_at);
  const hasClimbing = climbing.weeks.some((w) => w.climb_rate != null);

  return (
    <ScrollView
      style={ui.screen}
      contentContainerStyle={ui.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
    >
      <Text style={ui.title}>Progress</Text>

      <TouchableOpacity style={[ui.cardRaised, { padding: 18 }]} onPress={() => navigation.navigate('LevelGuide')}>
        <View style={ui.between}>
          <View style={{ gap: 4 }}>
            <Text style={ui.label}>Rider level</Text>
            <Text style={styles.level}>{level.points.toLocaleString()}</Text>
            <Text style={[ui.body, { fontSize: 14, color: level.gain_30d > 0 ? colors.good : colors.muted }]}>
              {level.gain_30d > 0 ? `+${level.gain_30d} in the last 30 days` : 'Ride to level up'}
            </Text>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 4, flexShrink: 1 }}>
            <Text style={ui.strong}>{level.tier}</Text>
            {level.tier_number && <Text style={ui.small}>Tier {level.tier_number} of {level.tier_count}</Text>}
            {level.next_tier && (
              <Text style={ui.small}>
                {level.to_next > 0
                  ? `${level.to_next.toLocaleString()} to ${level.next_tier}`
                  : `Points ready for ${level.next_tier}`}
              </Text>
            )}
            {(level.requirements || []).filter((r) => !r.met).map((r) => (
              <Text key={r.kind} style={[ui.small, { color: colors.warn, textAlign: 'right' }]}>
                {r.have}/{r.needed} · {r.label}
              </Text>
            ))}
          </View>
        </View>
        <Text style={ui.small}>
          {LEVEL_PARTS.filter(([key]) => level.parts[key] != null)
            .map(([key, label]) => `${label} ${level.parts[key]}`).join(' · ')}
        </Text>
        <Text style={[ui.small, { color: colors.accent }]}>How rider level works ›</Text>
      </TouchableOpacity>

      {suggestions.length > 0 && (
        <View style={ui.card}>
          <View style={ui.between}>
            <Text style={ui.label}>Ways to level up</Text>
            <Text style={[ui.small, { color: colors.accent }]} onPress={() => navigation.navigate('LevelGuide')}>All ›</Text>
          </View>
          {suggestions.slice(0, 3).map((s) => <SuggestionRow key={`${s.kind}-${s.title}`} suggestion={s} />)}
        </View>
      )}

      <View style={ui.card}>
        <View style={ui.between}>
          <Text style={ui.label}>Flow score · 8 weeks</Text>
          {data.flow_avg != null && <Text style={ui.small}>avg {data.flow_avg}</Text>}
        </View>
        {hasFlow ? <WeekBars weeks={data.flow_weeks} /> : (
          <Text style={ui.small}>Ride a few descents and your weekly flow shows up here. It's your own trend, not a ranking.</Text>
        )}
      </View>

      {fav && (
        <TouchableOpacity style={ui.card} onPress={() => navigation.navigate('Trail', { id: fav.id })}>
          <Text style={ui.label} numberOfLines={1}>{fav.name} · descent time</Text>
          <Sparkline values={fav.efforts.map((e) => e.elapsed_s)} />
          <View style={ui.between}>
            <Text style={ui.small}>First ride {duration(fav.first_s)}</Text>
            <Text style={ui.strong}>
              Now {duration(fav.latest_s)}{fav.latest_s !== fav.first_s ? ` · ${delta(fav.latest_s - fav.first_s)}` : ''}
            </Text>
          </View>
        </TouchableOpacity>
      )}

      <View style={ui.card}>
        <View style={ui.between}>
          <Text style={ui.label}>Climbing stamina · 8 weeks</Text>
          {climbing.best_climb_rate != null && <Text style={ui.small}>best {climbRate(climbing.best_climb_rate)}</Text>}
        </View>
        {hasClimbing ? (
          <>
            <WeekBars weeks={climbing.weeks} field="climb_rate" />
            <Text style={ui.small}>Climb rate: vertical metres per hour on climbs. Higher is fitter.</Text>
            <Grid>
              <StatTile
                value={climbing.latest?.climb_pace_held != null ? `${climbing.latest.climb_pace_held}%` : '—'}
                sub="pace held, last ride"
                center
                small
              />
              <StatTile value={`${climbing.longest_nonstop_m} m`} sub="longest non-stop climb" center small />
            </Grid>
          </>
        ) : (
          <Text style={ui.small}>Climb a few hills and your climbing fitness and stamina show up here.</Text>
        )}
      </View>

      {favClimb && (
        <TouchableOpacity style={ui.card} onPress={() => navigation.navigate('Trail', { id: favClimb.id })}>
          <Text style={ui.label} numberOfLines={1}>{favClimb.name} · climb time</Text>
          <Sparkline values={favClimb.efforts.map((e) => e.elapsed_s)} />
          <View style={ui.between}>
            <Text style={ui.small}>First climb {duration(favClimb.first_s)}</Text>
            <Text style={ui.strong}>
              Now {duration(favClimb.latest_s)}
              {favClimb.latest_s !== favClimb.first_s ? ` · ${delta(favClimb.latest_s - favClimb.first_s)}` : ''}
            </Text>
          </View>
        </TouchableOpacity>
      )}

      <Grid columns={3}>
        <StatTile value={totals.features_cleaned} sub="features cleaned" center small />
        <StatTile value={`${Math.round(totals.air_this_month_s)} s`} sub="air this month" center small />
        <StatTile value={`${totals.streak_weeks} wk`} sub="ride streak" center small />
      </Grid>

      <View style={[ui.card, { flexDirection: 'row', alignItems: 'center' }]}>
        <View style={styles.milestoneDot} />
        <Text style={[ui.body, { flex: 1, fontSize: 14 }]}>
          <Text style={{ fontFamily: fonts.semibold }}>Next milestone: </Text>
          <Text style={{ color: colors.muted }}>{data.next_milestone}</Text>
        </Text>
      </View>

      <View style={ui.card}>
        <View style={ui.between}>
          <Text style={ui.label}>Achievements</Text>
          <Text style={ui.small}>{earned.length} / {achievementList.length}</Text>
        </View>
        <View style={styles.badges}>
          {[...earned, ...locked].map((a) => {
            const fresh = a.earned_at && Date.now() - new Date(a.earned_at).getTime() < NEW_ACHIEVEMENT_MS;
            return (
              <View key={a.key} style={[styles.badge, a.earned_at && styles.badgeEarned]}>
                <View style={ui.between}>
                  <Ionicons name={a.earned_at ? 'trophy' : 'lock-closed'} size={18}
                    color={a.earned_at ? colors.warn : colors.muted} />
                  {fresh && <Text style={styles.newTag}>NEW</Text>}
                </View>
                <Text style={[ui.strong, { fontSize: 14 }, !a.earned_at && { color: colors.muted }]}>{a.title}</Text>
                <Text style={[ui.small, { fontSize: 12 }]}>{a.description}</Text>
              </View>
            );
          })}
        </View>
      </View>

      <Text style={[ui.small, { textAlign: 'center' }]}>
        This week: {totals.rides_this_week} ride{totals.rides_this_week === 1 ? '' : 's'} ·{' '}
        {(totals.distance_this_week_m / 1000).toFixed(1)} km · {totals.climb_this_week_m} m up · {totals.descent_this_week_m} m down
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  level: { fontFamily: fonts.display, fontSize: 56, lineHeight: 58, color: colors.text },
  bars: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, height: 115 },
  barCol: { flex: 1, alignItems: 'center', gap: 4 },
  barValue: { fontFamily: fonts.regular, fontSize: 11, color: colors.muted },
  bar: { width: '100%', borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  milestoneDot: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.warn },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  badge: {
    width: '48.5%', padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, gap: 4, opacity: 0.55,
  },
  badgeEarned: { backgroundColor: colors.cardRaised, borderColor: colors.cardRaised, opacity: 1 },
  newTag: { fontFamily: fonts.semibold, fontSize: 11, color: colors.accent, letterSpacing: 0.8 },
});
