import { useEffect, useMemo, useState } from 'react';
import { Alert, ScrollView, Share, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson, sendJson } from '../api';
import { announceAchievements } from '../utils/achievements';
import { useAuth } from '../AuthContext';
import FlowRing from '../components/FlowRing';
import RideMap from '../components/RideMap';
import { Button, CircleButton, ErrorState, Grid, Header, Loading, StatTile } from '../components/ui';
import { climbRate, day, delta, duration, feetDown, km, metres, seconds, shortDuration } from '../utils/format';
import { colors, fonts, ui } from '../theme';

const LEVEL_PART_NAMES = { features: 'features', speed: 'speed', air: 'air', descent: 'descending', climbing: 'climbing' };

const NEXT_STATUS = { locked: 'almost', almost: 'cleaned', cleaned: 'locked' };
const STATUS_STYLE = {
  cleaned: { dot: colors.good, mark: '✓', label: 'Cleaned' },
  almost: { dot: colors.warn, mark: '!', label: 'Almost' },
  locked: { dot: colors.dotMuted, mark: '', label: 'Not this time' },
};

function shareText(ride) {
  const lines = [`${ride.title || 'Ride'} · ${day(ride.started_at)}`];
  lines.push(`${km(ride.distance_m)} km · ${metres(ride.climb_m)} m up · ${metres(ride.descent_m)} m down`);
  if (ride.climb_rate) lines.push(`Climbing ${climbRate(ride.climb_rate)}`);
  if (ride.jump_count) lines.push(`${ride.jump_count} jumps · biggest air ${seconds(ride.biggest_air_s)}`);
  if (ride.pr_count) lines.push(`${ride.pr_count} descent PR${ride.pr_count > 1 ? 's' : ''}`);
  if (ride.flow_score != null) lines.push(`Flow ${Math.round(ride.flow_score)}`);
  lines.push('Recorded with Next Line');
  return lines.join('\n');
}

function lapsSub(ride) {
  if (!ride.laps.length) return 'No full trail runs';
  if (ride.laps.length === 1) return `on ${ride.laps[0].trail_name}`;
  return `on ${ride.laps.length} trails`;
}

// "Lap 2" labels for trails ridden more than once on this ride.
function lapNumbers(efforts) {
  const totals = {};
  efforts.forEach((e) => { totals[e.trail] = (totals[e.trail] || 0) + 1; });
  const seen = {};
  return Object.fromEntries(efforts.map((e) => {
    seen[e.trail] = (seen[e.trail] || 0) + 1;
    return [e.id, totals[e.trail] > 1 ? `Lap ${seen[e.trail]} · ` : ''];
  }));
}

// One line on climbing stamina: did the rider hold their pace, and how often did they stop?
function staminaLine(ride) {
  const rests = ride.climb_rests
    ? ` ${ride.climb_rests} rest stop${ride.climb_rests === 1 ? '' : 's'} on climbs.`
    : ' No rest stops on climbs.';
  const held = ride.climb_pace_held;
  if (held == null) return `Climb for 4+ minutes to see how well you hold your pace.${rests}`;
  if (held >= 95) return `You held your climbing pace all ride.${rests}`;
  if (held >= 85) return `A slight fade on the later climbs.${rests}`;
  return `You slowed a lot on the later climbs: pacing or fitness to work on.${rests}`;
}

function flowLine(ride) {
  if (ride.flow_score == null) return { headline: 'No descent long enough to score', sub: 'Flow needs a sustained downhill.' };
  if (ride.flow_vs_avg == null) return { headline: 'Your first flow score', sub: 'Steadier speed on descents scores higher.' };
  const best = [...ride.efforts].filter((e) => e.flow_score != null).sort((a, b) => b.flow_score - a.flow_score)[0];
  return {
    headline: `${ride.flow_vs_avg >= 0 ? '+' : '−'}${Math.abs(ride.flow_vs_avg)} vs your average`,
    sub: best ? `Smoothest on ${best.trail_name}` : 'Speed steadiness on descents',
  };
}

export default function RideSummaryScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [ride, setRide] = useState(null);
  const [error, setError] = useState(null);
  const [checkin, setCheckin] = useState({ confidence: null, crashed: false, touchdowns: 0, statuses: {} });
  const [saving, setSaving] = useState(false);

  const apply = (data) => {
    setRide(data);
    const statuses = {};
    for (const f of data.features) {
      statuses[f.id] = data.cleaned_features.includes(f.id) ? 'cleaned' : (f.status === 'almost' ? 'almost' : 'locked');
    }
    setCheckin({ confidence: data.confidence, crashed: data.crashed, touchdowns: data.touchdowns, statuses });
  };

  const load = () => {
    setError(null);
    fetchJson(`/api/rides/${params.id}/`, { logout }).then(apply).catch((err) => setError(err.message));
  };
  useEffect(load, [params.id]);
  // Earned by the upload that opened this screen.
  useEffect(() => { announceAchievements(params.newAchievements); }, [params.newAchievements]);

  const path = useMemo(() => (ride ? ride.track.map((p) => [p[1], p[2]]) : []), [ride]);

  const save = async () => {
    setSaving(true);
    const ids = (status) => Object.keys(checkin.statuses).filter((id) => checkin.statuses[id] === status).map(Number);
    try {
      const saved = await sendJson(`/api/rides/${ride.id}/checkin/`, 'POST', {
        confidence: checkin.confidence,
        crashed: checkin.crashed,
        touchdowns: checkin.touchdowns,
        cleaned: ids('cleaned'),
        almost: ids('almost'),
      }, logout);
      apply(saved);
      if (!announceAchievements(saved.new_achievements)) Alert.alert('Saved', 'Your check-in is in. Nice riding.');
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = () => Alert.alert('Delete this ride?', 'Its times and jumps will be removed.', [
    { text: 'Cancel', style: 'cancel' },
    {
      text: 'Delete', style: 'destructive', onPress: async () => {
        try {
          await sendJson(`/api/rides/${ride.id}/`, 'DELETE', undefined, logout);
          navigation.goBack();
        } catch (err) {
          Alert.alert("Couldn't delete", err.message);
        }
      },
    },
  ]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!ride) return <Loading />;

  const flow = flowLine(ride);
  const trailCount = new Set(ride.efforts.map((e) => e.trail)).size;
  const byTrail = ride.features.reduce((acc, f) => ({ ...acc, [f.trail]: [...(acc[f.trail] || []), f] }), {});
  const trailNames = Object.fromEntries(ride.efforts.map((e) => [e.trail, e.trail_name]));
  const lapLabels = lapNumbers(ride.efforts);
  const descentLaps = ride.efforts.filter((e) => e.trail_direction === 'descent').length;
  const gain = ride.level_gain;
  const gainParts = gain ? Object.entries(gain.parts).filter(([, v]) => v > 0)
    .map(([k, v]) => `+${v} ${LEVEL_PART_NAMES[k] || k}`) : [];
  const setTouchdowns = (n) => setCheckin((c) => ({ ...c, touchdowns: Math.max(0, n) }));

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header
        caption={`${day(ride.started_at)} · ${shortDuration(ride.elapsed_s)}`}
        right={<CircleButton icon="share-outline" label="Share" onPress={() => Share.share({ message: shareText(ride) })} />}
      />
      <View>
        <Text style={ui.title}>{ride.title || 'Ride'}</Text>
        <Text style={ui.subtitle}>
          {km(ride.distance_m)} km · {metres(ride.climb_m)} m up · {metres(ride.descent_m)} m down · {trailCount} segment{trailCount === 1 ? '' : 's'}
        </Text>
      </View>

      {path.length > 1 && <RideMap path={path} jumps={ride.jumps} />}

      <View style={[ui.cardRaised, ui.row, { gap: 16 }]}>
        <FlowRing score={ride.flow_score} />
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={ui.label}>Flow score</Text>
          <Text style={[ui.strong, { fontSize: 16 }]}>{flow.headline}</Text>
          <Text style={ui.small}>{flow.sub}</Text>
        </View>
      </View>

      <Grid>
        <StatTile label="Jumps" value={ride.jump_count} sub={`${seconds(ride.total_air_s)} total air`} />
        <StatTile
          label="Biggest air"
          value={seconds(ride.biggest_air_s)}
          sub={ride.biggest_air_is_pb ? 'New personal best' : 'Longest airtime'}
          subColor={ride.biggest_air_is_pb ? colors.good : undefined}
        />
        <StatTile
          label="Descent PRs"
          value={ride.pr_count}
          sub={`of ${descentLaps} descent lap${descentLaps === 1 ? '' : 's'}`}
        />
        <StatTile
          label="Speed rank"
          value={ride.speed_rank != null ? `Top ${ride.speed_rank}%` : '—'}
          sub={ride.speed_rank != null ? 'of riders on these trails' : 'No other riders here yet'}
        />
        <StatTile label="Full laps" value={ride.lap_count} sub={lapsSub(ride)} />
        <StatTile
          label="Touchdowns"
          value={ride.touchdowns}
          sub={ride.touchdowns === 0 ? 'Clean on every lap' : 'Feet down on trail laps'}
          subColor={ride.touchdowns === 0 ? colors.good : undefined}
        />
      </Grid>

      {gain && (
        <TouchableOpacity style={ui.cardRaised} onPress={() => navigation.navigate('LevelGuide')}>
          <View style={ui.between}>
            <Text style={ui.label}>Rider level</Text>
            <Text style={[ui.number, { fontSize: 28, color: gain.points > 0 ? colors.good : colors.muted }]}>
              +{gain.points}
            </Text>
          </View>
          {gain.tier_after !== gain.tier_before && (
            <Text style={[ui.strong, { color: colors.accent }]}>New tier: {gain.tier_after}</Text>
          )}
          {gainParts.length > 0 && <Text style={ui.small}>{gainParts.join(' · ')}</Text>}
          {gain.highlights.map((h) => <Text key={h} style={ui.body}>• {h}</Text>)}
          {gain.points === 0 && (
            <Text style={ui.small}>
              No new bests this time. Mark features you cleaned below; it's the biggest source of points.
            </Text>
          )}
          <Text style={[ui.small, { color: colors.accent }]}>How rider level works ›</Text>
        </TouchableOpacity>
      )}

      {ride.climb_time_s > 0 && (
        <View style={ui.card}>
          <View style={ui.between}>
            <Text style={ui.label}>Climbing stamina</Text>
            <Text style={ui.small}>
              {duration(ride.climb_time_s)} climbing
              {ride.climb_pr_count ? ` · ${ride.climb_pr_count} climb PR${ride.climb_pr_count > 1 ? 's' : ''}` : ''}
            </Text>
          </View>
          <Grid columns={3}>
            <StatTile value={climbRate(ride.climb_rate)} sub="climb rate" center small />
            <StatTile
              value={ride.climb_pace_held != null ? `${ride.climb_pace_held}%` : '—'}
              sub="pace held"
              subColor={ride.climb_pace_held >= 95 ? colors.good : undefined}
              center
              small
            />
            <StatTile value={`${Math.round(ride.longest_nonstop_climb_m)} m`} sub="longest non-stop" center small />
          </Grid>
          <Text style={ui.small}>{staminaLine(ride)}</Text>
        </View>
      )}

      {ride.efforts.length > 0 && (
        <View style={ui.card}>
          <Text style={ui.label}>Laps</Text>
          {ride.efforts.map((e) => (
            <TouchableOpacity key={e.id} style={ui.between} onPress={() => navigation.navigate('Trail', { id: e.trail })}>
              <Ionicons
                name={e.trail_direction === 'climb' ? 'arrow-up' : 'arrow-down'}
                size={16}
                color={colors.muted}
                style={{ marginRight: 8 }}
              />
              <View style={{ flex: 1 }}>
                <Text style={ui.body} numberOfLines={1}>{e.trail_name}</Text>
                <Text style={[ui.small, e.touchdowns === 0 && { color: colors.good }]}>
                  {lapLabels[e.id]}{feetDown(e.touchdowns)}
                  {e.climb_rate != null ? ` · ${climbRate(e.climb_rate)}` : ''}
                </Text>
              </View>
              <Text style={[ui.strong, e.is_pr && { color: colors.good }]}>
                {duration(e.elapsed_s)}
                {e.previous_best_s != null ? `  ${delta(e.elapsed_s - e.previous_best_s)}` : ''}
                {e.is_pr ? '  PR' : ''}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      <View style={ui.card}>
        <Text style={ui.label}>10-second check-in</Text>
        <Text style={ui.strong}>How confident did you feel?</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[1, 2, 3, 4, 5].map((n) => {
            const selected = checkin.confidence === n;
            return (
              <TouchableOpacity
                key={n}
                style={[styles.rating, selected && styles.ratingSelected]}
                onPress={() => setCheckin((c) => ({ ...c, confidence: n }))}
                accessibilityLabel={`Confidence ${n}`}
                accessibilityState={{ selected }}
              >
                <Text style={[ui.body, { fontSize: 16 }, selected && { color: colors.bg, fontFamily: fonts.semibold }]}>{n}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {Object.entries(byTrail).map(([trailId, features]) => (
          <View key={trailId} style={{ gap: 8 }}>
            <Text style={[ui.small, { marginTop: 6 }]}>Features on {trailNames[trailId]} · tap to mark</Text>
            {features.map((f) => {
              const status = checkin.statuses[f.id] || 'locked';
              const s = STATUS_STYLE[status];
              return (
                <TouchableOpacity
                  key={f.id}
                  style={[ui.row, styles.feature]}
                  onPress={() => setCheckin((c) => ({ ...c, statuses: { ...c.statuses, [f.id]: NEXT_STATUS[status] } }))}
                >
                  <View style={[styles.mark, { backgroundColor: s.dot }]}><Text style={styles.markText}>{s.mark}</Text></View>
                  <Text style={[ui.body, { flex: 1 }]}>{f.name}{f.approved ? '' : ' (awaiting approval)'}</Text>
                  <Text style={[ui.small, { color: s.dot === colors.dotMuted ? colors.muted : s.dot }]}>{s.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        ))}
        {ride.efforts.length > 0 && ride.features.length === 0 && (
          <Text style={ui.small}>No features pinned on these trails yet. Pin drops and rock gardens from the trail page.</Text>
        )}

        <View style={ui.between}>
          <View style={{ flex: 1 }}>
            <Text style={ui.body}>Times you put a foot down</Text>
            <Text style={ui.small}>We estimated {ride.touchdowns_detected} from your stops on descents</Text>
          </View>
          <View style={[ui.row, { gap: 8 }]}>
            <TouchableOpacity style={styles.stepper} onPress={() => setTouchdowns(checkin.touchdowns - 1)} accessibilityLabel="One fewer">
              <Text style={styles.stepperText}>−</Text>
            </TouchableOpacity>
            <Text style={[ui.number, { fontSize: 26, minWidth: 28, textAlign: 'center' }]}>{checkin.touchdowns}</Text>
            <TouchableOpacity style={styles.stepper} onPress={() => setTouchdowns(checkin.touchdowns + 1)} accessibilityLabel="One more">
              <Text style={styles.stepperText}>+</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={ui.between}>
          <Text style={ui.body}>I crashed on this ride</Text>
          <Switch value={checkin.crashed} onValueChange={(v) => setCheckin((c) => ({ ...c, crashed: v }))}
            trackColor={{ true: colors.accent, false: colors.border }} thumbColor={colors.text} />
        </View>
        <Button title={ride.checked_in_at ? 'Update check-in' : 'Save check-in'} onPress={save} loading={saving} />
      </View>

      {ride.efforts[0] && (
        <Button title="Pin a feature on this trail →" variant="secondary"
          onPress={() => navigation.navigate('Trail', { id: ride.efforts[0].trail })} />
      )}
      <Button title="Delete ride" variant="danger" onPress={remove} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  rating: { flex: 1, height: 44, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  ratingSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  feature: { minHeight: 44, paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.cardRaised },
  mark: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  markText: { color: colors.bg, fontFamily: fonts.semibold, fontSize: 14 },
  stepper: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  stepperText: { fontFamily: fonts.semibold, fontSize: 20, color: colors.text },
});
