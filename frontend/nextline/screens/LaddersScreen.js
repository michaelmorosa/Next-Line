// Ladders at a trail system: for each feature type, every feature in grade order with the rider's status.
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useRoute } from '@react-navigation/native';
import { fetchJson } from '../api';
import { useAuth } from '../AuthContext';
import FeatureRow from '../components/FeatureRow';
import { Chip, ErrorState, Header, Loading } from '../components/ui';
import { colors, fonts, ui } from '../theme';

export default function LaddersScreen() {
  const { params } = useRoute();
  const { logout } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [type, setType] = useState(params.type || null);

  const load = async () => {
    setError(null);
    try {
      const d = await fetchJson(`/api/systems/${params.id}/ladders/`, { logout });
      setData(d);
      if (!type && d.ladders[0]) setType(d.ladders[0].type);
    } catch (err) {
      setError(err.message);
    }
  };
  useFocusEffect(useCallback(() => { load(); }, [params.id]));

  if (!data && error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Loading />;

  const ladder = data.ladders.find((l) => l.type === type) || data.ladders[0];
  return (
    <ScrollView style={ui.screen} contentContainerStyle={ui.scroll}>
      <Header caption={data.system_name} />
      <Text style={ui.title}>Ladders</Text>
      <Text style={ui.subtitle}>Each type of feature, easiest to hardest. Each rung is a small step up from the last.</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {data.ladders.map((l) => (
          <Chip key={l.type} label={`${l.label} ${l.cleaned}/${l.total}`} selected={l.type === ladder?.type}
            onPress={() => setType(l.type)} />
        ))}
      </ScrollView>
      {!ladder && <Text style={ui.small}>No graded features here yet.</Text>}
      {ladder && (
        <>
          <Text style={ui.small}>
            {ladder.best_grade ? `Your best ${ladder.label.toLowerCase()}: grade ${ladder.best_grade}.` : `You haven't cleaned a ${ladder.label.toLowerCase()} yet.`}
          </Text>
          {/* Hardest at the top, like a ladder. */}
          {[...ladder.rungs].reverse().map((rung) => {
            const reached = ladder.best_grade && rung.grade <= ladder.best_grade;
            return (
              <View key={rung.grade} style={[ui.card, reached && { borderColor: colors.good }]}>
                <View style={ui.between}>
                  <Text style={styles.rung}>Grade {rung.grade}</Text>
                  {rung.rider_cleans > 0 && (
                    <Text style={[ui.small, { color: colors.good }]}>cleaned {rung.rider_cleans}×</Text>
                  )}
                </View>
                {rung.features.map((f) => (
                  <FeatureRow key={f.id} feature={{ ...f, type_label: ladder.label, my_status: f.status }}
                    subtitle={f.trail_name} />
                ))}
              </View>
            );
          })}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  rung: { fontFamily: fonts.display, fontSize: 22, color: colors.text, textTransform: 'uppercase' },
});
