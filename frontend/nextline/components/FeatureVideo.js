// A feature's POV clip. Public, so it plays straight from its URL.
import { StyleSheet, View } from 'react-native';
import { VideoView, useVideoPlayer } from 'expo-video';

export default function FeatureVideo({ url }) {
  const player = useVideoPlayer(url, (p) => {
    p.loop = false;
    p.muted = true;
  });
  return (
    <View style={styles.frame}>
      <VideoView player={player} style={StyleSheet.absoluteFill} contentFit="contain" nativeControls />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { aspectRatio: 16 / 9, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000' },
});
