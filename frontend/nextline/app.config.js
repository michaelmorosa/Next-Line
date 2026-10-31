// Extends app.json with values that shouldn't be committed. Expo loads app.json first and passes it in as `config`.
//
// GOOGLE_MAPS_ANDROID_API_KEY: Android release builds draw maps with Google Maps, which needs a key (Expo Go
// doesn't). Use a key restricted to "Maps SDK for Android" and this app's package name. Set it for EAS builds with
//   eas env:create --name GOOGLE_MAPS_ANDROID_API_KEY --value <key> --environment production --visibility sensitive
// iOS uses Apple Maps and needs nothing.
export default ({ config }) => {
  const androidMapsKey = process.env.GOOGLE_MAPS_ANDROID_API_KEY;
  if (!androidMapsKey) return config;
  return {
    ...config,
    plugins: [...(config.plugins || []), ['react-native-maps', { androidGoogleMapsApiKey: androidMapsKey }]],
  };
};
