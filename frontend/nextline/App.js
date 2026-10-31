import { useEffect } from 'react';
import { AppState } from 'react-native';
import { DarkTheme, NavigationContainer } from '@react-navigation/native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useFonts, Barlow_400Regular, Barlow_500Medium, Barlow_600SemiBold } from '@expo-google-fonts/barlow';
import { BarlowCondensed_700Bold } from '@expo-google-fonts/barlow-condensed';
import { AuthProvider, useAuth } from './AuthContext';
import Navigation from './Navigation';
import CrashPrompt from './components/CrashPrompt';
import { restore } from './recording/recorder';
import { uploadPending } from './recording/uploads';
import { colors } from './theme';

const theme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.bg, card: colors.bg, primary: colors.accent, text: colors.text },
};

// Uploads rides recorded offline whenever the app comes back to the foreground with a logged-in rider.
function BackgroundSync() {
  const { isAuthenticated, logout } = useAuth();
  useEffect(() => {
    if (!isAuthenticated) return undefined;
    uploadPending(logout);
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'active') uploadPending(logout);
    });
    return () => sub.remove();
  }, [isAuthenticated]);
  return null;
}

export default function App() {
  const [fontsLoaded] = useFonts({ Barlow_400Regular, Barlow_500Medium, Barlow_600SemiBold, BarlowCondensed_700Bold });

  useEffect(() => {
    restore();
  }, []);

  if (!fontsLoaded) return null;

  return (
    <SafeAreaProvider>
      <AuthProvider>
        <NavigationContainer theme={theme}>
          <StatusBar style="light" />
          <Navigation />
          <BackgroundSync />
          <CrashPrompt />
        </NavigationContainer>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
