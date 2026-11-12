// Trail team: one feature. Fill in the details, add photos, and move it through review: submit, certify (a second
// reviewer), flag changed or closed, mark verified, resolve rider reports. The POV clip is added from a computer
// in the admin.
import { useCallback, useState } from 'react';
import { Alert, Image, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { fetchJson, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, Chip, ErrorState, Header, Loading } from '../components/ui';
import { discardPhotos, keepPhoto, uploadPhoto } from '../utils/capture';
import { uuid } from '../utils/features';
import { FEATURE_TYPES, GRADES, PHOTO_SLOTS, measurementFor, parseMeasurement } from '../utils/team';
import { colors, fonts, ui } from '../theme';

const TEXT_FIELDS = [
  ['description', 'Description'],
  ['how_to_ride', 'How to ride it'],
  ['what_can_go_wrong', 'What can go wrong'],
];

const STATUS_TEXT = {
  draft: 'Draft: only the trail team sees it.',
  certified: 'Certified: live for riders.',
  changed: 'Changed: riders see a warning. Re-grade and certify it again.',
  closed: 'Closed: hidden from riders.',
};

export default function TeamFeatureScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [f, setF] = useState(null);
  const [edits, setEdits] = useState({});
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setError(null);
    try {
      setF(await fetchJson(`/api/team/features/${params.id}/`, { logout }));
      setEdits({});
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  const value = (key) => (key in edits ? edits[key] : f[key]);
  const edit = (key) => (v) => setEdits((e) => ({ ...e, [key]: v }));
  const dirty = Object.keys(edits).length > 0;

  const run = async (label, fn) => {
    setBusy(label);
    try {
      await fn();
      await load();
    } catch (err) {
      Alert.alert("Couldn't do that", err.message);
    } finally {
      setBusy(null);
    }
  };

  const save = () => run('save', async () => {
    const body = { ...edits };
    const m = measurementFor(value('type'));
    if (m && typeof body[m.field] === 'string') {
      const n = parseMeasurement(body[m.field]);
      if (n === undefined) throw new Error('The measurement should be a number.');
      body[m.field] = n;
    }
    await sendJson(`/api/team/features/${f.id}/`, 'PATCH', body, logout);
  });

  const action = (name, body) => run(name, () => sendJson(`/api/team/features/${f.id}/${name}/`, 'POST', body, logout));

  const addPhoto = (kind) => run('photo', async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) throw new Error('Turn on camera access for Next Line in Settings.');
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7, exif: false });
    if (shot.canceled) return;
    const photo = { kind, client_id: uuid() };
    photo.uri = keepPhoto(shot.assets[0].uri, photo.client_id);
    await uploadPhoto(f.id, photo, logout);
    discardPhotos([photo]);
  });

  const resolve = (report, status) => run('report', () => sendJson(`/api/team/reports/${report.id}/resolve/`, 'POST', { status }, logout));

  const remove = () => Alert.alert('Delete this draft?', 'Its photos are deleted too.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Delete', style: 'destructive', onPress: () => run('delete', async () => {
      await sendJson(`/api/team/features/${f.id}/`, 'DELETE', undefined, logout);
      navigation.goBack();
    }) },
  ]);

  if (!f && error) return <ErrorState message={error} onRetry={load} />;
  if (!f) return <Loading />;

  const locked = f.status === 'certified';  // grade and type are locked once certified
  const measurement = measurementFor(value('type'));

  return (
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={ui.scroll} keyboardShouldPersistTaps="handled">
        <Header caption={f.trail_name} />
        <TextInput style={[ui.title, styles.titleInput]} value={value('name')} onChangeText={edit('name')} maxLength={80} />
        <Text style={[ui.small, f.status === 'changed' && { color: colors.warn }]}>{STATUS_TEXT[f.status]}</Text>
        {f.stale && <Text style={[ui.small, { color: colors.warn }]}>Not verified in over a year.</Text>}

        <ScrollView horizontal contentContainerStyle={{ gap: 8 }} showsHorizontalScrollIndicator={false}>
          {f.media.map((m) => (
            m.kind === 'pov'
              ? <View key={m.id} style={[styles.photo, styles.pov]}><Text style={ui.small}>POV clip</Text></View>
              : <Image key={m.id} source={{ uri: m.thumbnail || m.url }} style={styles.photo} />
          ))}
          {PHOTO_SLOTS.map((slot) => (
            <TouchableOpacity key={slot.kind} style={[styles.photo, styles.addPhoto]} onPress={() => addPhoto(slot.kind)}
              disabled={busy === 'photo'}>
              <Text style={[ui.small, { textAlign: 'center' }]}>+ {slot.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <Text style={ui.small}>Add the POV clip from a computer: Admin → Features → this feature.</Text>

        <View style={ui.card}>
          <Text style={ui.label}>Type and grade{locked ? ' (locked: flag it as changed to regrade)' : ''}</Text>
          <View style={styles.chips}>
            {FEATURE_TYPES.map((t) => (
              <Chip key={t.key} label={t.label} selected={value('type') === t.key}
                onPress={locked ? undefined : () => edit('type')(t.key)} />
            ))}
          </View>
          <View style={styles.chips}>
            {GRADES.map((g) => (
              <TouchableOpacity key={g} style={[styles.grade, value('grade') === g && styles.gradeOn]} disabled={locked}
                onPress={() => edit('grade')(g)}>
                <Text style={[styles.gradeText, value('grade') === g && { color: colors.bg }]}>{g}</Text>
              </TouchableOpacity>
            ))}
          </View>
          {measurement && (
            <TextInput style={ui.input} placeholder={measurement.label} placeholderTextColor={colors.muted}
              keyboardType="decimal-pad" value={value(measurement.field) == null ? '' : String(value(measurement.field))}
              onChangeText={edit(measurement.field)} />
          )}
        </View>

        <View style={ui.card}>
          {TEXT_FIELDS.map(([key, label]) => (
            <View key={key} style={{ gap: 6 }}>
              <Text style={ui.label}>{label}</Text>
              <TextInput style={[ui.input, styles.multiline]} multiline value={value(key)} onChangeText={edit(key)}
                placeholderTextColor={colors.muted} placeholder="Optional" />
            </View>
          ))}
          <View style={ui.between}>
            <Text style={ui.body}>There's a ride-around</Text>
            <Switch value={Boolean(value('has_ride_around'))} onValueChange={edit('has_ride_around')}
              trackColor={{ true: colors.good, false: colors.border }} thumbColor={colors.text} />
          </View>
          {value('has_ride_around') && (
            <>
              <View style={styles.chips}>
                {GRADES.slice(0, 6).map((g) => (
                  <Chip key={g} label={`Grade ${g}`} selected={value('ride_around_grade') === g}
                    onPress={() => edit('ride_around_grade')(g)} />
                ))}
              </View>
              <TextInput style={ui.input} placeholder="Where it goes (e.g. left of the big rock)"
                placeholderTextColor={colors.muted} value={value('ride_around_note')} onChangeText={edit('ride_around_note')} />
            </>
          )}
          <Text style={ui.small}>Skill tags are set in the admin; until then the feature uses tips for its type.</Text>
          {dirty && <Button title="Save changes" onPress={save} loading={busy === 'save'} />}
        </View>

        {f.open_reports.length > 0 && (
          <View style={[ui.card, { borderColor: colors.warn }]}>
            <Text style={ui.label}>Rider reports</Text>
            {f.open_reports.map((r) => (
              <View key={r.id} style={{ gap: 6 }}>
                <Text style={ui.body}>{r.note || 'No note: a rider says it has changed.'}</Text>
                {r.photo && <Image source={{ uri: r.photo }} style={[styles.photo, { width: 160 }]} />}
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <Button title="Resolved" variant="secondary" style={{ flex: 1 }} onPress={() => resolve(r, 'resolved')} />
                  <Button title="No change" variant="outline" style={{ flex: 1 }} onPress={() => resolve(r, 'dismissed')} />
                </View>
              </View>
            ))}
          </View>
        )}

        <View style={ui.card}>
          <Text style={ui.label}>Review</Text>
          {['draft', 'changed'].includes(f.status) && !f.submitted_at && (
            <Button title="Submit for review" onPress={() => action('submit')} loading={busy === 'submit'} disabled={dirty} />
          )}
          {['draft', 'changed'].includes(f.status) && (
            <>
              <Button title="Certify (goes live)" onPress={() => action('certify')} loading={busy === 'certify'}
                disabled={!f.can_certify || dirty} />
              {!f.can_certify && f.certify_problems.map((p) => <Text key={p} style={ui.small}>• {p}</Text>)}
            </>
          )}
          {f.status === 'certified' && (
            <>
              <Button title="Mark verified: still as graded" variant="secondary" onPress={() => action('verify')}
                loading={busy === 'verify'} />
              <Button title="Flag as changed" variant="outline" onPress={() => action('flag', { status: 'changed' })}
                loading={busy === 'flag'} />
            </>
          )}
          {f.status !== 'closed' && f.status !== 'draft' && (
            <Button title="Close: hide from riders" variant="danger" onPress={() => action('flag', { status: 'closed' })} />
          )}
          {f.status === 'closed' && <Button title="Reopen as a draft" variant="secondary" onPress={() => action('reopen')} />}
          {f.status === 'draft' && <Button title="Delete draft" variant="danger" onPress={remove} />}
          {dirty && <Text style={ui.small}>Save your changes first.</Text>}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  titleInput: { paddingVertical: 0 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  photo: { width: 110, height: 110, borderRadius: 12, backgroundColor: colors.cardRaised },
  pov: { alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  addPhoto: {
    alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderStyle: 'dashed', borderColor: colors.borderDashed,
    padding: 8,
  },
  multiline: { height: 88, paddingTop: 12, textAlignVertical: 'top' },
  grade: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.border, alignItems: 'center',
    justifyContent: 'center',
  },
  gradeOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  gradeText: { fontFamily: fonts.display, fontSize: 20, color: colors.text },
});
