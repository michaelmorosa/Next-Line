// One feature in a list: photo, name, type and grade, notices, and the rider's status on it.
import { Image, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { STATUS_LABELS, featureMeta } from '../utils/features';
import { STATUS_COLORS, TYPE_ICONS, colors, fonts, ui } from '../theme';

export function FeatureThumb({ feature, size = 56 }) {
  if (feature.thumbnail) {
    return <Image source={{ uri: feature.thumbnail }} style={[styles.thumb, { width: size, height: size }]} />;
  }
  return (
    <View style={[styles.thumb, styles.placeholder, { width: size, height: size }]}>
      <Ionicons name={TYPE_ICONS[feature.type] || 'flag'} size={size * 0.45} color={colors.muted} />
    </View>
  );
}

export function GradeChip({ grade }) {
  return (
    <View style={styles.grade}>
      <Text style={styles.gradeText}>{grade ?? '?'}</Text>
    </View>
  );
}

export function StatusPill({ status, cleans }) {
  const color = STATUS_COLORS[status] || colors.muted;
  const label = status === 'cleaned' && cleans > 1 ? `Cleaned ×${cleans}` : STATUS_LABELS[status] || status;
  return <Text style={[styles.pill, { color, borderColor: color }]}>{label}</Text>;
}

export default function FeatureRow({ feature: f, right, onPress, subtitle }) {
  const navigation = useNavigation();
  const notices = [f.changed && 'Changed', f.stale && 'Not recently verified', f.has_ride_around && 'Ride-around']
    .filter(Boolean);
  return (
    <TouchableOpacity style={[ui.row, styles.row]} onPress={onPress || (() => navigation.navigate('Feature', { id: f.id }))}
      accessibilityLabel={`${f.name}, ${featureMeta(f)}`}>
      <FeatureThumb feature={f} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={ui.strong} numberOfLines={1}>{f.name}</Text>
        <Text style={ui.small} numberOfLines={1}>{subtitle || featureMeta(f)}</Text>
        {notices.length > 0 && (
          <Text style={[ui.small, { fontSize: 12, color: f.changed ? colors.warn : colors.muted }]} numberOfLines={1}>
            {notices.join(' · ')}
          </Text>
        )}
      </View>
      {right !== undefined ? right : <StatusPill status={f.my_status} cleans={f.my_cleans} />}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: 4 },
  thumb: { borderRadius: 10, backgroundColor: colors.cardRaised },
  placeholder: { alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  grade: {
    minWidth: 34, height: 34, borderRadius: 17, backgroundColor: colors.accent, alignItems: 'center',
    justifyContent: 'center', paddingHorizontal: 6,
  },
  gradeText: { fontFamily: fonts.display, fontSize: 20, color: colors.bg },
  pill: {
    fontFamily: fonts.medium, fontSize: 12, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10,
    borderWidth: 1, overflow: 'hidden',
  },
});
