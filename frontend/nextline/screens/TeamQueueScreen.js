// Trail team: captures waiting to upload, then everything needing a look: drafts awaiting a second reviewer,
// drafts still being filled in, changed features, rider reports, and features not verified in a year.
import { useCallback, useState } from 'react';
import { Alert, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import FeatureRow from '../components/FeatureRow';
import { Button, ErrorState, Header, Loading } from '../components/ui';
import { captureApi, captures, uploadCaptures } from '../utils/capture';
import { colors, ui } from '../theme';

const SECTIONS = [
  { key: 'awaiting_review', title: 'Waiting for a second reviewer', empty: 'Nothing waiting.' },
  { key: 'reported', title: 'Rider reports', empty: 'No open reports.' },
  { key: 'changed', title: 'Changed: needs re-grading', empty: 'None.' },
  { key: 'drafts', title: 'Drafts being filled in', empty: 'No drafts.' },
  { key: 'stale', title: 'Not verified in a year', empty: 'All checked recently.' },
];

// Team rows as FeatureRow expects them.
const row = (f) => ({
  ...f, type_label: f.type.replace('_', ' ').replace(/^./, (c) => c.toUpperCase()),
  thumbnail: f.media.find((m) => m.thumbnail)?.thumbnail, my_status: null,
});

export default function TeamQueueScreen() {
  const navigation = useNavigation();
  const { logout } = useAuth();
  const [queue, setQueue] = useState(null);
  const [local, setLocal] = useState([]);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setError(null);
    setLocal(await captures.read());
    try {
      setQueue(await fetchJson('/api/team/features/', { logout }));
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, []));

  const upload = async () => {
    setUploading(true);
    try {
      const result = await uploadCaptures(logout);
      if (result.left && !result.failed.length) Alert.alert('Still no signal', 'Try again when you have a connection.');
      await load();
    } finally {
      setUploading(false);
    }
  };

  const drop = (capture) => Alert.alert('Remove this capture?', 'Its photos on this phone are deleted too.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Remove', style: 'destructive', onPress: async () => { await captures.drop(capture.client_id, captureApi(logout)); load(); } },
  ]);

  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.accent}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
      <Header caption="Trail team" />
      <Text style={ui.title}>Review queue</Text>

      {local.length > 0 && (
        <View style={[ui.card, { borderColor: colors.warn }]}>
          <Text style={ui.label}>On this phone, not uploaded</Text>
          {local.map((c) => (
            <View key={c.client_id} style={ui.between}>
              <View style={{ flex: 1 }}>
                <Text style={ui.body}>{c.body.name || c.body.type.replace('_', ' ')} · grade {c.body.grade}</Text>
                <Text style={[ui.small, c.error && { color: colors.danger }]}>
                  {c.error || `${c.photos.filter((p) => !p.uploaded).length} photo(s) to send`}
                </Text>
              </View>
              {c.error && <Text style={[ui.small, { color: colors.danger }]} onPress={() => drop(c)}>Remove</Text>}
            </View>
          ))}
          <Button title="Upload now" icon="cloud-upload-outline" onPress={upload} loading={uploading} />
        </View>
      )}

      {!queue && error && <ErrorState message={error} onRetry={load} />}
      {!queue && !error && <Loading />}
      {queue && SECTIONS.map((s) => (
        <View key={s.key} style={ui.card}>
          <View style={ui.between}>
            <Text style={ui.label}>{s.title}</Text>
            <Text style={ui.small}>{queue[s.key].length}</Text>
          </View>
          {queue[s.key].length === 0 && <Text style={ui.small}>{s.empty}</Text>}
          {queue[s.key].map((f) => (
            <FeatureRow key={`${s.key}${f.id}`} feature={row(f)}
              subtitle={`${f.trail_name} · grade ${f.grade ?? '?'}${s.key === 'reported' ? ` · ${f.open_reports.length} report(s)` : ''}`}
              right={s.key === 'awaiting_review' && f.can_certify ? <Text style={[ui.small, { color: colors.good }]}>Ready</Text> : null}
              onPress={() => navigation.navigate('TeamFeature', { id: f.id })} />
          ))}
        </View>
      ))}

      <Button title="Add a feature" icon="add" variant="secondary" onPress={() => navigation.navigate('Capture')} />
    </ScrollView>
  );
}
