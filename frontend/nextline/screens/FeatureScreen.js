// One feature: photos, POV clip, grade, how to ride it, the ride-around, one-tap logging, the rider's history, and
// "Stuck?" tips from the skills it uses. Riders never see a skill tree; skills only appear here as tips.
import { useCallback, useState } from 'react';
import { Alert, Dimensions, Image, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import FeatureVideo from '../components/FeatureVideo';
import { GradeChip, StatusPill } from '../components/FeatureRow';
import OutcomeButtons from '../components/OutcomeButtons';
import SafetyNote from '../components/SafetyNote';
import { Button, ErrorState, Header, Loading } from '../components/ui';
import { announceAchievements } from '../utils/achievements';
import { gradeLabel, measurementList, outcomeLabel, points } from '../utils/features';
import { dateOnly } from '../utils/format';
import { logFeature } from '../utils/logging';
import { STATUS_COLORS, colors, ui } from '../theme';

const PHOTO_W = Dimensions.get('window').width - 40;

function Photos({ media }) {
  const photos = media.filter((m) => m.kind !== 'pov');
  if (!photos.length) return null;
  return (
    <ScrollView horizontal pagingEnabled showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -20 }}
      contentContainerStyle={{ paddingHorizontal: 20, gap: 10 }}>
      {photos.map((m) => (
        <View key={m.id} style={{ width: PHOTO_W, gap: 6 }}>
          <Image source={{ uri: m.url }} style={styles.photo} resizeMode="cover" accessibilityLabel={m.caption || m.kind_label} />
          <Text style={ui.small}>{m.kind_label}{m.caption ? ` · ${m.caption}` : ''}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

function Tip({ tip }) {
  const [open, setOpen] = useState(false);
  return (
    <View style={styles.tip}>
      <TouchableOpacity style={ui.between} onPress={() => setOpen(!open)} accessibilityRole="button">
        <Text style={[ui.strong, { flex: 1 }]}>{tip.name}</Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={colors.muted} />
      </TouchableOpacity>
      <Text style={ui.small}>{tip.what}</Text>
      {open && (
        <View style={{ gap: 8, marginTop: 4 }}>
          <Text style={[ui.small, { color: colors.text }]}>{tip.why}</Text>
          <Text style={ui.label}>Optional drills</Text>
          {tip.drills.map((d) => (
            <View key={d.name} style={{ gap: 2 }}>
              <Text style={ui.strong}>{d.name}</Text>
              <Text style={ui.small}>{d.how}</Text>
            </View>
          ))}
          <Text style={[ui.small, { fontStyle: 'italic' }]}>{tip.got_it_when}</Text>
        </View>
      )}
    </View>
  );
}

export default function FeatureScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [feature, setFeature] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(null);
  const [reporting, setReporting] = useState(false);
  const [reportNote, setReportNote] = useState('');

  const load = async () => {
    setError(null);
    try {
      setFeature(await fetchJson(`/api/features/${params.id}/`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  const log = async (outcome) => {
    setSaving(outcome);
    try {
      const result = await logFeature(feature.id, outcome, {}, logout);
      if (result.queued) {
        Alert.alert('Saved for later', "No signal right now. We'll send it when you're back in range.");
        return;
      }
      const entry = result.logs[0];
      await load();
      if (entry.first_clean) {
        navigation.navigate('ShareCard', { logId: entry.id, featureName: feature.name, points: result.points });
        announceAchievements(result.new_achievements);
      } else if (!announceAchievements(result.new_achievements)) {
        Alert.alert(outcomeLabel(outcome), result.points ? `${points(result.points)}. Logged.` : 'Logged. Every go counts.');
      }
      if (result.leveled_up) Alert.alert('Level up!', `Level ${result.level.level} · ${result.level.title}`);
    } catch (err) {
      Alert.alert("Couldn't log it", err.message);
    } finally {
      setSaving(null);
    }
  };

  const report = async () => {
    try {
      await sendJson(`/api/features/${feature.id}/report/`, 'POST', { note: reportNote.trim() }, logout);
      setReporting(false);
      setReportNote('');
      Alert.alert('Thanks', 'Our trail team will take a look.');
    } catch (err) {
      Alert.alert("Couldn't send it", err.message);
    }
  };

  if (!feature && error) return <ErrorState message={error} onRetry={load} />;
  if (!feature) return <Loading />;

  const pov = feature.media.find((m) => m.kind === 'pov');
  const measurements = measurementList(feature.measurements);

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll} keyboardShouldPersistTaps="handled">
      <Header caption={feature.trail_name} />
      <View style={[ui.row, { alignItems: 'flex-start' }]}>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={ui.title}>{feature.name}</Text>
          <Text style={ui.label}>{feature.type_label} · {gradeLabel(feature.grade)}</Text>
        </View>
        <GradeChip grade={feature.grade} />
      </View>

      {feature.notices.map((n) => (
        <View key={n} style={[ui.card, styles.notice]}>
          <Ionicons name="warning-outline" size={18} color={colors.warn} />
          <Text style={[ui.small, { flex: 1, color: colors.text }]}>{n}</Text>
        </View>
      ))}

      <Photos media={feature.media} />
      {pov && <FeatureVideo url={pov.url} />}

      {feature.has_ride_around && (
        <View style={[ui.card, styles.rideAround]}>
          <View style={ui.row}>
            <Ionicons name="git-compare-outline" size={20} color={colors.good} />
            <Text style={[ui.strong, { flex: 1 }]}>
              There's a ride-around{feature.ride_around_grade ? ` (grade ${feature.ride_around_grade})` : ''}
            </Text>
          </View>
          {feature.ride_around_note ? <Text style={ui.small}>{feature.ride_around_note}</Text> : null}
          <Text style={ui.small}>Use it any time you're not sure. That's what it's there for.</Text>
        </View>
      )}

      <View style={ui.card}>
        <View style={ui.between}>
          <Text style={ui.label}>How did it go?</Text>
          <StatusPill status={feature.my_status} cleans={feature.my_cleans} />
        </View>
        <OutcomeButtons onPick={log} disabled={Boolean(saving)} />
        {feature.my_status !== 'cleaned' && feature.first_clean_points > 0 && (
          <Text style={ui.small}>A first clean is worth {feature.first_clean_points} points.</Text>
        )}
      </View>

      {measurements.length > 0 && (
        <View style={[ui.card, { flexDirection: 'row', gap: 16 }]}>
          {measurements.map((m) => (
            <View key={m.label}>
              <Text style={ui.label}>{m.label}</Text>
              <Text style={[ui.number, { fontSize: 26 }]}>{m.value}</Text>
            </View>
          ))}
        </View>
      )}

      {feature.description ? <Text style={ui.body}>{feature.description}</Text> : null}
      {feature.how_to_ride ? (
        <View style={ui.card}>
          <Text style={ui.label}>How to ride it</Text>
          <Text style={ui.body}>{feature.how_to_ride}</Text>
        </View>
      ) : null}
      {feature.what_can_go_wrong ? (
        <View style={ui.card}>
          <Text style={ui.label}>What can go wrong</Text>
          <Text style={ui.body}>{feature.what_can_go_wrong}</Text>
        </View>
      ) : null}

      {feature.history.length > 0 && (
        <View style={ui.card}>
          <Text style={ui.label}>Your history</Text>
          {feature.history.map((h) => (
            <View key={h.id} style={ui.between}>
              <View style={[ui.row, { gap: 8, flex: 1 }]}>
                <View style={[styles.dot, { backgroundColor: STATUS_COLORS[h.outcome] }]} />
                <View style={{ flex: 1 }}>
                  <Text style={ui.body}>{outcomeLabel(h.outcome)}</Text>
                  {h.note ? <Text style={ui.small}>{h.note}</Text> : null}
                </View>
              </View>
              <Text style={ui.small}>{dateOnly(h.ridden_on)}{h.points ? ` · ${points(h.points)}` : ''}</Text>
            </View>
          ))}
        </View>
      )}

      {feature.stuck.length > 0 && (
        <View style={ui.card}>
          <Text style={ui.label}>Stuck?</Text>
          <Text style={ui.small}>Tips for the skills this feature uses. The drills are optional, for when you want them.</Text>
          {feature.stuck.map((tip) => <Tip key={tip.skill} tip={tip} />)}
        </View>
      )}

      {reporting ? (
        <View style={ui.card}>
          <Text style={ui.label}>What's changed?</Text>
          <TextInput style={[ui.input, { height: 80, paddingTop: 12 }]} multiline placeholder="Optional: lip washed out, tree down…"
            placeholderTextColor={colors.muted} value={reportNote} onChangeText={setReportNote} maxLength={300} />
          <Button title="Send to the trail team" onPress={report} />
          <Button title="Cancel" variant="outline" onPress={() => setReporting(false)} />
        </View>
      ) : (
        <Button title="Report a change" variant="outline" icon="flag-outline" onPress={() => setReporting(true)} />
      )}

      <SafetyNote text={feature.safety?.short} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  photo: { width: '100%', aspectRatio: 4 / 3, borderRadius: 14, backgroundColor: colors.card },
  notice: { flexDirection: 'row', alignItems: 'center', borderColor: colors.warn },
  rideAround: { borderColor: colors.good },
  tip: { gap: 4, paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
