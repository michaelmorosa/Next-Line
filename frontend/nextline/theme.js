// Colors and type from the "Line" mockup: dark trail greens with an orange accent.
import { StyleSheet } from 'react-native';

export const colors = {
  bg: '#10140F',
  card: '#182016',
  cardRaised: '#1B2418',
  button: '#263022',
  border: '#2A3226',
  borderDashed: '#4A5644',
  barMuted: '#3E4B39',
  dotMuted: '#3A4436',
  text: '#E8EDE4',
  muted: '#9AA596',
  accent: '#F2994A',
  good: '#7FD1C1',
  warn: '#E6D36A',
  danger: '#E5636B',
};

export const fonts = {
  regular: 'Barlow_400Regular',
  medium: 'Barlow_500Medium',
  semibold: 'Barlow_600SemiBold',
  display: 'BarlowCondensed_700Bold',
};

export const DIFFICULTY = {
  unrated: { label: 'Unrated', color: colors.muted },
  green: { label: 'Green', color: '#6FCF7F' },
  blue: { label: 'Blue', color: '#6FA8DC' },
  black: { label: 'Black diamond', color: colors.text },
  double_black: { label: 'Double black', color: colors.text },
};

export const ui = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: 20, paddingBottom: 40, gap: 14 },
  title: { fontFamily: fonts.display, fontSize: 40, lineHeight: 42, color: colors.text, textTransform: 'uppercase' },
  subtitle: { fontFamily: fonts.regular, fontSize: 14, color: colors.muted, marginTop: 4 },
  label: { fontFamily: fonts.medium, fontSize: 13, color: colors.muted, textTransform: 'uppercase', letterSpacing: 1 },
  body: { fontFamily: fonts.regular, fontSize: 15, color: colors.text },
  strong: { fontFamily: fonts.semibold, fontSize: 15, color: colors.text },
  small: { fontFamily: fonts.regular, fontSize: 13, color: colors.muted },
  number: { fontFamily: fonts.display, fontSize: 34, color: colors.text },
  card: { padding: 16, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, gap: 10 },
  cardRaised: { padding: 16, borderRadius: 16, backgroundColor: colors.cardRaised, gap: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  between: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  input: {
    height: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card,
    paddingHorizontal: 14, color: colors.text, fontFamily: fonts.regular, fontSize: 16,
  },
  error: { fontFamily: fonts.medium, fontSize: 14, color: colors.danger },
});
