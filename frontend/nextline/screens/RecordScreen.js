import { useEffect, useState } from 'react';
import { Alert, Linking, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../AuthContext';
import * as recorder from '../recording/recorder';
import useRecorder from '../recording/useRecorder';
import { uploadRide } from '../recording/uploads';
import { Button, Grid, StatTile } from '../components/ui';
import { duration, km } from '../utils/format';
import { colors, fonts, ui } from '../theme';

function gpsLabel(rec) {
  if (!rec.lastFixAt) return 'Finding GPS…';
  if (Date.now() - rec.lastFixAt > 15000) return 'GPS lost · still recording';
  if (rec.gpsAccuracy != null && rec.gpsAccuracy > 20) return 'GPS weak · Offline OK';
  return 'GPS strong · Offline OK';
}

// Re-render every second while recording, so the clocks tick.
function useTick(active) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [active]);
}

// Ride time since Start, less manual pauses. Ticks whatever GPS is doing.
function rideSeconds(rec) {
  if (!rec.startedAt) return 0;
  const now = rec.pausedAt || Date.now();
  return Math.max(0, (now - rec.startedAt - rec.pausedMs) / 1000);
}

// Moving time, ticking smoothly between GPS points while the rider is moving.
function movingSeconds(rec) {
  if (rec.status !== 'recording' || rec.autoPaused || !rec.lastFixAt) return rec.movingS;
  return rec.movingS + Math.min(2, (Date.now() - rec.lastFixAt) / 1000);
}

// Development builds only: whether GPS is actually arriving.
function Diagnostics({ rec }) {
  if (!__DEV__) return null;
  const age = rec.lastFixAt ? `${Math.round((Date.now() - rec.lastFixAt) / 1000)}s ago` : 'none yet';
  const accuracy = rec.gpsAccuracy == null ? '?' : Math.round(rec.gpsAccuracy);
  return (
    <Text style={[ui.small, { fontSize: 11, textAlign: 'center' }]}>
      {`dev · ${rec.points.length} GPS points · last fix ${age} · ±${accuracy} m · ${rec.speed.toFixed(1)} m/s`
        + ` · ${rec.background ? 'background' : 'foreground'} GPS${recorder.IN_EXPO_GO ? ' · Expo Go' : ''}`}
    </Text>
  );
}

function DetectionRow({ label, value, onChange }) {
  return (
    <View style={ui.between}>
      <Text style={ui.body}>{label}</Text>
      {onChange
        ? <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.good, false: colors.border }} thumbColor={colors.text} />
        : <Text style={[ui.body, { color: colors.good }]}>On</Text>}
    </View>
  );
}

export default function RecordScreen() {
  const navigation = useNavigation();
  const { user, logout } = useAuth();
  const rec = useRecorder();
  useTick(rec.status === 'recording');
  const [settings, setSettings] = useState(recorder.DEFAULT_SETTINGS);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    recorder.loadSettings().then(setSettings);
  }, []);

  const toggle = (key) => (value) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    recorder.saveSettings(next);
  };

  const start = async () => {
    setBusy(true);
    try {
      await recorder.start();
      const { background } = recorder.getState();
      if (recorder.IN_EXPO_GO) {
        Alert.alert(
          'Keep the app open',
          "Expo Go can't record with the screen off. Keep Next Line open with the screen on while testing. "
          + 'Pocket recording needs a development build.',
        );
      } else if (!background) {
        Alert.alert(
          'Keep the app open',
          'Background location is off, so recording stops if you lock the phone. Allow location "Always" in '
          + 'Settings for pocket recording.',
          [{ text: 'OK' }, { text: 'Open Settings', onPress: () => Linking.openSettings() }],
        );
      }
    } catch (err) {
      Alert.alert('Can\'t record', err.message, err.canAskAgain === false
        ? [{ text: 'Cancel', style: 'cancel' }, { text: 'Open Settings', onPress: () => Linking.openSettings() }]
        : undefined);
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    const ride = await recorder.finish();
    try {
      const saved = await uploadRide(ride, logout);
      navigation.navigate('RideSummary', { id: saved.id, newAchievements: saved.new_achievements });
    } catch {
      Alert.alert('Ride saved on your phone', "It'll upload when you have signal. Pull down on Rides to retry.");
      navigation.navigate('Rides');
    } finally {
      setBusy(false);
    }
  };

  const confirmFinish = () => {
    if (rec.points.length < 2) {
      Alert.alert('No GPS track yet', 'Nothing was recorded. Discard this ride?', [
        { text: 'Keep recording', style: 'cancel' },
        { text: 'Discard', style: 'destructive', onPress: () => recorder.discard() },
      ]);
      return;
    }
    Alert.alert('Finish ride?', undefined, [
      { text: 'Keep recording', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: () => recorder.discard() },
      { text: 'Finish', onPress: finish },
    ]);
  };

  const contactName = user?.crash_contact_name || (user?.crash_contact_phone ? 'your contact' : null);
  const active = rec.status === 'recording' || rec.status === 'paused';

  if (rec.status === 'interrupted') {
    return (
      <View style={[ui.screen, styles.pad, { justifyContent: 'center', gap: 14 }]}>
        <Text style={ui.title}>Ride interrupted</Text>
        <Text style={ui.subtitle}>
          The app closed while recording. {km(rec.distanceM)} km and {rec.jumps.length} jumps were saved.
        </Text>
        <Button title="Keep recording" onPress={() => recorder.resumeInterrupted().catch((e) => Alert.alert('Can\'t record', e.message))} />
        <Button title="Finish and save" variant="secondary" onPress={finish} loading={busy} />
        <Button title="Discard" variant="danger" onPress={() => recorder.discard()} />
      </View>
    );
  }

  return (
    <ScrollView style={ui.screen} contentContainerStyle={[styles.pad, { gap: 18, flexGrow: 1 }]}>
      <View style={ui.between}>
        <View style={ui.row}>
          <View style={[styles.dot, { backgroundColor: active ? colors.accent : colors.dotMuted }]} />
          <Text style={ui.label}>
            {rec.status === 'paused' ? 'Paused' : active ? (rec.autoPaused ? 'Auto-paused' : 'Recording') : 'Ready'}
          </Text>
        </View>
        <Text style={ui.small}>{active ? gpsLabel(rec) : 'Works offline'}</Text>
      </View>

      <View style={{ alignItems: 'center', paddingTop: 16 }}>
        <Text style={styles.timer}>{duration(active ? rideSeconds(rec) : 0)}</Text>
        <Text style={[ui.subtitle, { fontSize: 15 }]}>
          {!active ? 'One tap, then pocket it'
            : `Moving ${duration(movingSeconds(rec))}${rec.autoPaused ? ' · stopped' : ''}`}
        </Text>
        {active && (
          <Text style={ui.small}>
            {recorder.IN_EXPO_GO ? 'Expo Go: keep the app open and the screen on' : 'Phone can go in your pocket or pack'}
          </Text>
        )}
      </View>
      {active && <Diagnostics rec={rec} />}

      <Grid>
        <StatTile value={km(rec.distanceM)} sub="km" center small />
        <StatTile value={rec.jumps.length} sub="jumps" center small />
        <StatTile value={Math.round(rec.climbM)} sub="m up" center small />
        <StatTile value={Math.round(rec.descentM)} sub="m down" center small />
      </Grid>

      <View style={ui.card}>
        <Text style={ui.label}>Auto-detecting</Text>
        <DetectionRow label="Climb / descent split" value />
        <DetectionRow label="Jumps & airtime" value={settings.detectJumps} onChange={toggle('detectJumps')} />
        <DetectionRow label="Repeat segments" value />
        <DetectionRow
          label={contactName ? `Crash alert to ${contactName}` : 'Crash check (no contact set)'}
          value={settings.detectCrashes}
          onChange={toggle('detectCrashes')}
        />
      </View>

      <View style={[ui.cardRaised, { flexDirection: 'row', gap: 12 }]}>
        <Ionicons name="phone-portrait-outline" size={22} color={colors.warn} />
        <Text style={[ui.body, { flex: 1, fontSize: 14 }]}>
          <Text style={{ fontFamily: fonts.semibold }}>Precision mode coming soon. </Text>
          <Text style={{ color: colors.muted }}>A watch or bar mount will unlock braking and fine-grained flow scores.</Text>
        </Text>
      </View>

      <View style={{ flex: 1 }} />
      {active ? (
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <Button
            title={rec.status === 'paused' ? 'Resume' : 'Pause'}
            variant="outline"
            onPress={rec.status === 'paused' ? recorder.resume : recorder.pause}
            style={styles.big}
          />
          <Button title="Finish ride" onPress={confirmFinish} loading={busy} style={styles.big} />
        </View>
      ) : (
        <Button title="Start ride" icon="radio-button-on" onPress={start} loading={busy} style={{ height: 64 }} />
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  pad: { padding: 20 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  timer: { fontFamily: fonts.display, fontSize: 84, lineHeight: 88, color: colors.text },
  big: { flex: 1, height: 60 },
});
