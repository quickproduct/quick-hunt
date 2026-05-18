import React, { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuthStore } from '../../store/authStore';
import { AuthStackParamList } from '../../navigation/AppNavigator';
import { useTheme } from '../../context/ThemeContext';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard } from '../../components/GlassKit';

export default function RegisterScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<AuthStackParamList, 'Register'>>();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const { register, isLoading } = useAuthStore();
  const { colors } = useTheme();

  const handleRegister = async () => {
    if (!name.trim() || !email.trim() || !password.trim() || !confirmPassword.trim()) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }

    if (password !== confirmPassword) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }

    try {
      await register(name.trim(), email.trim(), password.trim());
    } catch (error: any) {
      Alert.alert('Registration Failed', error.response?.data?.detail || 'Registration failed');
    }
  };

  return (
    <SVGBackground>
      <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
          <View style={styles.hero}>
            <View style={[styles.logo, { backgroundColor: colors.primarySoft, borderColor: colors.border }]}>
              <Ionicons name="rocket-outline" size={30} color={colors.primary} />
            </View>
            <Text style={[styles.title, { color: colors.text }]}>Create Account</Text>
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Set up your workspace and start building an application pipeline.</Text>
          </View>

          <GlassCard style={styles.card}>
            <AuthInput icon="business-outline" placeholder="Workspace or tenant name" value={name} onChangeText={setName} autoCapitalize="words" />
            <AuthInput icon="mail-outline" placeholder="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} />
            <AuthInput
              icon="lock-closed-outline"
              placeholder="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              right={<Pressable onPress={() => setShowPassword(!showPassword)} hitSlop={10}><Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={19} color={colors.textSecondary} /></Pressable>}
            />
            <AuthInput icon="shield-checkmark-outline" placeholder="Confirm Password" value={confirmPassword} onChangeText={setConfirmPassword} secureTextEntry />

            <AppButton
              label={isLoading ? 'Creating account' : 'Sign Up'}
              icon="arrow-forward-outline"
              onPress={handleRegister}
              disabled={isLoading}
              style={styles.primaryButton}
            />

            <Pressable style={styles.linkButton} onPress={() => navigation.navigate('Login')} hitSlop={8}>
              <Text style={[styles.linkText, { color: colors.primary }]}>Already have an account? Sign in</Text>
            </Pressable>
          </GlassCard>
        </ScrollView>
      </KeyboardAvoidingView>
    </SVGBackground>
  );
}

function AuthInput({
  icon,
  right,
  ...props
}: React.ComponentProps<typeof TextInput> & { icon: keyof typeof Ionicons.glyphMap; right?: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.inputShell, { backgroundColor: colors.input, borderColor: colors.border }]}>
      <Ionicons name={icon} size={18} color={colors.textMuted} />
      <TextInput
        {...props}
        placeholderTextColor={colors.textMuted}
        style={[styles.input, { color: colors.text }, props.style]}
      />
      {right}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: 22, paddingVertical: 32 },
  hero: { alignItems: 'center', marginBottom: 22, paddingTop: 12 },
  logo: { alignItems: 'center', borderRadius: 24, borderWidth: 1, height: 68, justifyContent: 'center', marginBottom: 18, width: 68 },
  title: { fontSize: 32, fontWeight: '900', letterSpacing: 0, marginBottom: 8, textAlign: 'center' },
  subtitle: { fontSize: 15, fontWeight: '700', lineHeight: 22, maxWidth: 290, textAlign: 'center' },
  card: { gap: 13 },
  inputShell: { alignItems: 'center', borderRadius: 18, borderWidth: 1, flexDirection: 'row', gap: 10, minHeight: 56, paddingHorizontal: 15 },
  input: { flex: 1, fontSize: 15, fontWeight: '700' },
  primaryButton: { marginTop: 4 },
  linkButton: { alignItems: 'center', marginTop: 2 },
  linkText: { fontSize: 14, fontWeight: '900' },
});
