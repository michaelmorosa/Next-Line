// After a first clean: the share card, sized for Stories and TikTok or an Instagram post, and the share sheet.
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { downloadPrivate } from '../api';
import { useAuth } from '../AuthContext';
import { Button, Chip, Header } from '../components/ui';
import { points } from '../utils/features';
import { colors, ui } from '../theme';

const SIZES = [
  { key: 'story', label: 'Story / TikTok', ratio: 1080 / 1920 },
  { key: 'feed', label: 'Post', ratio: 1080 / 1350 },
];

export default function ShareCardScreen() {
  const navigation = useNavigation();
  const { params } = useRoute();
  const { logout } = useAuth();
  const [size, setSize] = useState('story');
  const [cards, setCards] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    if (cards[size]) return;
    setError(null);
    const file = new File(Paths.cache, `share-${params.logId}-${size}.jpg`);
    downloadPrivate(`/api/logs/${params.logId}/share-card/?size=${size}`, file, logout)
      .then((saved) => setCards((c) => ({ ...c, [size]: `${saved.uri}?v=${Date.now()}` })))
      .catch((err) => setError(err.message));
  }, [size]);

  const share = async () => {
    try {
      if (!(await Sharing.isAvailableAsync())) {
        Alert.alert("Can't share from here", 'Sharing is not available on this device.');
        return;
      }
      await Sharing.shareAsync(cards[size].split('?')[0], { mimeType: 'image/jpeg', UTI: 'public.jpeg', dialogTitle: 'Share your clean' });
    } catch (err) {
      Alert.alert("Couldn't share", err.message);
    }
  };

  const current = SIZES.find((s) => s.key === size);
  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header caption="First clean" />
      <Text style={ui.title}>{params.featureName}</Text>
      {params.points ? <Text style={[ui.strong, { color: colors.good }]}>{points(params.points)}</Text> : null}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {SIZES.map((s) => <Chip key={s.key} label={s.label} selected={size === s.key} onPress={() => setSize(s.key)} />)}
      </View>
      <View style={[styles.frame, { aspectRatio: current.ratio }]}>
        {cards[size] ? <Image source={{ uri: cards[size] }} style={StyleSheet.absoluteFill} resizeMode="contain" />
          : error ? <Text style={[ui.small, { padding: 16, textAlign: 'center' }]}>{error}</Text>
            : <ActivityIndicator color={colors.accent} />}
      </View>
      <Button title="Share" icon="share-outline" onPress={share} disabled={!cards[size]} />
      <Button title="Done" variant="outline" onPress={() => navigation.goBack()} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  frame: {
    width: '100%', borderRadius: 14, overflow: 'hidden', backgroundColor: colors.card, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1, borderColor: colors.border,
  },
});
