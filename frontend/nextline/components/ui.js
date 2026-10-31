// Small building blocks shared by the screens, styled after the mockup.
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, ui } from '../theme';

// Round outlined icon button (back, share, settings).
export function CircleButton({ icon, onPress, label }) {
  return (
    <TouchableOpacity style={styles.circle} onPress={onPress} accessibilityLabel={label} hitSlop={6}>
      <Ionicons name={icon} size={20} color={colors.text} />
    </TouchableOpacity>
  );
}

// Back button, small uppercase caption in the middle, optional action on the right.
export function Header({ caption, back = true, right }) {
  const navigation = useNavigation();
  return (
    <View style={styles.header}>
      {back && navigation.canGoBack()
        ? <CircleButton icon="chevron-back" label="Back" onPress={() => navigation.goBack()} />
        : <View style={styles.circleSpacer} />}
      <Text style={[ui.label, styles.headerCaption]} numberOfLines={1}>{caption}</Text>
      {right || <View style={styles.circleSpacer} />}
    </View>
  );
}

export function Button({ title, onPress, variant = 'primary', disabled, loading, style, icon }) {
  const v = VARIANTS[variant];
  return (
    <TouchableOpacity
      style={[styles.button, v.button, (disabled || loading) && styles.disabled, style]}
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
    >
      {loading ? <ActivityIndicator color={v.text.color} /> : (
        <View style={ui.row}>
          {icon && <Ionicons name={icon} size={18} color={v.text.color} />}
          <Text style={[styles.buttonText, v.text]}>{title}</Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

const VARIANTS = {
  primary: { button: { backgroundColor: colors.accent }, text: { color: colors.bg } },
  secondary: { button: { backgroundColor: colors.button }, text: { color: colors.text } },
  outline: { button: { borderWidth: 1, borderColor: colors.border }, text: { color: colors.text } },
  dashed: { button: { borderWidth: 1, borderStyle: 'dashed', borderColor: colors.borderDashed }, text: { color: colors.text } },
  danger: { button: { borderWidth: 1, borderColor: colors.danger }, text: { color: colors.danger } },
};

export function StatTile({ label, value, sub, subColor, center, small }) {
  return (
    <View style={[styles.tile, center && { alignItems: 'center' }]}>
      {label ? <Text style={[ui.label, { fontSize: 12 }]}>{label}</Text> : null}
      <Text style={[ui.number, small && { fontSize: 28 }]} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
      {sub ? <Text style={[ui.small, subColor && { color: subColor }]} numberOfLines={2}>{sub}</Text> : null}
    </View>
  );
}

export function Grid({ children, columns = 2 }) {
  const items = Array.isArray(children) ? children.filter(Boolean) : [children];
  const rows = [];
  for (let i = 0; i < items.length; i += columns) rows.push(items.slice(i, i + columns));
  return (
    <View style={{ gap: 12 }}>
      {rows.map((row, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: 12 }}>
          {row.map((item, j) => <View key={j} style={{ flex: 1 }}>{item}</View>)}
          {row.length < columns && Array.from({ length: columns - row.length }, (_, j) => <View key={`pad${j}`} style={{ flex: 1 }} />)}
        </View>
      ))}
    </View>
  );
}

export function ProgressBar({ fraction, color = colors.accent }) {
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`, backgroundColor: color }]} />
    </View>
  );
}

export function Chip({ label, selected, onPress, color = colors.accent }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, selected && { backgroundColor: color, borderColor: color }]}
      accessibilityRole="button"
      accessibilityState={{ selected }}
    >
      <Text style={[styles.chipText, selected && { color: colors.bg, fontFamily: fonts.semibold }]}>{label}</Text>
    </Pressable>
  );
}

export function Loading() {
  return (
    <View style={styles.centerFill}>
      <ActivityIndicator color={colors.accent} size="large" />
    </View>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <View style={[styles.centerFill, { gap: 14, padding: 24 }]}>
      <Text style={[ui.body, { textAlign: 'center' }]}>{message}</Text>
      {onRetry && <Button title="Try again" variant="secondary" onPress={onRetry} style={{ alignSelf: 'stretch' }} />}
    </View>
  );
}

// Bottom sheet of choices. Android's Alert can only show three buttons. options: [{ text, onPress, destructive }]
export function OptionsSheet({ title, message, options, onClose }) {
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.sheetBackdrop} onPress={onClose}>
        <Pressable style={styles.sheet}>
          <Text style={[ui.strong, { fontSize: 18 }]}>{title}</Text>
          {message ? <Text style={ui.small}>{message}</Text> : null}
          {options.map((o) => (
            <Button
              key={o.text}
              title={o.text}
              variant={o.destructive ? 'danger' : 'secondary'}
              onPress={() => {
                onClose();
                o.onPress();
              }}
            />
          ))}
          <Button title="Cancel" variant="outline" onPress={onClose} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  sheetBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: {
    backgroundColor: colors.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, paddingBottom: 36,
    gap: 10, borderWidth: 1, borderColor: colors.border,
  },
  circle: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  circleSpacer: { width: 44, height: 44 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  headerCaption: { flex: 1, textAlign: 'center' },
  button: { minHeight: 52, borderRadius: 14, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16 },
  buttonText: { fontFamily: fonts.semibold, fontSize: 16 },
  disabled: { opacity: 0.5 },
  tile: { padding: 14, borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, gap: 2 },
  barTrack: { height: 10, borderRadius: 5, backgroundColor: colors.border, overflow: 'hidden' },
  barFill: { height: 10 },
  chip: {
    paddingHorizontal: 14, minHeight: 40, borderRadius: 20, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  chipText: { fontFamily: fonts.medium, fontSize: 14, color: colors.text },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
