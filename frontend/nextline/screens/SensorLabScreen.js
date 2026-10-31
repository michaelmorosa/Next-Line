// Validation tool for the riskiest part of the app: whether jumps show up cleanly from a phone in a pocket.
// Logs every accelerometer sample (50 Hz) plus GPS to a CSV you can share to a computer and plot, and runs the same
// jump detector as recording so you can compare what it found with the jumps you actually hit.
import { useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { File, Paths } from 'expo-file-system';
import * as Location from 'expo-location';
import { Accelerometer } from 'expo-sensors';
import * as Sharing from 'expo-sharing';
import { createJumpDetector, magnitude } from '../recording/detectors';
import useRecorder from '../recording/useRecorder';
import { Button, Grid, Header, StatTile } from '../components/ui';
import { colors, ui } from '../theme';

const FLUSH_MS = 2000;

export default function SensorLabScreen() {
  const recorder = useRecorder();
  const [logging, setLogging] = useState(false);
  const [stats, setStats] = useState({ samples: 0, g: 1, minG: 1, maxG: 1, jumps: [], speed: null });
  const [file, setFile] = useState(null);
  const subs = useRef({});

  const stop = () => {
    const s = subs.current;
    s.accel?.remove();
    s.gps?.remove();
    clearInterval(s.flush);
    clearInterval(s.ui);
    s.flushNow?.();
    subs.current = {};
    setLogging(false);
  };

  useEffect(() => stop, []);

  const start = async () => {
    if (recorder.status === 'recording') {
      Alert.alert('Finish your ride first', 'The sensor lab and ride recording both use the motion sensors.');
      return;
    }
    const { status } = await Location.requestForegroundPermissionsAsync();
    const out = new File(Paths.document, `sensor-log-${new Date().toISOString().replace(/[:.]/g, '-')}.csv`);
    out.create();
    out.write('t_ms,x,y,z,g,lat,lng,alt,speed,gps_accuracy,jump_airtime_s\n');
    setFile(out);

    let buffer = [];
    let gps = { lat: '', lng: '', alt: '', speed: '', acc: '' };
    let speed = 0;
    const live = { samples: 0, g: 1, minG: 1, maxG: 1, jumps: [] };
    const detector = createJumpDetector();
    const flushNow = () => {
      if (!buffer.length) return;
      out.write(buffer.join(''), { append: true });
      buffer = [];
    };

    Accelerometer.setUpdateInterval(20);
    subs.current.accel = Accelerometer.addListener(({ x, y, z }) => {
      const t = Date.now();
      const g = magnitude(x, y, z);
      const jump = detector.push(t, g, speed >= 1.5);
      if (jump) live.jumps = [...live.jumps, jump.airtimeS];
      live.samples += 1;
      live.g = g;
      live.minG = Math.min(live.minG, g);
      live.maxG = Math.max(live.maxG, g);
      buffer.push(`${t},${x.toFixed(4)},${y.toFixed(4)},${z.toFixed(4)},${g.toFixed(4)},${gps.lat},${gps.lng},${gps.alt},${gps.speed},${gps.acc},${jump ? jump.airtimeS : ''}\n`);
    });
    if (status === 'granted') {
      subs.current.gps = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, timeInterval: 1000, distanceInterval: 0 },
        ({ coords }) => {
          speed = coords.speed ?? 0;
          gps = {
            lat: coords.latitude.toFixed(6), lng: coords.longitude.toFixed(6),
            alt: coords.altitude?.toFixed(1) ?? '', speed: coords.speed?.toFixed(2) ?? '', acc: coords.accuracy?.toFixed(0) ?? '',
          };
        },
      );
    }
    subs.current.flush = setInterval(flushNow, FLUSH_MS);
    subs.current.flushNow = flushNow;
    subs.current.ui = setInterval(() => setStats({ ...live, speed }), 250);
    setLogging(true);
  };

  const share = async () => {
    if (!file?.exists) return;
    if (!(await Sharing.isAvailableAsync())) {
      Alert.alert('Sharing unavailable', `The log is saved at ${file.uri}`);
      return;
    }
    await Sharing.shareAsync(file.uri, { mimeType: 'text/csv', dialogTitle: 'Sensor log' });
  };

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header caption="Validation" />
      <Text style={ui.title}>Sensor lab</Text>
      <Text style={ui.subtitle}>
        Start logging, pocket the phone, ride a line with jumps you can count, then share the CSV. Keep the screen on:
        this logger only runs with the app open.
      </Text>

      <Grid columns={3}>
        <StatTile label="Now" value={stats.g.toFixed(2)} sub="g" small />
        <StatTile label="Min" value={stats.minG.toFixed(2)} sub="g (air → 0)" small />
        <StatTile label="Max" value={stats.maxG.toFixed(1)} sub="g (impacts)" small />
      </Grid>
      <Grid>
        <StatTile label="Jumps found" value={stats.jumps.length}
          sub={stats.jumps.length ? stats.jumps.slice(-6).map((a) => `${a.toFixed(2)}s`).join(' · ') : 'none yet'} />
        <StatTile label="GPS speed" value={stats.speed == null ? '—' : `${(stats.speed * 3.6).toFixed(0)}`}
          sub="km/h · jumps need 5+" />
      </Grid>
      <Text style={ui.small}>{stats.samples.toLocaleString()} samples logged</Text>

      {logging
        ? <Button title="Stop logging" variant="outline" onPress={stop} />
        : <Button title={file ? 'Start a new log' : 'Start logging'} onPress={start} />}
      {file && !logging && <Button title="Share CSV" variant="secondary" icon="share-outline" onPress={share} />}

      <View style={ui.card}>
        <Text style={ui.label}>What good looks like</Text>
        <Text style={[ui.small, { color: colors.text }]}>
          At rest g sits near 1. On a jump it should drop below 0.4 for the airtime, then spike above 1.6 on landing.
          If pocket jumps don't dip clearly, tune the thresholds in recording/detectors.js before trusting jump counts.
        </Text>
      </View>
    </ScrollView>
  );
}
