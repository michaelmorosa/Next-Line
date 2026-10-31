import { Text, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { colors, fonts } from '../theme';

// Flow score in a ring that fills with the score.
export default function FlowRing({ score, size = 76 }) {
  const stroke = 6;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const filled = score == null ? 0 : (score / 100) * circumference;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size} style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={colors.border} strokeWidth={stroke} fill="none" />
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={colors.accent} strokeWidth={stroke} fill="none"
          strokeDasharray={`${filled} ${circumference}`} strokeLinecap="round" />
      </Svg>
      <Text style={{ fontFamily: fonts.display, fontSize: 30, color: colors.text }}>
        {score == null ? '—' : Math.round(score)}
      </Text>
    </View>
  );
}
