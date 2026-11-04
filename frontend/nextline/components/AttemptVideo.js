// Plays one of the rider's private attempt videos. The file needs the rider's token, so the source is fetched first.
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { VideoView, useVideoPlayer } from 'expo-video';
import { privateVideoSource } from '../api';
import { useAuth } from '../AuthContext';
import { colors, ui } from '../theme';

function Player({ source, autoPlay }) {
  const player = useVideoPlayer(source, (p) => {
    p.loop = true;
    p.muted = true;
    if (autoPlay) p.play();
  });
  return <VideoView player={player} style={StyleSheet.absoluteFill} contentFit="contain" nativeControls />;
}

export default function AttemptVideo({ url, autoPlay = true, style }) {
  const { logout } = useAuth();
  const [source, setSource] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    privateVideoSource(url, logout).then((s) => live && setSource(s)).catch((err) => live && setError(err.message));
    return () => { live = false; };
  }, [url]);

  return (
    <View style={[styles.frame, style]}>
      {source ? <Player source={source} autoPlay={autoPlay} />
        : error ? <Text style={[ui.small, { padding: 12 }]}>{error}</Text>
          : <ActivityIndicator color={colors.accent} />}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { aspectRatio: 9 / 16, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' },
});
