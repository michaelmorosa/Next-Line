import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import { publicPost } from '../api';
import { useAuth } from '../AuthContext';
import { Button, Header } from '../components/ui';
import { colors, ui } from '../theme';

export default function RegisterScreen() {
  const { login } = useAuth();
  const [form, setForm] = useState({ username: '', email: '', password: '', re_password: '' });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    if (Object.values(form).some((v) => !v)) {
      setError('Fill in every field.');
      return;
    }
    if (form.password !== form.re_password) {
      setError("Passwords don't match.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const body = { ...form, username: form.username.trim(), email: form.email.trim() };
      const created = await publicPost('/api/auth/users/', body);
      try {
        await login(await publicPost('/api/auth/jwt/create/', { username: body.username, password: form.password }));
      } catch {
        // The server requires email activation first.
        setError(`Account created for ${created.username}. Check your email to activate it, then log in.`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const field = (key, placeholder, props = {}) => (
    <TextInput style={ui.input} placeholder={placeholder} placeholderTextColor={colors.muted} value={form[key]}
      onChangeText={set(key)} autoCapitalize="none" autoCorrect={false} {...props} />
  );

  return (
    <KeyboardAvoidingView style={ui.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Header />
        <Text style={ui.title}>Create account</Text>
        {field('username', 'Username')}
        {field('email', 'Email', { keyboardType: 'email-address' })}
        {field('password', 'Password (10+ characters)', { secureTextEntry: true })}
        {field('re_password', 'Repeat password', { secureTextEntry: true })}
        {error && <Text style={ui.error}>{error}</Text>}
        <Button title="Create account" onPress={submit} loading={loading} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 24, gap: 12 },
});
