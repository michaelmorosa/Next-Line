import { Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, ui } from '../theme';

const ICONS = { feature: 'flag', climb: 'trending-up', speed: 'speedometer', air: 'airplane', weeks: 'calendar' };

// One "way to level up" from /api/progress/ suggestions. Opens its trail when it has one.
export default function SuggestionRow({ suggestion: s }) {
  const navigation = useNavigation();
  const body = (
    <View style={[ui.row, { alignItems: 'flex-start' }]}>
      <Ionicons name={ICONS[s.kind] || 'flag'} size={18} color={colors.accent} style={{ marginTop: 2 }} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={ui.strong}>{s.title}</Text>
        <Text style={ui.small}>{s.detail}</Text>
      </View>
      {s.points > 0 && <Text style={{ fontFamily: fonts.semibold, fontSize: 14, color: colors.good }}>+{s.points}</Text>}
    </View>
  );
  if (!s.trail) return body;
  return <TouchableOpacity onPress={() => navigation.navigate('Trail', { id: s.trail })}>{body}</TouchableOpacity>;
}
