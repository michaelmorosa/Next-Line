// A trail system or trail: trail lines and feature pins coloured by the rider's status.
import { StyleSheet, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { regionFor } from '../utils/geo';
import { STATUS_COLORS, colors } from '../theme';

export default function TrailMap({ trails = [], features = [], onFeaturePress, height = 220 }) {
  const points = [
    ...trails.flatMap((t) => t.path || []),
    ...features.map((f) => [f.lat, f.lng]),
  ];
  const region = regionFor(points);
  if (!region) return null;
  return (
    <View style={[styles.wrap, { height }]}>
      <MapView style={StyleSheet.absoluteFill} initialRegion={region} mapType="terrain" userInterfaceStyle="dark"
        toolbarEnabled={false} showsUserLocation>
        {trails.filter((t) => t.path?.length > 1).map((t) => (
          <Polyline key={`t${t.id}`} coordinates={t.path.map(([latitude, longitude]) => ({ latitude, longitude }))}
            strokeColor={colors.accent} strokeWidth={4} />
        ))}
        {features.map((f) => (
          <Marker key={`f${f.id}`} coordinate={{ latitude: f.lat, longitude: f.lng }}
            title={`${f.name} · grade ${f.grade}`} description={f.type_label}
            pinColor={STATUS_COLORS[f.my_status] || colors.muted}
            onCalloutPress={onFeaturePress ? () => onFeaturePress(f) : undefined} />
        ))}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card },
});
