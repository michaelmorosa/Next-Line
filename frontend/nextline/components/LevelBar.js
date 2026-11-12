import { Text, View } from 'react-native';
import { ProgressBar } from './ui';
import { colors, ui } from '../theme';

// Level, title, points bar and practice streak, from any response's `level` and `streak_weeks`.
export default function LevelBar({ level, streakWeeks }) {
  return (
    <View style={{ gap: 6 }}>
      <View style={ui.between}>
        <Text style={ui.strong}>Level {level.level} · {level.title}</Text>
        <Text style={ui.small}>{level.total.toLocaleString()} points</Text>
      </View>
      <ProgressBar fraction={level.fraction} />
      <View style={ui.between}>
        <Text style={ui.small}>
          {level.to_next == null ? 'Top level' : `${level.to_next.toLocaleString()} points to level ${level.level + 1}`}
        </Text>
        {streakWeeks > 0 && <Text style={[ui.small, { color: colors.accent }]}>🔥 {streakWeeks}-week streak</Text>}
      </View>
    </View>
  );
}
