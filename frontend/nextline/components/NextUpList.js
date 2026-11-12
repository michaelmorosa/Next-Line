// "Next up when you're ready": suggested features with the reason for each.
import { Text, View } from 'react-native';
import FeatureRow, { GradeChip } from './FeatureRow';
import { colors, ui } from '../theme';

export default function NextUpList({ items, empty }) {
  if (!items.length) {
    return <Text style={ui.small}>{empty || 'Nothing to suggest yet. Ride a trail with graded features and log how it went.'}</Text>;
  }
  return (
    <View style={{ gap: 14 }}>
      {items.map((f) => (
        <View key={f.id} style={{ gap: 6 }}>
          <FeatureRow feature={f} subtitle={`${f.type_label} on ${f.trail_name}`} right={<GradeChip grade={f.grade} />} />
          <Text style={[ui.small, { color: colors.text }]}>{f.reason}</Text>
        </View>
      ))}
    </View>
  );
}
