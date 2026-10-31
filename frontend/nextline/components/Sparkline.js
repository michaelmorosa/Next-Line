import { useState } from 'react';
import { View } from 'react-native';
import Svg, { Circle, Polyline } from 'react-native-svg';
import { colors } from '../theme';

// A line through `values`, highest value at the top, last point marked.
export default function Sparkline({ values, height = 70, color = colors.accent }) {
  const [width, setWidth] = useState(0);
  const pad = 6;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => [
    pad + (values.length === 1 ? 0 : (i / (values.length - 1)) * (width - pad * 2)),
    pad + (1 - (v - min) / span) * (height - pad * 2),
  ]);
  const last = points[points.length - 1];
  return (
    <View style={{ height }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {width > 0 && (
        <Svg width={width} height={height}>
          <Polyline points={points.map((p) => p.join(',')).join(' ')} fill="none" stroke={color} strokeWidth={3}
            strokeLinecap="round" strokeLinejoin="round" />
          <Circle cx={last[0]} cy={last[1]} r={5} fill={color} />
        </Svg>
      )}
    </View>
  );
}
