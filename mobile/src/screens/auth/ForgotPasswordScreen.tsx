import React, { useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import apiService from '../../services/api';

export default function ForgotPasswordScreen() {
  const { colors } = useTheme();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSend() {
    if (!email.trim()) {
      Alert.alert('Error', 'Please enter your email address');
      return;
    }
    setLoading(true);
    try {
      await apiService.forgotPassword(email.trim());
      setSent(true);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to send reset email');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SVGBackground>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.content}>
          <GlassCard style={styles.card}>
            <View style={[styles.iconPlate, { backgroundColor: sent ? colors.success + '22' : colors.primarySoft, borderColor: colors.border }]}>
              <Ionicons name={sent ? 'mail-open-outline' : 'key-outline'} size={34} color={sent ? colors.success : colors.primary} />
            </View>
            {sent ? (
              <>
                <Text style={[styles.title, { color: colors.text }]}>Check your email</Text>
                <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                  We sent a password reset link to <Text style={{ color: colors.primary }}>{email}</Text>.
                </Text>
                <Text style={[styles.hint, { color: colors.textMuted }]}>Check spam if it does not arrive in a few minutes.</Text>
              </>
            ) : (
              <>
                <Text style={[styles.title, { color: colors.text }]}>Reset Password</Text>
                <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Enter your email and we will send a secure reset link.</Text>

                <View style={[styles.inputShell, { backgroundColor: colors.input, borderColor: colors.border }]}>
                  <Ionicons name="mail-outline" size={18} color={colors.textMuted} />
                  <TextInput
                    style={[styles.input, { color: colors.text }]}
                    placeholder="Email address"
                    placeholderTextColor={colors.textMuted}
                    value={email}
                    onChangeText={setEmail}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                </View>

                <AppButton
                  label={loading ? 'Sending' : 'Send Reset Link'}
                  icon="send-outline"
                  onPress={handleSend}
                  loading={loading}
                  style={styles.button}
                />
              </>
            )}
          </GlassCard>
        </View>
      </KeyboardAvoidingView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: 22 },
  card: { alignItems: 'center', padding: 26 },
  iconPlate: { alignItems: 'center', borderRadius: 24, borderWidth: 1, height: 70, justifyContent: 'center', marginBottom: 18, width: 70 },
  title: { fontSize: 28, fontWeight: '900', marginBottom: 8, textAlign: 'center' },
  subtitle: { fontSize: 15, fontWeight: '700', lineHeight: 22, marginBottom: 18, textAlign: 'center' },
  hint: { fontSize: 13, fontWeight: '700', lineHeight: 19, marginTop: 4, textAlign: 'center' },
  inputShell: { alignItems: 'center', alignSelf: 'stretch', borderRadius: 18, borderWidth: 1, flexDirection: 'row', gap: 10, minHeight: 56, paddingHorizontal: 15 },
  input: { flex: 1, fontSize: 15, fontWeight: '700' },
  button: { alignSelf: 'stretch', marginTop: 14 },
});
