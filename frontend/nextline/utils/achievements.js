import { Alert } from 'react-native';

// Pop up any achievements the server says were just earned ({ title, description } from new_achievements).
export function announceAchievements(earned) {
  if (!earned?.length) return false;
  const lines = earned.map((a) => `🏆 ${a.title}: ${a.description}`).join('\n');
  Alert.alert(earned.length === 1 ? 'Achievement unlocked' : `${earned.length} achievements unlocked`, lines);
  return true;
}
