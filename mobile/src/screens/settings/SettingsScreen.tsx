import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, FilterChip, GlassCard, KeyValueRow, ScreenError, SectionHeader, StatusPill } from '../../components/GlassKit';
import PasswordStrengthBar from '../../components/PasswordStrengthBar';
import { useTheme, Theme } from '../../context/ThemeContext';
import { useAuthStore } from '../../store/authStore';
import { useTenantStore } from '../../store/tenantStore';
import apiService from '../../services/api';
import { User } from '../../types';

const THEME_OPTIONS: Array<{ label: string; value: Theme }> = [
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
  { label: 'System', value: 'system' },
];

const TABS = ['General', 'Team', 'Security'] as const;
type TabType = typeof TABS[number];

export default function SettingsScreen() {
  const { colors, theme, effectiveTheme, setTheme } = useTheme();
  const { user, logout, updateUser } = useAuthStore();
  const { tenant, fetchTenant, updateTenant } = useTenantStore();

  const [activeTab, setActiveTab] = useState<TabType>('General');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Team
  const [users, setUsers] = useState<User[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);

  // Tenant config
  const [tenantName, setTenantName] = useState(tenant?.name ?? '');
  const [scoreThreshold, setScoreThreshold] = useState(tenant?.score_threshold ?? 50);
  const [requiresApproval, setRequiresApproval] = useState(tenant?.requires_approval ?? false);
  const [autoSend, setAutoSend] = useState(tenant?.auto_send ?? false);
  const [savingTenant, setSavingTenant] = useState(false);

  // Security
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [savingPwd, setSavingPwd] = useState(false);

  const load = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const [me, userList] = await Promise.all([
        apiService.getCurrentUser(),
        apiService.listUsers().catch(() => [] as User[]),
      ]);
      updateUser(me);
      setUsers(userList);
      await fetchTenant();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, [updateUser, fetchTenant]);

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    if (tenant) {
      setTenantName(tenant.name);
      setScoreThreshold(tenant.score_threshold);
      setRequiresApproval(tenant.requires_approval);
      setAutoSend(tenant.auto_send);
    }
  }, [tenant]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load(false);
    setRefreshing(false);
  };

  async function handleSaveTenant() {
    setSavingTenant(true);
    try {
      await updateTenant({
        name: tenantName.trim() || undefined,
        score_threshold: scoreThreshold,
        requires_approval: requiresApproval,
        auto_send: autoSend,
      });
      Alert.alert('Saved', 'Workspace settings updated');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to save');
    } finally {
      setSavingTenant(false);
    }
  }

  async function handleInvite() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const newUser = await apiService.inviteUser(inviteEmail.trim(), inviteRole);
      setUsers((u) => [...u, newUser]);
      setInviteEmail('');
      Alert.alert('Invited', `Invitation sent to ${inviteEmail}`);
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Invite failed');
    } finally {
      setInviting(false);
    }
  }

  async function handleRemoveUser(userId: string, email: string) {
    Alert.alert('Remove user', `Remove ${email} from the workspace?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.removeUser(userId);
            setUsers((u) => u.filter((usr) => usr.id !== userId));
          } catch (e: any) {
            Alert.alert('Error', e.response?.data?.detail || 'Failed to remove user');
          }
        },
      },
    ]);
  }

  async function handleChangeRole(userId: string, role: string) {
    try {
      const updated = await apiService.changeUserRole(userId, role);
      setUsers((u) => u.map((usr) => (usr.id === userId ? updated : usr)));
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to change role');
    }
  }

  async function handleChangePassword() {
    if (!currentPwd || !newPwd || newPwd !== confirmPwd) {
      Alert.alert('Error', 'Check all fields and make sure passwords match');
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
      Alert.alert('Success', 'Password changed');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to change password');
    } finally {
      setSavingPwd(false);
    }
  }

  function handleLogout() {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Logout', style: 'destructive', onPress: () => void logout() },
    ]);
  }

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
        </View>
      </SVGBackground>
    );
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          <View style={styles.header}>
            <Text style={[styles.title, { color: colors.text }]}>Settings</Text>
            <StatusPill label={effectiveTheme} tone={effectiveTheme === 'dark' ? 'cyan' : 'mint'} />
          </View>

          {error && <ScreenError message={error} onRetry={() => void load(true)} />}

          {/* Tab Switcher */}
          <View style={styles.tabs}>
            {TABS.map((tab) => (
              <FilterChip
                key={tab}
                label={tab}
                active={activeTab === tab}
                onPress={() => setActiveTab(tab)}
              />
            ))}
          </View>

          {/* ── General Tab ── */}
          {activeTab === 'General' && (
            <>
              <SectionHeader title="Appearance" />
              <GlassCard>
                <View style={styles.themeRow}>
                  {THEME_OPTIONS.map((option) => (
                    <FilterChip
                      key={option.value}
                      label={option.label}
                      active={theme === option.value}
                      onPress={() => setTheme(option.value)}
                      icon={theme === option.value ? 'checkmark-circle-outline' : undefined}
                    />
                  ))}
                </View>
              </GlassCard>

              <SectionHeader title="Workspace" />
              <GlassCard>
                <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>ORGANIZATION NAME</Text>
                <TextInput
                  value={tenantName}
                  onChangeText={setTenantName}
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                  placeholder="Organization name"
                  placeholderTextColor={colors.textMuted}
                />
                <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>
                  SCORE THRESHOLD: {scoreThreshold}%
                </Text>
                <View style={styles.sliderRow}>
                  {[0, 25, 50, 60, 70, 80, 90].map((v) => (
                    <FilterChip
                      key={v}
                      label={`${v}%`}
                      active={scoreThreshold === v}
                      onPress={() => setScoreThreshold(v)}
                    />
                  ))}
                </View>
                <View style={[styles.switchRow, { borderTopColor: colors.border }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.switchLabel, { color: colors.text }]}>Requires Approval</Text>
                    <Text style={[styles.switchHint, { color: colors.textMuted }]}>Disable auto-send and queue for review</Text>
                  </View>
                  <Switch
                    value={requiresApproval}
                    onValueChange={(v) => { setRequiresApproval(v); if (v) setAutoSend(false); }}
                    trackColor={{ false: colors.border, true: colors.primary }}
                  />
                </View>
                <View style={[styles.switchRow, { borderTopColor: colors.border }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.switchLabel, { color: colors.text }]}>Auto Send</Text>
                    <Text style={[styles.switchHint, { color: colors.textMuted }]}>Automatically send after cover is generated</Text>
                  </View>
                  <Switch
                    value={autoSend}
                    onValueChange={setAutoSend}
                    disabled={requiresApproval}
                    trackColor={{ false: colors.border, true: colors.primary }}
                  />
                </View>
                <AppButton label={savingTenant ? 'Saving...' : 'Save Workspace Settings'} icon="save-outline" onPress={handleSaveTenant} loading={savingTenant} style={styles.saveBtn} />
              </GlassCard>

              <SectionHeader title="Account" />
              <GlassCard>
                <KeyValueRow label="Email" value={user?.email} />
                <KeyValueRow label="Role" value={user?.role ?? 'member'} />
                <KeyValueRow label="Plan" value={tenant?.plan ?? 'free'} />
                <AppButton label="Logout" icon="log-out-outline" variant="danger" onPress={handleLogout} style={styles.logoutBtn} />
              </GlassCard>
            </>
          )}

          {/* ── Team Tab ── */}
          {activeTab === 'Team' && (
            <>
              <SectionHeader title="Invite Member" />
              <GlassCard>
                <TextInput
                  value={inviteEmail}
                  onChangeText={setInviteEmail}
                  placeholder="Email address"
                  placeholderTextColor={colors.textMuted}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <View style={styles.roleRow}>
                  {['member', 'admin'].map((r) => (
                    <FilterChip key={r} label={r} active={inviteRole === r} onPress={() => setInviteRole(r)} />
                  ))}
                </View>
                <AppButton label={inviting ? 'Inviting...' : 'Send Invite'} icon="mail-outline" onPress={handleInvite} loading={inviting} disabled={!inviteEmail.trim()} style={styles.saveBtn} />
              </GlassCard>

              <SectionHeader title={`Members (${users.length})`} />
              <GlassCard padded={false}>
                {users.map((u, i) => (
                  <View
                    key={u.id}
                    style={[styles.userRow, { borderBottomColor: colors.border, borderBottomWidth: i < users.length - 1 ? StyleSheet.hairlineWidth : 0 }]}
                  >
                    <View style={[styles.userAvatar, { backgroundColor: colors.primarySoft }]}>
                      <Text style={[styles.userAvatarText, { color: colors.primary }]}>{(u.email?.[0] ?? '?').toUpperCase()}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.userEmail, { color: colors.text }]} numberOfLines={1}>{u.email}</Text>
                      <StatusPill label={u.role ?? 'member'} tone={u.role === 'owner' ? 'mint' : u.role === 'admin' ? 'cyan' : 'neutral'} compact />
                    </View>
                    {u.id !== user?.id && u.role !== 'owner' && user?.role === 'owner' && (
                      <AppButton
                        label="Remove"
                        icon="trash-outline"
                        variant="danger"
                        onPress={() => handleRemoveUser(u.id, u.email)}
                        style={styles.removeBtn}
                      />
                    )}
                  </View>
                ))}
              </GlassCard>
            </>
          )}

          {/* ── Security Tab ── */}
          {activeTab === 'Security' && (
            <>
              <SectionHeader title="Change Password" />
              <GlassCard>
                <TextInput
                  value={currentPwd}
                  onChangeText={setCurrentPwd}
                  secureTextEntry
                  placeholder="Current password"
                  placeholderTextColor={colors.textMuted}
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <TextInput
                  value={newPwd}
                  onChangeText={setNewPwd}
                  secureTextEntry
                  placeholder="New password"
                  placeholderTextColor={colors.textMuted}
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <PasswordStrengthBar password={newPwd} />
                <TextInput
                  value={confirmPwd}
                  onChangeText={setConfirmPwd}
                  secureTextEntry
                  placeholder="Confirm new password"
                  placeholderTextColor={colors.textMuted}
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input, marginTop: 12 }]}
                />
                {confirmPwd.length > 0 && newPwd !== confirmPwd && (
                  <Text style={[styles.mismatch, { color: colors.error }]}>Passwords do not match</Text>
                )}
                <AppButton
                  label={savingPwd ? 'Saving...' : 'Change Password'}
                  icon="lock-closed-outline"
                  onPress={handleChangePassword}
                  loading={savingPwd}
                  disabled={!currentPwd || !newPwd || newPwd !== confirmPwd}
                  style={styles.saveBtn}
                />
              </GlassCard>
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  content: { padding: 20, paddingBottom: 118 },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 20, paddingTop: 10 },
  title: { fontSize: 30, fontWeight: '900' },
  tabs: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 },
  themeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  fieldLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8, marginTop: 4 },
  input: { borderRadius: 17, borderWidth: 1, fontSize: 14, fontWeight: '700', marginBottom: 12, paddingHorizontal: 14, paddingVertical: 13 },
  sliderRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 },
  switchRow: { alignItems: 'center', borderTopWidth: StyleSheet.hairlineWidth, flexDirection: 'row', gap: 12, paddingVertical: 14 },
  switchLabel: { fontSize: 14, fontWeight: '700' },
  switchHint: { fontSize: 12, fontWeight: '500', marginTop: 2 },
  saveBtn: { marginTop: 4 },
  logoutBtn: { marginTop: 16 },
  roleRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  userRow: { alignItems: 'center', flexDirection: 'row', gap: 12, paddingHorizontal: 16, paddingVertical: 14 },
  userAvatar: { alignItems: 'center', borderRadius: 18, height: 36, justifyContent: 'center', width: 36 },
  userAvatarText: { fontSize: 14, fontWeight: '900' },
  userEmail: { fontSize: 13, fontWeight: '700', marginBottom: 4 },
  removeBtn: { minHeight: 36, minWidth: 80 },
  mismatch: { fontSize: 12, fontWeight: '600', marginBottom: 8 },
});
