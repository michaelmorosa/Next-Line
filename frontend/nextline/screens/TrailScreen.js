// A timed trail: laps and best times from recorded rides. Shared trails link to their graded features.
import { useCallback, useState } from 'react';
import { Alert, Modal, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import { fetchJson, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, Chip, CircleButton, ErrorState, Header, Loading, ProgressBar } from '../components/ui';
import { progressLine } from '../utils/features';
import { climbRate, directionLabel, duration, feetDown, km, metres, shortDate } from '../utils/format';
import { DIFFICULTY, colors, ui } from '../theme';

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
          Your own rating counts as Blue at most toward clean-climb points. Black and double-black count in full on
          shared trails.
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

  const load = async () => {
    setError(null);
    try {
      setTrail(await fetchJson(`/api/trails/${params.id}/`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!trail) return <Loading />;

  const difficulty = DIFFICULTY[trail.difficulty] || DIFFICULTY.unrated;
  const shared = !trail.is_mine;

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

      {shared && trail.feature_count > 0 && (
        <TouchableOpacity style={ui.cardRaised} onPress={() => navigation.navigate('TrailFeatures', { id: trail.id })}>
          <Text style={ui.label}>Graded features</Text>
          <Text style={ui.strong}>{progressLine(trail.cleaned_count, trail.feature_count)}</Text>
          <ProgressBar fraction={trail.cleaned_count / trail.feature_count} />
          <Text style={[ui.small, { color: colors.accent }]}>See the features ›</Text>
        </TouchableOpacity>
      )}

      {trail.efforts.length > 0 ? (
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
      ) : (
        <Text style={ui.small}>Record a ride down this trail and your laps and times show up here.</Text>
      )}
      {editing && <EditTrail trail={trail} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />}
    </ScrollView>
  );
}
