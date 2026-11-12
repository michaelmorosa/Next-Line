// Trail team: the grading guidelines (edited in the admin), so grades stay consistent on site.
import { useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import { ErrorState, Header, Loading } from '../components/ui';
import { markdownBlocks } from '../utils/markdown';
import { colors, fonts, ui } from '../theme';

const STYLE = {
  h1: [ui.title, { fontSize: 30, lineHeight: 32 }],
  h2: [ui.strong, { fontSize: 19, marginTop: 10, color: colors.accent }],
  h3: [ui.strong, { marginTop: 6 }],
  p: ui.body,
  li: ui.body,
};

export default function GuidelinesScreen() {
  const { logout } = useAuth();
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setError(null);
    fetchJson('/api/team/guidelines/', { logout }).then(setDoc).catch((err) => setError(err.message));
  };
  useEffect(load, []);

  if (!doc && error) return <ErrorState message={error} onRetry={load} />;
  if (!doc) return <Loading />;

  return (
    <ScrollView style={ui.screen} contentContainerStyle={[ui.scroll, { gap: 8 }]}>
      <Header caption="Grading guidelines" />
      {markdownBlocks(doc.body).map((b, i) => {
        if (b.type === 'table') {
          return (
            <View key={i} style={[ui.card, { gap: 6, padding: 12 }]}>
              {b.rows.map((cells, j) => (
                <View key={j} style={{ flexDirection: 'row', gap: 10 }}>
                  <Text style={[ui.strong, { width: 52, fontFamily: j === 0 ? fonts.semibold : fonts.display }]}>{cells[0]}</Text>
                  <Text style={[ui.small, { flex: 1, color: j === 0 ? colors.muted : colors.text }]}>{cells.slice(1).join(' · ')}</Text>
                </View>
              ))}
            </View>
          );
        }
        return <Text key={i} style={STYLE[b.type]}>{b.type === 'li' ? `• ${b.text}` : b.text}</Text>;
      })}
    </ScrollView>
  );
}
