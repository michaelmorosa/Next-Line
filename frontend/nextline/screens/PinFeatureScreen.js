import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { sendJson } from '../api';
import { useAuth } from '../AuthContext';
import RideMap from '../components/RideMap';
import { Button, Chip, Header } from '../components/ui';
import { colors, ui } from '../theme';

const KINDS = [
  ['drop', 'Drop'], ['jump', 'Jump'], ['gap', 'Gap'], ['rock_garden', 'Rock garden'],
  ['roots', 'Roots'], ['berm', 'Berm'], ['technical', 'Technical'], ['other', 'Other'],
];

export default function PinFeatureScreen() {
  const navigation = useNavigation();
  const { params: { trail } } = useRoute();
  const { logout } = useAuth();
  const [pin, setPin] = useState(null);
  const [name, setName] = useState('');
  const [kind, setKind] = useState('drop');
  const [saving, setSaving] = useState(false);
  const path = trail.path?.length ? trail.path : [[trail.start_lat, trail.start_lng], [trail.end_lat, trail.end_lng]];

  const save = async () => {
    setSaving(true);
    try {
      const pinned = await sendJson(`/api/trails/${trail.id}/features/`, 'POST', {
        name: name.trim(), kind, lat: pin.latitude, lng: pin.longitude,
      }, logout);
      if (!pinned.approved) {
        Alert.alert(
          'Pinned',
          "You can track it now. Other riders will see it once it's approved, and it starts counting toward your "
          + 'rider level then.',
        );
      }
      navigation.goBack();
    } catch (err) {
      Alert.alert("Couldn't pin it", err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={ui.scroll} keyboardShouldPersistTaps="handled">
        <Header caption={trail.name} />
        <Text style={ui.title}>Pin a feature</Text>
        <Text style={ui.subtitle}>Tap the map where the feature is, on the orange line.</Text>
        <RideMap path={path} features={trail.features} pin={pin} onPress={setPin} height={300} />
        <TextInput
          style={ui.input}
          value={name}
          onChangeText={setName}
          placeholder="Name it, e.g. 3 ft drop"
          placeholderTextColor={colors.muted}
          maxLength={80}
        />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {KINDS.map(([key, label]) => <Chip key={key} label={label} selected={kind === key} onPress={() => setKind(key)} />)}
        </View>
        <Button title={pin ? 'Pin feature' : 'Tap the map first'} onPress={save} loading={saving} disabled={!pin || !name.trim()} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
