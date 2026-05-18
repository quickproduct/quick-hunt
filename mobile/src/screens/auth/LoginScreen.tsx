import React, { useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuthStore } from '../../store/authStore';
import { AuthStackParamList } from '../../navigation/AppNavigator';
import { useTheme } from '../../context/ThemeContext';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard } from '../../components/GlassKit';

export default function LoginScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList, 'Login'>>();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const { login, isLoading } = useAuthStore();
  const { colors } = useTheme();

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }

    try {
      await login(email.trim(), password.trim());
    } catch (error: any) {
      Alert.alert('Login Failed', error.response?.data?.detail || 'Invalid credentials');
    }
  };

  return (
    <SVGBackground>
      <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.content}>
          <View style={styles.hero}>
            <View style={[styles.logo, { backgroundColor: colors.primarySoft, borderColor: colors.border }]}>
              <Ionicons name="sparkles" size={30} color={colors.primary} />
            </View>
            <Text style={[styles.kicker, { color: colors.textMuted }]}>AI application studio</Text>
            <Text style={[styles.title, { color: colors.text }]}>QuickHunt</Text>
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Track, score, write, and send from one polished workspace.</Text>
          </View>

          <GlassCard style={styles.card}>
            <View style={[styles.inputShell, { backgroundColor: colors.input, borderColor: colors.border }]}>
              <Ionicons name="mail-outline" size={18} color={colors.textMuted} />
              <TextInput
                style={[styles.input, { color: colors.text }]}
                placeholder="Email"
                placeholderTextColor={colors.textMuted}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>

            <View style={[styles.inputShell, { backgroundColor: colors.input, borderColor: colors.border }]}>
              <Ionicons name="lock-closed-outline" size={18} color={colors.textMuted} />
              <TextInput
                style={[styles.input, { color: colors.text }]}
                placeholder="Password"
                placeholderTextColor={colors.textMuted}
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!showPassword}
              />
              <Pressable onPress={() => setShowPassword(!showPassword)} hitSlop={10}>
                <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={19} color={colors.textSecondary} />
              </Pressable>
            </View>

            <AppButton
              label={isLoading ? 'Signing in' : 'Sign In'}
              icon={isLoading ? undefined : 'arrow-forward-outline'}
              onPress={handleLogin}
              disabled={isLoading}
              style={styles.primaryButton}
            />
            {isLoading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : null}

            <View style={styles.links}>
              <Pressable onPress={() => navigation.navigate('Register')} hitSlop={8}>
                <Text style={[styles.linkPrimary, { color: colors.primary }]}>Create account</Text>
              </Pressable>
              <Pressable onPress={() => navigation.navigate('ForgotPassword')} hitSlop={8}>
                <Text style={[styles.linkMuted, { color: colors.textMuted }]}>Forgot password?</Text>
              </Pressable>
            </View>
          </GlassCard>
        </View>
      </KeyboardAvoidingView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: 22, paddingVertical: 32 },
  hero: { alignItems: 'center', marginBottom: 24 },
  logo: { alignItems: 'center', borderRadius: 24, borderWidth: 1, height: 68, justifyContent: 'center', marginBottom: 18, width: 68 },
  kicker: { fontSize: 12, fontWeight: '900', letterSpacing: 0, marginBottom: 6, textTransform: 'uppercase' },
  title: { fontSize: 38, fontWeight: '900', letterSpacing: 0, marginBottom: 8 },
  subtitle: { fontSize: 15, fontWeight: '700', lineHeight: 22, maxWidth: 280, textAlign: 'center' },
  card: { gap: 14 },
  inputShell: { alignItems: 'center', borderRadius: 18, borderWidth: 1, flexDirection: 'row', gap: 10, minHeight: 56, paddingHorizontal: 15 },
  input: { flex: 1, fontSize: 15, fontWeight: '700' },
  primaryButton: { marginTop: 4 },
  loader: { marginTop: -4 },
  links: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginTop: 2 },
  linkPrimary: { fontSize: 14, fontWeight: '900' },
  linkMuted: { fontSize: 13, fontWeight: '800' },
});
