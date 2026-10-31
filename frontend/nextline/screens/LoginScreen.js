import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { publicPost } from '../api';
import { useAuth } from '../AuthContext';
import { Button } from '../components/ui';
import { colors, ui } from '../theme';

export default function LoginScreen() {
  const navigation = useNavigation();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!username || !password) {
      setError('Enter your username and password.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await login(await publicPost('/api/auth/jwt/create/', { username: username.trim(), password }));
    } catch (err) {
      setError(err.status === 401 ? 'Wrong username or password.' : err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.brand}>Next Line</Text>
        <Text style={ui.subtitle}>Put your phone in your pocket and ride. We'll find the jumps, PRs and progress.</Text>
        <View style={{ gap: 10, marginTop: 24 }}>
          <TextInput style={ui.input} placeholder="Username" placeholderTextColor={colors.muted} value={username}
            onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} returnKeyType="next" />
          <TextInput style={ui.input} placeholder="Password" placeholderTextColor={colors.muted} value={password}
            onChangeText={setPassword} secureTextEntry returnKeyType="go" onSubmitEditing={submit} />
        </View>
        {error && <Text style={ui.error}>{error}</Text>}
        <Button title="Log in" onPress={submit} loading={loading} />
        <TouchableOpacity onPress={() => navigation.navigate('Register')} style={styles.link}>
          <Text style={ui.small}>New here? <Text style={{ color: colors.accent }}>Create an account</Text></Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, justifyContent: 'center', padding: 24, gap: 14 },
  brand: { ...StyleSheet.flatten(ui.title), fontSize: 56, lineHeight: 58, color: colors.accent },
  link: { alignItems: 'center', padding: 12 },
});
