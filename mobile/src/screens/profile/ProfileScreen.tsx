import React, { useState } from 'react';
import {
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard, KeyValueRow, SectionHeader, StatusPill } from '../../components/GlassKit';
import PasswordStrengthBar from '../../components/PasswordStrengthBar';
import { useTheme } from '../../context/ThemeContext';
import { useAuthStore } from '../../store/authStore';
import apiService from '../../services/api';

export default function ProfileScreen() {
  const { colors } = useTheme();
  const { user, updateUser } = useAuthStore();

  const [newEmail, setNewEmail] = useState(user?.email ?? '');
  const [savingEmail, setSavingEmail] = useState(false);

  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [savingPwd, setSavingPwd] = useState(false);
  const [showCurrentPwd, setShowCurrentPwd] = useState(false);
  const [showNewPwd, setShowNewPwd] = useState(false);

  const [refreshing, setRefreshing] = useState(false);

  async function onRefresh() {
    setRefreshing(true);
    try {
      const me = await apiService.getCurrentUser();
      updateUser(me);
      setNewEmail(me.email);
    } finally {
      setRefreshing(false);
    }
  }

  async function handleSaveEmail() {
    if (!newEmail.trim()) return;
    setSavingEmail(true);
    try {
      const updated = await apiService.updateProfile({ email: newEmail.trim() });
      updateUser(updated);
      Alert.alert('Saved', 'Email updated successfully');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to update email');
    } finally {
      setSavingEmail(false);
    }
  }

  async function handleChangePassword() {
    if (!currentPwd || !newPwd) {
      Alert.alert('Error', 'Fill in all password fields');
      return;
    }
    if (newPwd !== confirmPwd) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }
    if (newPwd.length < 8) {
      Alert.alert('Error', 'New password must be at least 8 characters');
      return;
    }
    setSavingPwd(true);
    try {
      await apiService.updateProfile({ current_password: currentPwd, new_password: newPwd });
      setCurrentPwd('');
      setNewPwd('');
      setConfirmPwd('');
      Alert.alert('Success', 'Password changed successfully');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to change password');
    } finally {
      setSavingPwd(false);
    }
  }

  const memberSince = user?.created_at
    ? new Date(user.created_at).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    : 'Unknown';

  const roleColor =
    user?.role === 'owner' ? 'mint' : user?.role === 'admin' ? 'cyan' : 'neutral';

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          {/* Profile header */}
          <View style={styles.header}>
            <View style={[styles.avatar, { backgroundColor: colors.primary }]}>
              <Text style={[styles.avatarText, { color: colors.primaryText }]}>
                {(user?.email?.[0] ?? 'U').toUpperCase()}
              </Text>
            </View>
            <Text style={[styles.email, { color: colors.text }]}>{user?.email}</Text>
            <View style={styles.badges}>
              <StatusPill label={user?.role ?? 'member'} tone={roleColor} />
              {user?.is_verified && <StatusPill label="Verified" tone="mint" />}
            </View>
            <Text style={[styles.since, { color: colors.textMuted }]}>Member since {memberSince}</Text>
          </View>

          {/* Account info */}
          <SectionHeader title="Account Information" />
          <GlassCard>
            <KeyValueRow label="Email" value={user?.email} />
            <KeyValueRow label="Role" value={user?.role ?? 'member'} />
            <KeyValueRow label="Tenant ID" value={user?.tenant_id} />
            <KeyValueRow label="Verified" value={user?.is_verified ? 'Yes' : 'No'} />
          </GlassCard>

          {/* Edit email */}
          <SectionHeader title="Update Email" />
          <GlassCard>
            <TextInput
              value={newEmail}
              onChangeText={setNewEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
              placeholder="New email address"
              placeholderTextColor={colors.textMuted}
            />
            <AppButton
              label="Save Email"
              icon="save-outline"
              onPress={handleSaveEmail}
              loading={savingEmail}
              disabled={newEmail.trim() === user?.email}
              style={styles.saveBtn}
            />
          </GlassCard>

          {/* Change password */}
          <SectionHeader title="Change Password" />
          <GlassCard>
            <View style={styles.pwdRow}>
              <TextInput
                value={currentPwd}
                onChangeText={setCurrentPwd}
                secureTextEntry={!showCurrentPwd}
                style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                placeholder="Current password"
                placeholderTextColor={colors.textMuted}
              />
            </View>
            <View style={styles.pwdRow}>
              <TextInput
                value={newPwd}
                onChangeText={setNewPwd}
                secureTextEntry={!showNewPwd}
                style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                placeholder="New password"
                placeholderTextColor={colors.textMuted}
              />
            </View>
            <PasswordStrengthBar password={newPwd} />
            <TextInput
              value={confirmPwd}
              onChangeText={setConfirmPwd}
              secureTextEntry
              style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input, marginTop: 12 }]}
              placeholder="Confirm new password"
              placeholderTextColor={colors.textMuted}
            />
            {confirmPwd.length > 0 && newPwd !== confirmPwd && (
              <Text style={[styles.noMatch, { color: colors.error }]}>Passwords do not match</Text>
            )}
            <AppButton
              label="Change Password"
              icon="lock-closed-outline"
              onPress={handleChangePassword}
              loading={savingPwd}
              disabled={!currentPwd || !newPwd || newPwd !== confirmPwd}
              style={styles.saveBtn}
            />
          </GlassCard>
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  header: { alignItems: 'center', marginBottom: 28, paddingTop: 10 },
  avatar: {
    alignItems: 'center',
    borderRadius: 40,
    borderWidth: 1,
    height: 80,
    justifyContent: 'center',
    marginBottom: 12,
    width: 80,
  },
  avatarText: { fontSize: 32, fontWeight: '900' },
  email: { fontSize: 16, fontWeight: '700', marginBottom: 8 },
  badges: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  since: { fontSize: 12, fontWeight: '600' },
  input: {
    borderRadius: 17,
    borderWidth: 1,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 8,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  pwdRow: { position: 'relative' },
  saveBtn: { marginTop: 8 },
  noMatch: { fontSize: 12, fontWeight: '600', marginBottom: 8 },
});
