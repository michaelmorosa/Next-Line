// The three one-tap outcomes. Big targets for gloves; walking it is shown the same as the others.
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { OUTCOMES } from '../utils/features';
import { STATUS_COLORS, colors, fonts } from '../theme';

export default function OutcomeButtons({ selected, onPick, compact, disabled }) {
  return (
    <View style={styles.row}>
      {OUTCOMES.map((o) => {
        const on = selected === o.key;
        const color = STATUS_COLORS[o.key];
        return (
          <TouchableOpacity
            key={o.key}
            style={[styles.button, compact && styles.compact, on && { backgroundColor: color, borderColor: color },
              disabled && { opacity: 0.5 }]}
            onPress={() => onPick(on && compact ? null : o.key)}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityLabel={o.label}
            accessibilityState={{ selected: on }}
          >
            <Ionicons name={o.icon} size={compact ? 18 : 22} color={on ? colors.bg : color === colors.dotMuted ? colors.muted : color} />
            <Text style={[styles.text, compact && { fontSize: 12 }, on && { color: colors.bg }]} numberOfLines={1}>
              {compact ? o.short : o.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8 },
  button: {
    flex: 1, minHeight: 64, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.cardRaised,
    alignItems: 'center', justifyContent: 'center', gap: 4, paddingHorizontal: 4,
  },
  compact: { minHeight: 48, borderRadius: 12 },
  text: { fontFamily: fonts.semibold, fontSize: 13, color: colors.text, textAlign: 'center' },
});
