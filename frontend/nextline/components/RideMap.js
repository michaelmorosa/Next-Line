import { StyleSheet, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { regionFor } from '../utils/geo';
import { colors } from '../theme';

const FEATURE_COLORS = { cleaned: colors.good, almost: colors.warn, locked: colors.muted };

// A route ([[lat, lng], ...]) with jump dots and feature pins. `onPress` gets { latitude, longitude } for pinning.
export default function RideMap({ path, jumps = [], features = [], pin, onPress, height = 160 }) {
  const region = regionFor(path);
  if (!region) return null;
  return (
    <View style={[styles.wrap, { height }]}>
      <MapView
        style={StyleSheet.absoluteFill}
        initialRegion={region}
        mapType="terrain"
        userInterfaceStyle="dark"
        toolbarEnabled={false}
        onPress={onPress ? (e) => onPress(e.nativeEvent.coordinate) : undefined}
      >
        <Polyline
          coordinates={path.map(([latitude, longitude]) => ({ latitude, longitude }))}
          strokeColor={colors.accent}
          strokeWidth={4}
        />
        {jumps.filter((j) => j.lat != null).map((j, i) => (
          <Marker key={`j${i}`} coordinate={{ latitude: j.lat, longitude: j.lng }} anchor={{ x: 0.5, y: 0.5 }}
            title={`Jump · ${j.airtime_s.toFixed(2)} s`}>
            <View style={[styles.dot, { backgroundColor: colors.good }]} />
          </Marker>
        ))}
        {features.map((f) => (
          <Marker key={`f${f.id}`} coordinate={{ latitude: f.lat, longitude: f.lng }} title={f.name}
            pinColor={FEATURE_COLORS[f.status] || colors.muted} />
        ))}
        {pin && <Marker coordinate={pin} pinColor={colors.accent} />}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card },
  dot: { width: 12, height: 12, borderRadius: 6, borderWidth: 2, borderColor: colors.bg },
});
