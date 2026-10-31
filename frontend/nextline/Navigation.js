import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from './AuthContext';
import ScreenContainer from './ScreenContainer';
import LevelGuideScreen from './screens/LevelGuideScreen';
import LoginScreen from './screens/LoginScreen';
import PinFeatureScreen from './screens/PinFeatureScreen';
import ProgressScreen from './screens/ProgressScreen';
import RecordScreen from './screens/RecordScreen';
import RegisterScreen from './screens/RegisterScreen';
import RideSummaryScreen from './screens/RideSummaryScreen';
import RidesScreen from './screens/RidesScreen';
import SensorLabScreen from './screens/SensorLabScreen';
import SettingsScreen from './screens/SettingsScreen';
import TrailScreen from './screens/TrailScreen';
import TrailsScreen from './screens/TrailsScreen';
import { colors } from './theme';

const Stack = createNativeStackNavigator();

// `tabs: false` hides the bottom bar (logged-out screens).
const APP_SCREENS = [
  { name: 'Rides', component: RidesScreen },
  { name: 'Record', component: RecordScreen },
  { name: 'Trails', component: TrailsScreen },
  { name: 'Progress', component: ProgressScreen },
  { name: 'LevelGuide', component: LevelGuideScreen },
  { name: 'RideSummary', component: RideSummaryScreen },
  { name: 'Trail', component: TrailScreen },
  { name: 'PinFeature', component: PinFeatureScreen },
  { name: 'Settings', component: SettingsScreen },
  { name: 'SensorLab', component: SensorLabScreen },
];

const GUEST_SCREENS = [
  { name: 'Login', component: LoginScreen, tabs: false },
  { name: 'Register', component: RegisterScreen, tabs: false },
];

export default function Navigation() {
  const { isAuthenticated } = useAuth();
  const screens = isAuthenticated ? APP_SCREENS : GUEST_SCREENS;
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
