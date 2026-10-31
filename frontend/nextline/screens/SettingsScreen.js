import { useEffect, useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, Header } from '../components/ui';
import { colors, ui } from '../theme';

export default function SettingsScreen() {
  const navigation = useNavigation();
  const { user, setUser, refreshUser, logout } = useAuth();
  const [form, setForm] = useState({ crash_contact_name: '', crash_contact_phone: '', crash_alerts_enabled: true });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) refreshUser();
  }, []);

  useEffect(() => {
    if (user) {
      setForm({
        crash_contact_name: user.crash_contact_name,
        crash_contact_phone: user.crash_contact_phone,
        crash_alerts_enabled: user.crash_alerts_enabled,
      });
    }
  }, [user]);

  const save = async () => {
    setSaving(true);
    try {
      setUser(await sendJson('/api/user/me/', 'PATCH', form, logout));
      Alert.alert('Saved');
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };

  const deleteAccount = () => Alert.alert(
    'Delete your account?',
    'Every ride, trail and feature you have will be deleted. This cannot be undone.',
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive', onPress: async () => {
          try {
            await sendJson('/api/user/delete-account/', 'DELETE', undefined, logout);
            await logout();
          } catch (err) {
            Alert.alert("Couldn't delete", err.message);
          }
        },
      },
    ],
  );

  return (
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={ui.scroll} keyboardShouldPersistTaps="handled">
        <Header caption={user ? user.username : 'Settings'} />
        <Text style={ui.title}>Settings</Text>

        <View style={ui.card}>
          <Text style={ui.label}>Crash alert contact</Text>
          <Text style={ui.small}>
            If crash detection fires and you don't answer "You OK?" within a minute, we text this person your location.
          </Text>
          <TextInput style={ui.input} placeholder="Name" placeholderTextColor={colors.muted} value={form.crash_contact_name}
            onChangeText={(v) => setForm((f) => ({ ...f, crash_contact_name: v }))} />
          <TextInput style={ui.input} placeholder="Phone, with country code (+1 …)" placeholderTextColor={colors.muted}
            keyboardType="phone-pad" value={form.crash_contact_phone}
            onChangeText={(v) => setForm((f) => ({ ...f, crash_contact_phone: v }))} />
          <View style={ui.between}>
            <Text style={ui.body}>Send crash alerts</Text>
            <Switch value={form.crash_alerts_enabled} onValueChange={(v) => setForm((f) => ({ ...f, crash_alerts_enabled: v }))}
              trackColor={{ true: colors.good, false: colors.border }} thumbColor={colors.text} />
          </View>
          <Button title="Save" onPress={save} loading={saving} />
        </View>

        <View style={ui.card}>
          <Text style={ui.label}>Sensor lab</Text>
          <Text style={ui.small}>
            Log raw accelerometer and GPS data on a ride to check how well jumps show up with the phone in your pocket.
          </Text>
          <Button title="Open sensor lab" variant="secondary" onPress={() => navigation.navigate('SensorLab')} />
        </View>

        <Button title="Log out" variant="outline" onPress={logout} />
        <Button title="Delete account" variant="danger" onPress={deleteAccount} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
