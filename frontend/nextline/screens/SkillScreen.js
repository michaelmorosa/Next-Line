// One skill: what it is, drills to log, the mastery test, attempt videos side by side, history and nearby features.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { fetchJson, sendForm, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import AttemptVideo from '../components/AttemptVideo';
import { Button, ErrorState, Header, Loading, OptionsSheet } from '../components/ui';
import { dateOnly, localDay, metres, shortDate, xp } from '../utils/format';
import { uuidv4 } from '../utils/geo';
import { SKILL_STATE, colors, fonts, ui } from '../theme';

const MAX_SECONDS = 60;
const HISTORY_SHOWN = 8;
const TOAST_MS = 3500;

// What a log or upload earned, in a sentence.
export function earnedMessage(res, what) {
  if (!res.created) return `${what} was already saved.`;
  if (res.capped && !res.xp_gained) return `${what} saved. You've hit today's XP cap for this skill, but it still counts toward mastery.`;
  const extra = res.challenges_completed.length ? ` Challenge complete: ${res.challenges_completed.join(', ')}!` : '';
  return `${what} saved · ${xp(res.xp_gained)}${extra}`;
}

async function nearbyQuery() {
  try {
    const { status } = await Location.getForegroundPermissionsAsync();
    if (status !== 'granted') return '';
    const pos = await Location.getLastKnownPositionAsync();
    return pos ? `?lat=${pos.coords.latitude}&lng=${pos.coords.longitude}` : '';
  } catch {
    return '';
  }
}

function Requirement({ label, have, need }) {
  const met = have >= need;
  return (
    <View style={ui.row}>
      <Ionicons name={met ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={met ? colors.good : colors.muted} />
      <Text style={[ui.body, { flex: 1 }]}>{label}</Text>
      <Text style={[ui.strong, { color: met ? colors.good : colors.muted }]}>{Math.min(have, need)}/{need}</Text>
    </View>
  );
}

export default function SkillScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [skill, setSkill] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null); // drill index being logged, or 'attempt'
  const [toast, setToast] = useState(null);
  const [picking, setPicking] = useState(false);
  const [selected, setSelected] = useState([]); // attempt ids to play, up to 2 side by side
  const toastTimer = useRef(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSkill(await fetchJson(`/api/skills/${params.id}/${await nearbyQuery()}`, { logout }));
    } catch (err) {
      setError(err.message);
    }
  }, [params.id, logout]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const showToast = (message) => {
    clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = setTimeout(() => setToast(null), TOAST_MS);
  };

  if (error && !skill) return <ErrorState message={error} onRetry={load} />;
  if (!skill) return <Loading />;

  const state = SKILL_STATE[skill.state];
  const locked = skill.state === 'locked';
  const mastered = skill.state === 'mastered';
  const req = skill.requirements;

  const logSession = async (drillIndex) => {
    setBusy(drillIndex);
    try {
      const res = await sendJson(`/api/skills/${skill.id}/sessions/`, 'POST', {
        client_id: uuidv4(), practiced_on: localDay(), drill_index: drillIndex,
      }, logout);
      showToast(earnedMessage(res, skill.drills[drillIndex]?.name || 'Session'));
      await load();
    } catch (err) {
      Alert.alert("Couldn't log the session", err.message);
    } finally {
      setBusy(null);
    }
  };

  const addAttempt = async (fromCamera) => {
    const options = {
      mediaTypes: ['videos'],
      videoMaxDuration: MAX_SECONDS,
      // 720p keeps clips around 10–40 MB.
      videoQuality: ImagePicker.UIImagePickerControllerQualityType?.IFrame1280x720,
      videoExportPreset: ImagePicker.VideoExportPreset?.H264_1280x720,
    };
    try {
      const perm = fromCamera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('Permission needed', `Allow ${fromCamera ? 'camera' : 'photo library'} access in Settings to add attempt videos.`);
        return;
      }
      const picked = fromCamera
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
      if (picked.canceled) return;
      const asset = picked.assets[0];
      const seconds = asset.duration ? asset.duration / 1000 : null;
      if (seconds && seconds > MAX_SECONDS + 1) {
        Alert.alert('Too long', `Attempt videos can be up to ${MAX_SECONDS} seconds. Trim it and try again.`);
        return;
      }
      const isMov = (asset.mimeType || asset.uri).toLowerCase().includes('quicktime') || asset.uri.toLowerCase().endsWith('.mov');
      const form = new FormData();
      form.append('video', { uri: asset.uri, name: isMov ? 'attempt.mov' : 'attempt.mp4', type: isMov ? 'video/quicktime' : 'video/mp4' });
      form.append('client_id', uuidv4());
      form.append('practiced_on', localDay());
      if (seconds) form.append('duration_s', String(seconds));
      setBusy('attempt');
      const res = await sendForm(`/api/skills/${skill.id}/attempts/`, form, logout);
      showToast(earnedMessage(res, 'Attempt'));
      await load();
    } catch (err) {
      Alert.alert("Couldn't add the attempt", err.message);
    } finally {
      setBusy(null);
    }
  };

  const toggleAttempt = (id) => setSelected((cur) => (
    cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(-2)
  ));
  const playing = skill.attempt_videos.filter((a) => selected.includes(a.id));

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={ui.scroll}>
        <Header caption={`Tier ${skill.tier} skill`} />
        <View style={{ gap: 6 }}>
          <Text style={ui.title}>{skill.name}</Text>
          <View style={[ui.row, { flexWrap: 'wrap', gap: 8 }]}>
            <View style={[styles.tag, { borderColor: state.color }]}>
              <Ionicons name={state.icon} size={14} color={state.color} />
              <Text style={[styles.tagText, { color: state.color }]}>{state.label}</Text>
            </View>
            {skill.coach_verified && <View style={[styles.tag, { borderColor: colors.good }]}><Text style={[styles.tagText, { color: colors.good }]}>Coach verified</Text></View>}
            {skill.draft && <View style={styles.tag}><Text style={styles.tagText}>Draft</Text></View>}
            {skill.xp > 0 && <Text style={ui.small}>{skill.xp.toLocaleString()} XP earned here</Text>}
          </View>
        </View>

        {toast && <View style={styles.toast}><Text style={[ui.strong, { color: colors.bg }]}>{toast}</Text></View>}

        <Text style={ui.body}>{skill.description}</Text>
        <View style={ui.card}>
          <Text style={ui.label}>Why it matters</Text>
          <Text style={ui.body}>{skill.why}</Text>
        </View>

        {locked && (
          <View style={[ui.card, { borderColor: colors.borderDashed }]}>
            <Text style={ui.label}>Locked</Text>
            <Text style={ui.body}>Master these first:</Text>
            {skill.prerequisites.map((id) => (
              <TouchableOpacity key={id} style={ui.between} onPress={() => navigation.push('Skill', { id })}>
                <Text style={[ui.strong, { color: colors.accent }]}>{skill.prerequisite_names[id]}</Text>
                <Ionicons name="chevron-forward" size={16} color={colors.muted} />
              </TouchableOpacity>
            ))}
          </View>
        )}

        <Text style={ui.label}>Drills</Text>
        {skill.drills.map((drill, i) => (
          <View key={drill.name} style={ui.card}>
            <Text style={ui.strong}>{drill.name}</Text>
            <Text style={ui.body}>{drill.how}</Text>
            {!locked && (
              <Button title="Log session" variant="secondary" icon="add" loading={busy === i}
                disabled={busy !== null} onPress={() => logSession(i)} />
            )}
          </View>
        ))}

        <View style={[ui.cardRaised, { borderWidth: 1, borderColor: mastered ? colors.accent : colors.border }]}>
          <Text style={ui.label}>Mastery test</Text>
          <Text style={[ui.body, { fontFamily: fonts.medium }]}>{skill.mastery_test}</Text>
          {mastered ? (
            <Text style={[ui.strong, { color: colors.accent }]}>Mastered {shortDate(skill.mastered_at)}</Text>
          ) : !locked && (
            <>
              <Requirement label="Practice sessions" have={skill.sessions} need={req.min_sessions} />
              <Requirement label="Days practised" have={skill.practice_days} need={req.min_practice_days} />
              <Requirement label="Attempt videos" have={skill.attempts} need={req.min_videos} />
              <Button
                title={skill.eligible ? 'I passed the test' : 'Keep practising'}
                disabled={!skill.eligible}
                onPress={() => navigation.navigate('Mastery', { id: skill.id })}
              />
            </>
          )}
        </View>

        <View style={ui.between}>
          <Text style={ui.label}>Attempts</Text>
          {!locked && <Text style={[ui.small, { color: colors.accent }]} onPress={() => setPicking(true)}>+ Add attempt</Text>}
        </View>
        {skill.attempt_videos.length === 0 ? (
          <View style={ui.card}>
            <Text style={ui.small}>Film a try (up to {MAX_SECONDS} s). Compare them side by side as you get better.</Text>
            {!locked && <Button title="Add attempt video" variant="dashed" icon="videocam" loading={busy === 'attempt'}
              disabled={busy !== null} onPress={() => setPicking(true)} />}
          </View>
        ) : (
          <>
            {playing.length > 0 && (
              <View style={{ flexDirection: 'row', gap: 10 }}>
                {playing.map((a) => <AttemptVideo key={a.id} url={a.video_url} style={{ flex: 1 }} />)}
              </View>
            )}
            <Text style={ui.small}>Tap one to play it, or two to compare side by side.</Text>
            <View style={styles.attemptGrid}>
              {skill.attempt_videos.map((a) => {
                const on = selected.includes(a.id);
                return (
                  <TouchableOpacity key={a.id} style={[styles.attempt, on && { borderColor: colors.accent }]}
                    onPress={() => toggleAttempt(a.id)}>
                    <Ionicons name={on ? 'pause-circle' : 'play-circle'} size={26} color={on ? colors.accent : colors.text} />
                    <Text style={ui.strong}>{dateOnly(a.practiced_on)}</Text>
                    {a.duration_s ? <Text style={ui.small}>{Math.round(a.duration_s)} s</Text> : null}
                  </TouchableOpacity>
                );
              })}
            </View>
            {busy === 'attempt' && <Text style={ui.small}>Uploading…</Text>}
          </>
        )}

        {skill.history.length > 0 && (
          <>
            <Text style={ui.label}>Practice history</Text>
            <View style={ui.card}>
              {skill.history.slice(0, HISTORY_SHOWN).map((s) => (
                <View key={s.id} style={ui.between}>
                  <Text style={ui.body}>{s.drill || 'Practice'}</Text>
                  <Text style={ui.small}>{dateOnly(s.practiced_on)}</Text>
                </View>
              ))}
              {skill.sessions > HISTORY_SHOWN && <Text style={ui.small}>{skill.sessions} sessions in all</Text>}
            </View>
          </>
        )}

        {skill.nearby_features.length > 0 && (
          <>
            <Text style={ui.label}>Practise it on the trail</Text>
            {skill.nearby_features.map((f) => (
              <TouchableOpacity key={f.id} style={[ui.card, ui.between]} onPress={() => navigation.navigate('Trail', { id: f.trail })}>
                <View style={{ flex: 1 }}>
                  <Text style={ui.strong}>{f.name}</Text>
                  <Text style={ui.small}>{f.trail_name} · {metres(f.distance_m)} away{f.status === 'cleaned' ? ' · cleaned' : ''}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </TouchableOpacity>
            ))}
          </>
        )}

        {skill.unlocks.length > 0 && (
          <Text style={ui.small}>Unlocks: {skill.unlocks.map((u) => u.name).join(', ')}</Text>
        )}
      </ScrollView>

      {picking && (
        <OptionsSheet
          title="Add attempt video"
          message={`Up to ${MAX_SECONDS} seconds. Only you can see it.`}
          options={[
            { text: 'Record now', onPress: () => addAttempt(true) },
            { text: 'Choose from library', onPress: () => addAttempt(false) },
          ]}
          onClose={() => setPicking(false)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  tag: {
    flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderColor: colors.border, borderRadius: 10,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  tagText: { fontFamily: fonts.medium, fontSize: 12, color: colors.muted },
  toast: { backgroundColor: colors.accent, borderRadius: 12, padding: 12 },
  attemptGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  attempt: {
    width: '31%', minHeight: 88, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card,
    alignItems: 'center', justifyContent: 'center', gap: 2, padding: 8,
  },
});
