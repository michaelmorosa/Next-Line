// The short safety notice, shown on every feature page and trail page. Tapping it opens the full notice.
import { Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, ui } from '../theme';

export const SAFETY_FALLBACK = "Grades are our team's opinion, and trails change. You decide what to ride. Use the "
  + "ride-around whenever you're unsure.";

export default function SafetyNote({ text }) {
  const navigation = useNavigation();
  return (
    <TouchableOpacity style={[ui.card, { flexDirection: 'row', gap: 10, alignItems: 'flex-start' }]}
      onPress={() => navigation.navigate('Safety')} accessibilityRole="button">
      <Ionicons name="shield-checkmark-outline" size={18} color={colors.muted} style={{ marginTop: 1 }} />
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={ui.small}>{text || SAFETY_FALLBACK}</Text>
        <Text style={[ui.small, { color: colors.accent }]}>Read the full notice ›</Text>
      </View>
    </TouchableOpacity>
  );
}
