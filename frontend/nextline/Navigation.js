import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from './AuthContext';
import ScreenContainer from './ScreenContainer';
import CaptureFeatureScreen from './screens/CaptureFeatureScreen';
import ChallengesScreen from './screens/ChallengesScreen';
import FeatureScreen from './screens/FeatureScreen';
import GuidelinesScreen from './screens/GuidelinesScreen';
import LaddersScreen from './screens/LaddersScreen';
import LevelGuideScreen from './screens/LevelGuideScreen';
import LogTrailScreen from './screens/LogTrailScreen';
import LoginScreen from './screens/LoginScreen';
import NextUpScreen from './screens/NextUpScreen';
import ProgressScreen from './screens/ProgressScreen';
import RecordScreen from './screens/RecordScreen';
import RegisterScreen from './screens/RegisterScreen';
import RideSummaryScreen from './screens/RideSummaryScreen';
import RidesScreen from './screens/RidesScreen';
import SafetyScreen from './screens/SafetyScreen';
import SensorLabScreen from './screens/SensorLabScreen';
import SettingsScreen from './screens/SettingsScreen';
import SystemScreen from './screens/SystemScreen';
import TeamFeatureScreen from './screens/TeamFeatureScreen';
import TeamQueueScreen from './screens/TeamQueueScreen';
import TrailFeaturesScreen from './screens/TrailFeaturesScreen';
import TrailScreen from './screens/TrailScreen';
import TrailSystemsScreen from './screens/TrailSystemsScreen';
import TrailsScreen from './screens/TrailsScreen';
import XPHistoryScreen from './screens/XPHistoryScreen';
import { colors } from './theme';

const Stack = createNativeStackNavigator();

// `tabs: false` hides the bottom bar (logged-out screens).
const APP_SCREENS = [
  { name: 'Rides', component: RidesScreen },
  { name: 'Record', component: RecordScreen },
  { name: 'Trails', component: TrailSystemsScreen },
  { name: 'NextUp', component: NextUpScreen },
  { name: 'Progress', component: ProgressScreen },
  { name: 'System', component: SystemScreen },
  { name: 'TrailFeatures', component: TrailFeaturesScreen },
  { name: 'Feature', component: FeatureScreen },
  { name: 'LogTrail', component: LogTrailScreen },
  { name: 'Ladders', component: LaddersScreen },
  { name: 'Safety', component: SafetyScreen },
  { name: 'TimedTrails', component: TrailsScreen },
  { name: 'Trail', component: TrailScreen },
  { name: 'LevelGuide', component: LevelGuideScreen },
  { name: 'XPHistory', component: XPHistoryScreen },
  { name: 'Challenges', component: ChallengesScreen },
  { name: 'RideSummary', component: RideSummaryScreen },
  { name: 'Settings', component: SettingsScreen },
  { name: 'SensorLab', component: SensorLabScreen },
  // Trail team only (the entry points are hidden from riders, and the server checks).
  { name: 'Capture', component: CaptureFeatureScreen },
  { name: 'TeamQueue', component: TeamQueueScreen },
  { name: 'TeamFeature', component: TeamFeatureScreen },
  { name: 'Guidelines', component: GuidelinesScreen },
];

const GUEST_SCREENS = [
  { name: 'Login', component: LoginScreen, tabs: false },
  { name: 'Register', component: RegisterScreen, tabs: false },
];

// Riders who haven't accepted the current safety notice see only that until they do.
const SAFETY_SCREENS = [
  { name: 'AcceptSafety', component: () => <SafetyScreen mustAccept />, tabs: false },
];

export default function Navigation() {
  const { isAuthenticated, user } = useAuth();
  let screens = GUEST_SCREENS;
  if (isAuthenticated) {
    const needsSafety = user && user.safety_current_version != null && user.safety_version < user.safety_current_version;
    screens = needsSafety ? SAFETY_SCREENS : APP_SCREENS;
  }
  return (
    <Stack.Navigator screenOptions={{ headerShown: false, animation: 'fade', contentStyle: { backgroundColor: colors.bg } }}>
      {screens.map(({ name, component: Component, tabs = true }) => (
        <Stack.Screen key={name} name={name}>
          {() => (
            <ScreenContainer tabs={tabs}>
              <Component />
            </ScreenContainer>
          )}
        </Stack.Screen>
      ))}
    </Stack.Navigator>
  );
}
