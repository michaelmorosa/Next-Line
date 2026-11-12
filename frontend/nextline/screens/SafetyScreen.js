// The full safety notice. Also shown on its own, without tabs, when a rider hasn't accepted the current version.
import { useEffect, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { fetchJson, sendJson } from '../api';
import { useAuth } from '../AuthContext';
import { Button, ErrorState, Header, Loading } from '../components/ui';
import { colors, ui } from '../theme';

export default function SafetyScreen({ mustAccept }) {
  const { user, setUser, logout } = useAuth();
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setError(null);
    fetchJson('/api/safety/', { logout }).then(setNotice).catch((err) => setError(err.message));
  };
  useEffect(load, []);

  const accept = async () => {
    setSaving(true);
    try {
      setUser(await sendJson('/api/user/me/', 'PATCH', { safety_version: notice.version }, logout));
    } catch (err) {
      Alert.alert("Couldn't save", err.message);
    } finally {
      setSaving(false);
    }
  };

  if (!notice && error) return <ErrorState message={error} onRetry={load} />;
  if (!notice) return <Loading />;

  const accepted = user && user.safety_version >= notice.version;
  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      {!mustAccept && <Header caption="Safety" />}
      <Text style={ui.title}>{notice.title}</Text>
      {mustAccept && <Text style={ui.subtitle}>Please read this before you carry on.</Text>}
      <View style={ui.card}>
        {notice.full.map((p) => <Text key={p} style={ui.body}>{p}</Text>)}
      </View>
      {notice.needs_legal_review && user?.is_trail_team && (
        <Text style={[ui.small, { color: colors.warn }]}>Draft wording: needs legal review.</Text>
      )}
      {!accepted && <Button title="I understand" onPress={accept} loading={saving} />}
      {mustAccept && <Button title="Log out" variant="outline" onPress={logout} />}
    </ScrollView>
  );
}
