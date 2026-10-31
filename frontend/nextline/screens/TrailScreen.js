import { useCallback, useState } from 'react';
import { Alert, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { fetchJson, sendJson } from '../api';
import { announceAchievements } from '../utils/achievements';
import { useAuth } from '../AuthContext';
import { Button, Chip, CircleButton, ErrorState, Header, Loading, OptionsSheet, ProgressBar } from '../components/ui';
import { climbRate, directionLabel, duration, feetDown, km, metres, shortDate } from '../utils/format';
import { DIFFICULTY, colors, fonts, ui } from '../theme';

const STATUS = {
  cleaned: { dot: colors.good, mark: '✓', tag: colors.good, label: 'Cleaned' },
  almost: { dot: colors.warn, mark: '!', tag: colors.warn, label: 'Almost' },
  locked: { dot: colors.dotMuted, mark: '', tag: colors.muted, label: 'Locked' },
};
const NEW_DAYS = 14;

function featureMeta(f) {
  if (!f.approved) return 'Waiting for approval · only you see it for now';
  if (f.note) return f.note;
  if (f.status === 'cleaned') {
    const first = f.first_cleaned_at ? ` · first ${shortDate(f.first_cleaned_at)}` : '';
    return `Cleaned ${f.clean_count} time${f.clean_count === 1 ? '' : 's'}${first}`;
  }
  if (f.riders_cleaned) return `${f.riders_cleaned} rider${f.riders_cleaned === 1 ? '' : 's'} cleaned it`;
  return 'Nobody has cleaned it yet';
}

function isNew(f) {
  return f.status === 'cleaned' && f.first_cleaned_at
    && Date.now() - new Date(f.first_cleaned_at).getTime() < NEW_DAYS * 86400000;
}

function EditTrail({ trail, onClose, onSaved }) {
  const { logout } = useAuth();
  const [name, setName] = useState(trail.name);
  const [difficulty, setDifficulty] = useState(trail.difficulty);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await sendJson(`/api/trails/${trail.id}/`, 'PATCH', { name: name.trim(), difficulty }, logout);
      onSaved();
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <View style={[ui.screen, { padding: 24, paddingTop: 70, gap: 14 }]}>
        <Text style={ui.title}>Edit trail</Text>
        <TextInput style={ui.input} value={name} onChangeText={setName} placeholder="Trail name" placeholderTextColor={colors.muted} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {Object.entries(DIFFICULTY).map(([key, d]) => (
            <Chip key={key} label={d.label} selected={difficulty === key} onPress={() => setDifficulty(key)} />
          ))}
        </View>
        <Text style={ui.small}>
          Your own rating counts as Blue at most toward rider level. Black and double-black count in full on shared
          trails.
        </Text>
        <Button title="Save" onPress={save} loading={saving} disabled={!name.trim()} />
        <Button title="Cancel" variant="outline" onPress={onClose} />
      </View>
    </Modal>
  );
}

export default function TrailScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [trail, setTrail] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = async () => {
    setError(null);
    try {
      setTrail(await fetchJson(`/api/trails/${params.id}/`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  const setStatus = async (feature, status) => {
    try {
      const updated = await sendJson(`/api/features/${feature.id}/progress/`, 'PUT', { status }, logout);
      setTrail((t) => ({ ...t, features: t.features.map((f) => (f.id === updated.id ? updated : f)) }));
      announceAchievements(updated.new_achievements);
    } catch (err) {
      Alert.alert("Couldn't update", err.message);
    }
  };

  const removeFeature = async (feature) => {
    try {
      await sendJson(`/api/features/${feature.id}/`, 'DELETE', undefined, logout);
      load();
    } catch (err) {
      Alert.alert("Couldn't remove", err.message);
    }
  };

  const featureOptions = (feature) => [
    { text: 'Cleaned it', onPress: () => setStatus(feature, 'cleaned') },
    { text: 'Almost', onPress: () => setStatus(feature, 'almost') },
    { text: 'Not yet', onPress: () => setStatus(feature, 'locked') },
    ...(feature.is_mine ? [{ text: 'Remove pin', destructive: true, onPress: () => removeFeature(feature) }] : []),
  ];

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!trail) return <Loading />;

  const difficulty = DIFFICULTY[trail.difficulty] || DIFFICULTY.unrated;
  const cleaned = trail.features.filter((f) => f.status === 'cleaned').length;
  const total = trail.features.length;

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header
        caption={`${directionLabel(trail.direction)} · ${difficulty.label} · ${km(trail.length_m)} km`}
        right={trail.is_mine ? <CircleButton icon="create-outline" label="Edit trail" onPress={() => setEditing(true)} /> : null}
      />
      <View>
        <Text style={ui.title}>{trail.name}</Text>
        <Text style={ui.subtitle}>
          {trail.laps} full lap{trail.laps === 1 ? '' : 's'} · {trail.clean_laps} clean
          {trail.best_s ? ` · best ${duration(trail.best_s)}` : ''}
          {` · ${metres(trail.drop_m)} m ${trail.direction === 'climb' ? 'gain' : 'drop'}`}
          {trail.is_mine ? ' · your trail, only you see it' : ' · shared trail'}
          {trail.is_auto && trail.name.startsWith('Unnamed') ? ' · tap ✎ to name it' : ''}
        </Text>
      </View>

      <View style={ui.cardRaised}>
        <View style={[ui.between, { alignItems: 'baseline' }]}>
          <Text style={ui.label}>Feature mastery</Text>
          <Text style={[ui.number, { fontSize: 32 }]}>{cleaned} / {total}</Text>
        </View>
        <ProgressBar fraction={total ? cleaned / total : 0} />
        <Text style={ui.small}>
          {total === 0 ? 'Pin the drops, jumps and rock gardens on this trail to track them.'
            : cleaned === total ? 'Trail mastered. Time to find a harder line.'
              : `${total - cleaned} to go before this trail is mastered`}
        </Text>
      </View>

      <View style={{ gap: 8 }}>
        {trail.features.map((f) => {
          const s = STATUS[f.status] || STATUS.locked;
          const fresh = isNew(f);
          return (
            <TouchableOpacity key={f.id} style={[ui.row, styles.feature]} onPress={() => setSelected(f)}>
              <View style={[styles.mark, { backgroundColor: s.dot }]}><Text style={styles.markText}>{s.mark}</Text></View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={ui.strong}>{f.name}</Text>
                <Text style={ui.small}>{featureMeta(f)}</Text>
              </View>
              <Text style={[styles.tag, { color: s.tag }]}>{fresh ? 'New' : s.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <Button title="+ Pin a new feature on this trail" variant="dashed"
        onPress={() => navigation.navigate('PinFeature', { trail })} />

      {trail.efforts.length > 0 && (
        <View style={ui.card}>
          <Text style={ui.label}>Your laps</Text>
          {[...trail.efforts].reverse().slice(0, 10).map((e) => (
            <TouchableOpacity key={e.id} style={ui.between} onPress={() => navigation.navigate('RideSummary', { id: e.ride })}>
              <Text style={ui.body}>
                {shortDate(e.started_at)}
                <Text style={[ui.small, e.touchdowns === 0 && { color: colors.good }]}>
                  {`  ${feetDown(e.touchdowns)}`}
                  {e.climb_rate != null ? ` · ${climbRate(e.climb_rate)}` : ''}
                </Text>
              </Text>
              <Text style={[ui.strong, e.elapsed_s === trail.best_s && { color: colors.good }]}>{duration(e.elapsed_s)}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      {selected && (
        <OptionsSheet title={selected.name} message="Mark your progress on this feature." options={featureOptions(selected)}
          onClose={() => setSelected(null)} />
      )}
      {editing && <EditTrail trail={trail} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  feature: {
    paddingVertical: 12, paddingHorizontal: 14, borderRadius: 14, backgroundColor: colors.card,
    borderWidth: 1, borderColor: colors.border, minHeight: 44,
  },
  mark: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  markText: { color: colors.bg, fontFamily: fonts.semibold, fontSize: 14 },
  tag: { fontFamily: fonts.medium, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.7 },
});
