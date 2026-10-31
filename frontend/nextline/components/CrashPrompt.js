// "You OK?" after crash detection fires. If the rider doesn't answer before the countdown ends, their emergency
// contact is texted with the last known location.
import { useEffect, useRef, useState } from 'react';
import { Modal, StyleSheet, Text, Vibration, View } from 'react-native';
import { sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { dismissCrash } from '../recording/recorder';
import useRecorder from '../recording/useRecorder';
import { Button } from './ui';
import { colors, fonts, ui } from '../theme';

const COUNTDOWN_S = 60;

const RESULT_TEXT = {
  sent: (name) => `${name || 'Your contact'} has been texted your location.`,
  not_configured: () => "Couldn't text your contact: texting isn't set up on the server yet.",
  no_contact: () => 'No alert sent: add an emergency contact in Settings.',
  failed: () => "The text didn't go through. Call someone if you need help.",
};

export default function CrashPrompt() {
  const { crash } = useRecorder();
  const { user, logout } = useAuth();
  const [left, setLeft] = useState(COUNTDOWN_S);
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const sentFor = useRef(null);

  const sendAlert = async () => {
    if (!crash || sentFor.current === crash.at) return;
    sentFor.current = crash.at;
    Vibration.cancel();
    setSending(true);
    try {
      const res = await sendJson('/api/crash-alerts/', 'POST', { lat: crash.lat, lng: crash.lng }, logout);
      setResult(RESULT_TEXT[res.status]?.(user?.crash_contact_name) || RESULT_TEXT.failed());
    } catch {
      setResult("No signal to send the alert. Call someone if you need help.");
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    if (!crash) return undefined;
    setLeft(COUNTDOWN_S);
    setResult(null);
    Vibration.vibrate([0, 800, 400], true);
    const timer = setInterval(() => {
      const remaining = COUNTDOWN_S - Math.floor((Date.now() - crash.at) / 1000);
      setLeft(Math.max(0, remaining));
      if (remaining <= 0) {
        clearInterval(timer);
        sendAlert();
      }
    }, 500);
    return () => {
      clearInterval(timer);
      Vibration.cancel();
    };
  }, [crash?.at]);

  const close = () => {
    Vibration.cancel();
    dismissCrash();
  };

  return (
    <Modal visible={Boolean(crash)} animationType="fade" transparent={false} onRequestClose={close}>
      <View style={styles.screen}>
        <Text style={ui.label}>Possible crash detected</Text>
        <Text style={styles.big}>You OK?</Text>
        {result ? (
          <>
            <Text style={ui.body}>{result}</Text>
            <View style={{ flex: 1 }} />
            <Button title="Close" onPress={close} />
          </>
        ) : (
          <>
            <Text style={ui.body}>
              {user?.crash_contact_phone
                ? `If you don't answer, we'll text ${user.crash_contact_name || 'your emergency contact'} your location in`
                : 'No emergency contact is set, so no one will be alerted. Add one in Settings.'}
            </Text>
            {user?.crash_contact_phone ? <Text style={styles.count}>{left}</Text> : <View style={{ flex: 1 }} />}
            <Button title="I'm OK" onPress={close} style={styles.ok} />
            {user?.crash_contact_phone ? (
              <Button title="Send alert now" variant="danger" onPress={sendAlert} loading={sending} />
            ) : null}
          </>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, padding: 28, paddingTop: 90, gap: 18 },
  big: { fontFamily: fonts.display, fontSize: 72, color: colors.text, textTransform: 'uppercase' },
  count: { fontFamily: fonts.display, fontSize: 120, color: colors.accent, textAlign: 'center', flex: 1, textAlignVertical: 'center' },
  ok: { height: 72 },
});
