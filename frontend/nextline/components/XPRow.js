import { Text, View } from 'react-native';
import { shortDate, xp } from '../utils/format';
import { colors, fonts, ui } from '../theme';

// One XP ledger entry: "Drill session · Manual   +10 XP".
export default function XPRow({ entry: e }) {
  const what = e.skill_name || e.challenge_title;
  return (
    <View style={ui.between}>
      <View style={{ flex: 1, gap: 1 }}>
        <Text style={ui.body}>{what ? `${e.label} · ${what}` : e.label}</Text>
        <Text style={ui.small}>{shortDate(e.created_at)}</Text>
      </View>
      <Text style={{ fontFamily: fonts.semibold, fontSize: 15, color: e.amount < 0 ? colors.danger : colors.good }}>
        {xp(e.amount)}
      </Text>
    </View>
  );
}
