import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import useRecorder from './recording/useRecorder';
import { colors, fonts } from './theme';

const TABS = [
  { route: 'Rides', label: 'Rides', icon: 'pulse' },
  { route: 'Record', label: 'Record', icon: 'radio-button-on' },
  { route: 'Trails', label: 'Trails', icon: 'triangle' },
  { route: 'Progress', label: 'Progress', icon: 'bar-chart' },
];

// Which tab a route belongs to, so screens opened from a tab keep it highlighted.
const TAB_FOR_ROUTE = {
  Rides: 'Rides', RideSummary: 'Rides', Settings: 'Rides', SensorLab: 'Rides',
  Record: 'Record',
  Trails: 'Trails', Trail: 'Trails', PinFeature: 'Trails',
  Progress: 'Progress', LevelGuide: 'Progress',
};

function TabBar() {
  const navigation = useNavigation();
  const route = useRoute();
  const { status } = useRecorder();
  const active = TAB_FOR_ROUTE[route.name];
  const recording = status === 'recording' || status === 'paused';
  return (
    <View style={styles.tabBar}>
      {TABS.map((tab) => {
        const selected = tab.route === active;
        const color = selected ? colors.accent : colors.muted;
        return (
          <TouchableOpacity
            key={tab.route}
            style={styles.tab}
            onPress={() => navigation.navigate(tab.route)}
            accessibilityRole="tab"
            accessibilityLabel={tab.label}
            accessibilityState={{ selected }}
          >
            <Ionicons name={tab.icon} size={22} color={tab.route === 'Record' && recording ? colors.accent : color} />
            <Text style={[styles.tabLabel, { color }]}>{tab.route === 'Record' && recording ? 'Recording' : tab.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export default function ScreenContainer({ children, tabs = true }) {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>{children}</View>
      {tabs && <TabBar />}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.bg },
  content: { flex: 1 },
  tabBar: {
    height: 64,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4 },
  tabLabel: { fontFamily: fonts.medium, fontSize: 12 },
});
