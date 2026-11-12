// Trail team: add a feature on site in under 3 minutes, with or without signal.
// GPS starts as the screen opens; take the photos, tap a type and grade, save. The draft and photos wait on the phone
// and upload when there's signal. Everything else (how to ride it, ride-around, tags) can be filled in later.
import { useEffect, useRef, useState } from 'react';
import { Alert, Image, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, Chip, Header } from '../components/ui';
import { captures, keepPhoto, uploadCaptures } from '../utils/capture';
import { uuid } from '../utils/features';
import {
  FEATURE_TYPES, GRADES, MAX_ACCURACY_M, PHOTO_SLOTS, betterFix, captureBody, captureProblems, measurementFor,
} from '../utils/team';
import { colors, fonts, ui } from '../theme';

const blank = () => ({ clientId: uuid(), photos: {}, type: null, grade: null, name: '', measurementText: '' });

export default function CaptureFeatureScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [form, setForm] = useState(blank);
  const [fix, setFix] = useState(null);
  const [gpsError, setGpsError] = useState(null);
  const [trails, setTrails] = useState(null);
  const [trailId, setTrailId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [waiting, setWaiting] = useState(0);
  const fetchedTrails = useRef(false);

  useEffect(() => {
    captures.count().then(setWaiting);
    let sub;
    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setGpsError('Location is off for Next Line. Turn it on in Settings to capture features.');
        return;
      }
      sub = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.BestForNavigation, timeInterval: 1000, distanceInterval: 0 },
        (p) => setFix((cur) => betterFix(cur, { ...p.coords, at: p.timestamp })),
      );
    })().catch((err) => setGpsError(err.message));
    return () => sub?.remove();
  }, []);

  // Nearby trails once there's a fix, if there's signal. Without it, the server picks the nearest on upload.
  useEffect(() => {
    if (!fix || fetchedTrails.current) return;
    fetchedTrails.current = true;
    fetchJson(`/api/team/trails/?lat=${fix.latitude}&lng=${fix.longitude}`, { logout, timeoutMs: 8000 })
      .then((list) => setTrails(list.slice(0, 6)))
      .catch(() => setTrails(null));
  }, [fix]);

  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const takePhoto = async (kind) => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Camera is off', 'Turn on camera access for Next Line in Settings.');
      return;
    }
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7, exif: false });
    if (shot.canceled) return;
    const clientId = uuid();
    try {
      const uri = keepPhoto(shot.assets[0].uri, clientId);
      setForm((f) => ({ ...f, photos: { ...f.photos, [kind]: { kind, uri, client_id: clientId } } }));
    } catch (err) {
      Alert.alert("Couldn't keep the photo", err.message);
    }
  };

  const problems = captureProblems({ position: fix, ...form });

  const save = async () => {
    if (problems.length) {
      Alert.alert('Not yet', problems.join('\n'));
      return;
    }
    setSaving(true);
    try {
      const body = captureBody({ ...form, position: fix, trailId });
      await captures.add({
        client_id: form.clientId, body, photos: Object.values(form.photos), created_at: new Date().toISOString(),
      });
      const result = await uploadCaptures(logout).catch(() => ({ uploaded: [], failed: [], left: 1 }));
      setWaiting(result.left);
      const mine = result.failed.find((f) => f.client_id === form.clientId);
      if (mine) Alert.alert('Saved, but the server turned it down', `${mine.message}\nFix or remove it from the review queue.`);
      else if (result.left) Alert.alert('Saved on your phone', "No signal right now. It'll upload from the review queue when you're back in range.");
      else Alert.alert('Draft saved', 'Uploaded. A second reviewer certifies it before riders see it.');
      setForm(blank());  // ready for the next feature down the trail
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };

  const measurement = measurementFor(form.type);
  const accuracyOk = fix && fix.accuracy != null && fix.accuracy <= MAX_ACCURACY_M;

  return (
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={ui.scroll} keyboardShouldPersistTaps="handled">
        <Header caption="Trail team"
          right={<Text style={[ui.small, { color: colors.accent }]} onPress={() => navigation.navigate('Guidelines')}>Guidelines</Text>} />
        <Text style={ui.title}>Add a feature</Text>
        {waiting > 0 && (
          <Text style={[ui.small, { color: colors.warn }]} onPress={() => navigation.navigate('TeamQueue')}>
            {waiting} capture{waiting === 1 ? '' : 's'} waiting to upload ›
          </Text>
        )}

        <View style={[ui.card, ui.row]}>
          <Ionicons name="locate" size={22} color={accuracyOk ? colors.good : colors.warn} />
          <View style={{ flex: 1 }}>
            <Text style={ui.strong}>
              {gpsError ? 'No GPS' : !fix ? 'Finding GPS…' : `±${Math.round(fix.accuracy ?? 0)} m`}
            </Text>
            <Text style={ui.small}>
              {gpsError || (accuracyOk ? 'Stand at the feature. The best fix is kept.' : 'Stand still at the feature for a moment.')}
            </Text>
          </View>
        </View>

        <View style={ui.card}>
          <Text style={ui.label}>Photos</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {PHOTO_SLOTS.map((slot) => {
              const photo = form.photos[slot.kind];
              return (
                <TouchableOpacity key={slot.kind} style={styles.photoSlot} onPress={() => takePhoto(slot.kind)}
                  accessibilityLabel={`Take ${slot.label} photo`}>
                  {photo ? <Image source={{ uri: photo.uri }} style={StyleSheet.absoluteFill} />
                    : <Ionicons name="camera" size={26} color={colors.muted} />}
                  <Text style={styles.photoLabel}>{slot.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={ui.card}>
          <Text style={ui.label}>Type</Text>
          <View style={styles.chips}>
            {FEATURE_TYPES.map((t) => (
              <Chip key={t.key} label={t.label} selected={form.type === t.key} onPress={() => set('type')(t.key)} />
            ))}
          </View>
          <Text style={ui.label}>Grade</Text>
          <View style={styles.chips}>
            {GRADES.map((g) => (
              <TouchableOpacity key={g} style={[styles.grade, form.grade === g && styles.gradeOn]} onPress={() => set('grade')(g)}
                accessibilityLabel={`Grade ${g}`} accessibilityState={{ selected: form.grade === g }}>
                <Text style={[styles.gradeText, form.grade === g && { color: colors.bg }]}>{g}</Text>
              </TouchableOpacity>
            ))}
          </View>
          {measurement && (
            <TextInput style={ui.input} placeholder={`${measurement.label}, optional`} placeholderTextColor={colors.muted}
              keyboardType="decimal-pad" value={form.measurementText} onChangeText={set('measurementText')} />
          )}
          <TextInput style={ui.input} placeholder="Name (optional, e.g. Root step)" placeholderTextColor={colors.muted}
            value={form.name} onChangeText={set('name')} maxLength={80} />
        </View>

        <View style={ui.card}>
          <Text style={ui.label}>Trail</Text>
          <View style={styles.chips}>
            <Chip label="Nearest" selected={!trailId} onPress={() => setTrailId(null)} />
            {(trails || []).map((t) => (
              <Chip key={t.id} label={`${t.name}${t.distance_m != null ? ` · ${t.distance_m} m` : ''}`}
                selected={trailId === t.id} onPress={() => setTrailId(t.id)} />
            ))}
          </View>
          {!trails && <Text style={ui.small}>No signal for the trail list. The nearest trail is used when it uploads.</Text>}
        </View>

        <Button title="Save draft" icon="save-outline" onPress={save} loading={saving} disabled={problems.length > 0} />
        {problems.length > 0 && <Text style={ui.small}>{problems.join(' ')}</Text>}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  photoSlot: {
    flex: 1, aspectRatio: 3 / 4, borderRadius: 12, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.borderDashed,
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden', backgroundColor: colors.cardRaised,
  },
  photoLabel: {
    position: 'absolute', bottom: 0, left: 0, right: 0, textAlign: 'center', paddingVertical: 4,
    fontFamily: fonts.medium, fontSize: 12, color: colors.text, backgroundColor: 'rgba(0,0,0,0.55)',
  },
  grade: {
    width: 48, height: 48, borderRadius: 24, borderWidth: 1, borderColor: colors.border, alignItems: 'center',
    justifyContent: 'center',
  },
  gradeOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  gradeText: { fontFamily: fonts.display, fontSize: 22, color: colors.text },
});
