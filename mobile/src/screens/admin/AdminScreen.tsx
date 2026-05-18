import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { SegmentedButtons } from 'react-native-paper';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, FilterChip, GlassCard, PageHeader, SectionHeader, StatusPill } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useAdminStore } from '../../store/adminStore';
import { FeatureFlags } from '../../types';

const QUICK_ACTIONS = [
  { action: 'purge-irrelevant', label: 'Purge Irrelevant', icon: 'trash-outline' as const, destructive: true },
  { action: 'deduplicate', label: 'Deduplicate', icon: 'copy-outline' as const, destructive: false },
  { action: 'reset-email-discovery', label: 'Reset Discovery', icon: 'refresh-outline' as const, destructive: false },
  { action: 'fill-missing-covers', label: 'Fill Covers', icon: 'sparkles-outline' as const, destructive: false },
  { action: 'backfill-hr-emails', label: 'Backfill HR Emails', icon: 'mail-outline' as const, destructive: false },
  { action: 'refresh-cover-letters', label: 'Refresh Covers', icon: 'sync-outline' as const, destructive: false },
  { action: 'cleanup-old-jobs', label: 'Cleanup Old Jobs', icon: 'time-outline' as const, destructive: true },
  { action: 'fix-placeholder-emails', label: 'Fix Placeholders', icon: 'build-outline' as const, destructive: false },
  { action: 'priority-cover-emailed', label: 'Priority Pipeline', icon: 'star-outline' as const, destructive: false },
  { action: 'current-month-pipeline', label: 'Monthly Pipeline', icon: 'calendar-outline' as const, destructive: false },
];

const HEALTH_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  connected: 'checkmark-circle',
  error: 'close-circle',
  not_configured: 'remove-circle',
  unknown: 'help-circle',
};

// Collapsible section wrapper
function AdminSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <View style={sectionStyles.wrap}>
      <Pressable onPress={() => setOpen((v) => !v)} style={[sectionStyles.toggle, { borderBottomColor: colors.border }]}>
        <Text style={[sectionStyles.title, { color: colors.text }]}>{title}</Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMuted} />
      </Pressable>
      {open ? <View style={sectionStyles.body}>{children}</View> : null}
    </View>
  );
}

const sectionStyles = StyleSheet.create({
  wrap: { marginBottom: 8 },
  toggle: {
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingBottom: 10,
    paddingTop: 18,
  },
  title: { fontSize: 18, fontWeight: '700' },
  body: { marginTop: 12 },
});

export default function AdminScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<any>();
  const {
    health, queues, featureFlags, portals, cronStatus,
    fetchHealth, fetchQueues, fetchFeatureFlags, updateFeatureFlags,
    fetchPortals, togglePortal, fetchCronStatus, resetCronCircuit, releaseCronLock,
    triggerQuickAction, applyPerformanceMode,
  } = useAdminStore();

  const [refreshing, setRefreshing] = useState(false);
  const [localFlags, setLocalFlags] = useState<FeatureFlags | null>(null);
  const [savingFlags, setSavingFlags] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [logLevel, setLogLevel] = useState('error');
  const [logs, setLogs] = useState<string[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logsExpanded, setLogsExpanded] = useState(false);
  const [perfMode, setPerfMode] = useState<'turbo' | 'normal' | 'economy'>('normal');

  const loadAll = useCallback(async () => {
    await Promise.allSettled([
      fetchHealth(), fetchQueues(), fetchFeatureFlags(), fetchPortals(), fetchCronStatus(),
    ]);
  }, [fetchHealth, fetchQueues, fetchFeatureFlags, fetchPortals, fetchCronStatus]);

  useEffect(() => { void loadAll(); }, [loadAll]);
  useEffect(() => { if (featureFlags) setLocalFlags({ ...featureFlags }); }, [featureFlags]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadAll();
    setRefreshing(false);
  };

  async function handleSaveFlags() {
    if (!localFlags) return;
    setSavingFlags(true);
    try {
      await updateFeatureFlags(localFlags);
      Alert.alert('Saved', 'Feature flags updated');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to save flags');
    } finally {
      setSavingFlags(false);
    }
  }

  async function handleQuickAction(action: string, label: string, destructive: boolean) {
    const message = destructive
      ? `"${label}" is a destructive action and cannot be undone. Run it now?`
      : `Run "${label}" immediately?`;
    Alert.alert(`Run: ${label}`, message, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Run',
        style: destructive ? 'destructive' : 'default',
        onPress: async () => {
          setActionLoading(action);
          try {
            const taskId = await triggerQuickAction(action);
            Alert.alert('Queued', `Task ID: ${taskId}`);
          } catch (e: any) {
            Alert.alert('Error', e.response?.data?.detail || 'Action failed');
          } finally {
            setActionLoading('');
          }
        },
      },
    ]);
  }

  async function loadLogs() {
    setLoadingLogs(true);
    try {
      const api = (await import('../../services/api')).default;
      const result = await api.getAdminLogs(logLevel, logsExpanded ? 100 : 10);
      setLogs(Array.isArray(result) ? result : [String(result)]);
    } catch {
      setLogs(['Failed to load logs']);
    } finally {
      setLoadingLogs(false);
    }
  }

  const healthColor = (status: string) =>
    status === 'connected' ? colors.success : status === 'not_configured' ? colors.warning : colors.error;

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          <PageHeader title="Admin Panel" />

          {/* System Health */}
          <AdminSection title="System Health" defaultOpen>
            <GlassCard>
              <View style={styles.healthGrid}>
                {health && Object.entries(health).map(([key, status]) => (
                  <View key={key} style={styles.healthItem}>
                    <Ionicons name={HEALTH_ICONS[status] ?? 'help-circle'} size={22} color={healthColor(status)} />
                    <Text style={[styles.healthLabel, { color: colors.textMuted }]}>{key}</Text>
                    <StatusPill
                      label={status}
                      tone={status === 'connected' ? 'mint' : status === 'not_configured' ? 'amber' : 'coral'}
                      compact
                    />
                  </View>
                ))}
              </View>
            </GlassCard>
          </AdminSection>

          {/* Performance Mode */}
          <AdminSection title="Performance Mode" defaultOpen>
            <GlassCard>
              <SegmentedButtons
                value={perfMode}
                onValueChange={async (value) => {
                  const nextMode = value as 'turbo' | 'normal' | 'economy';
                  setPerfMode(nextMode);
                  try {
                    await applyPerformanceMode(nextMode);
                    Alert.alert('Applied', `${nextMode} mode activated`);
                  } catch (e: any) {
                    Alert.alert('Error', e.response?.data?.detail || 'Failed');
                  }
                }}
                buttons={[
                  { value: 'turbo', label: 'Turbo' },
                  { value: 'normal', label: 'Normal' },
                  { value: 'economy', label: 'Economy' },
                ]}
              />
            </GlassCard>
          </AdminSection>

          {/* Queue Monitor */}
          {queues.length > 0 && (
            <AdminSection title={`Queue Monitor (${queues.filter((q) => q.messages > 0).length} active)`} defaultOpen>
              <GlassCard padded={false}>
                <View style={[styles.tableHeader, { borderBottomColor: colors.border }]}>
                  {['Queue', 'Msgs', 'Ready', 'Workers'].map((col) => (
                    <Text key={col} style={[styles.tableHeaderCell, { color: colors.textMuted }]}>{col}</Text>
                  ))}
                </View>
                {queues.map((q, i) => (
                  <View key={q.name} style={[styles.tableRow, { borderBottomColor: colors.border, borderBottomWidth: i < queues.length - 1 ? StyleSheet.hairlineWidth : 0 }]}>
                    <Text style={[styles.tableCell, { color: colors.text }]} numberOfLines={1}>{q.name.replace('jh_', '')}</Text>
                    <Text style={[styles.tableCell, { color: q.messages > 0 ? colors.warning : colors.textMuted, fontWeight: '800' }]}>{q.messages}</Text>
                    <Text style={[styles.tableCell, { color: colors.textMuted }]}>{q.ready}</Text>
                    <Text style={[styles.tableCell, { color: colors.textMuted }]}>{q.consumers}</Text>
                  </View>
                ))}
              </GlassCard>
            </AdminSection>
          )}

          {/* Feature Flags */}
          {localFlags && (
            <AdminSection title="Feature Flags" defaultOpen={false}>
              <GlassCard>
                {[
                  { key: 'auto_send_enabled', label: 'Auto Send' },
                  { key: 'langchain_enabled', label: 'LangChain' },
                  { key: 'semantic_filter_enabled', label: 'Semantic Filter' },
                ].map(({ key, label }) => (
                  <View key={key} style={[styles.flagRow, { borderBottomColor: colors.border }]}>
                    <Text style={[styles.flagLabel, { color: colors.text }]}>{label}</Text>
                    <Switch
                      value={!!(localFlags as any)[key]}
                      onValueChange={(v) => setLocalFlags({ ...localFlags, [key]: v })}
                      trackColor={{ false: colors.border, true: colors.primary }}
                    />
                  </View>
                ))}
                <View style={[styles.flagRow, { borderBottomColor: colors.border }]}>
                  <Text style={[styles.flagLabel, { color: colors.text }]}>Score Threshold</Text>
                  <TextInput
                    value={String(localFlags.score_threshold)}
                    onChangeText={(v) => setLocalFlags({ ...localFlags, score_threshold: Number(v) || 0 })}
                    keyboardType="numeric"
                    style={[styles.flagInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                  />
                </View>
                <AppButton label={savingFlags ? 'Saving...' : 'Save Flags'} icon="save-outline" onPress={handleSaveFlags} loading={savingFlags} style={styles.saveBtn} />
              </GlassCard>
            </AdminSection>
          )}

          {/* Portal Control */}
          {portals.length > 0 && (
            <AdminSection title="Portal Control" defaultOpen={false}>
              <GlassCard>
                <View style={styles.portalGrid}>
                  {portals.map((p) => (
                    <FilterChip
                      key={p.name}
                      label={p.name}
                      active={p.enabled}
                      onPress={() => void togglePortal(p.name, !p.enabled)}
                    />
                  ))}
                </View>
              </GlassCard>
            </AdminSection>
          )}

          {/* Backend Logs */}
          <AdminSection title="Backend Logs" defaultOpen={false}>
            <GlassCard>
              <View style={styles.logTabRow}>
                {['critical', 'error', 'warning'].map((level) => (
                  <FilterChip key={level} label={level} active={logLevel === level} onPress={() => setLogLevel(level)} />
                ))}
              </View>
              <View style={styles.logBtnRow}>
                <AppButton
                  label={loadingLogs ? 'Loading...' : 'Load Logs'}
                  icon="terminal-outline"
                  variant="secondary"
                  onPress={loadLogs}
                  loading={loadingLogs}
                  style={styles.logBtn}
                />
                {logs.length > 0 && (
                  <AppButton
                    label={logsExpanded ? 'Collapse' : 'Load All'}
                    icon={logsExpanded ? 'contract-outline' : 'expand-outline'}
                    variant="secondary"
                    onPress={() => { setLogsExpanded((v) => !v); void loadLogs(); }}
                    style={styles.logBtn}
                  />
                )}
              </View>
              {logs.length > 0 && (
                <View style={[styles.logBox, { backgroundColor: colors.surfaceStrong }]}>
                  {logs.map((line, i) => {
                    try {
                      const parsed = JSON.parse(line);
                      const level: string = parsed.level ?? parsed.severity ?? '';
                      const event: string = parsed.event ?? parsed.message ?? parsed.msg ?? '';
                      const ts: string = parsed.timestamp ?? parsed.time ?? '';
                      const taskId: string = parsed.task_id ?? '';
                      const jobId: string = parsed.job_id ?? '';
                      const levelColor =
                        level.toUpperCase() === 'CRITICAL' || level.toUpperCase() === 'ERROR' ? colors.error
                        : level.toUpperCase() === 'WARNING' || level.toUpperCase() === 'WARN' ? colors.warning
                        : colors.textMuted;
                      return (
                        <View key={i} style={[styles.parsedLogRow, { borderBottomColor: colors.border }]}>
                          <Text style={[styles.parsedLogLevel, { color: levelColor }]}>{level.toUpperCase().slice(0, 4) || '?'}</Text>
                          <View style={{ flex: 1 }}>
                            <Text style={[styles.parsedLogEvent, { color: colors.text }]} numberOfLines={3}>{event}</Text>
                            {(ts || taskId || jobId) ? (
                              <Text style={[styles.parsedLogMeta, { color: colors.textMuted }]}>
                                {[ts?.slice(11, 19), taskId && `task:${taskId.slice(0, 8)}`, jobId && `job:${jobId.slice(0, 8)}`].filter(Boolean).join(' · ')}
                              </Text>
                            ) : null}
                          </View>
                        </View>
                      );
                    } catch {
                      return <Text key={i} style={[styles.logLine, { color: colors.textSecondary }]}>{line}</Text>;
                    }
                  })}
                </View>
              )}
            </GlassCard>
          </AdminSection>

          {/* Cron Tasks */}
          {cronStatus.length > 0 && (
            <AdminSection title="Cron Tasks" defaultOpen={false}>
              <GlassCard padded={false}>
                {cronStatus.map((task, i) => (
                  <View key={task.task_name} style={[styles.cronRow, { borderBottomColor: colors.border, borderBottomWidth: i < cronStatus.length - 1 ? StyleSheet.hairlineWidth : 0 }]}>
                    <View style={styles.cronHeader}>
                      <Text style={[styles.cronName, { color: colors.text }]}>{task.task_name}</Text>
                      <StatusPill
                        label={task.circuit_state}
                        tone={task.circuit_state === 'closed' ? 'mint' : task.circuit_state === 'open' ? 'coral' : 'amber'}
                        compact
                      />
                    </View>
                    <Text style={[styles.cronMeta, { color: colors.textMuted }]}>
                      Lock: {task.lock_held ? 'held' : 'free'} · Failures: {task.failures}
                    </Text>
                    <View style={styles.cronActions}>
                      <AppButton
                        label="Reset Circuit"
                        icon="refresh-outline"
                        variant="secondary"
                        onPress={() => void resetCronCircuit(task.task_name)}
                        style={styles.cronBtn}
                      />
                      <AppButton
                        label="Release Lock"
                        icon="lock-open-outline"
                        variant="secondary"
                        onPress={() => void releaseCronLock(task.task_name)}
                        style={styles.cronBtn}
                      />
                    </View>
                  </View>
                ))}
              </GlassCard>
              <AppButton
                label="Open Cron Monitor"
                icon="pulse-outline"
                variant="secondary"
                onPress={() => navigation.navigate('CronMonitor')}
                style={styles.cronMonitorBtn}
              />
            </AdminSection>
          )}

          {/* Quick Actions */}
          <AdminSection title="Quick Actions" defaultOpen={false}>
            <View style={styles.quickGrid}>
              {QUICK_ACTIONS.map((item) => (
                <AppButton
                  key={item.action}
                  label={item.label}
                  icon={item.icon}
                  variant={item.destructive ? 'danger' : 'secondary'}
                  loading={actionLoading === item.action}
                  onPress={() => void handleQuickAction(item.action, item.label, item.destructive)}
                  style={styles.quickBtn}
                />
              ))}
            </View>
          </AdminSection>

          {/* Device Logs */}
          <AdminSection title="Device Logs" defaultOpen={false}>
            <GlassCard>
              <AppButton
                label="View Device Logs"
                icon="terminal-outline"
                variant="secondary"
                onPress={() => navigation.navigate('DeviceLogs')}
              />
            </GlassCard>
          </AdminSection>

          {/* API Quotas */}
          <AdminSection title="API Quotas" defaultOpen={false}>
            <GlassCard>
              <AppButton
                label="View API Quotas"
                icon="speedometer-outline"
                variant="secondary"
                onPress={() => navigation.navigate('AdminQuota')}
              />
            </GlassCard>
          </AdminSection>
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  pageTitle: { fontSize: 28, fontWeight: '900', marginTop: 10, marginBottom: 4 },
  healthGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  healthItem: { alignItems: 'center', gap: 6, minWidth: '44%' },
  healthLabel: { fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  tableHeader: { borderBottomWidth: StyleSheet.hairlineWidth, flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 8 },
  tableHeaderCell: { flex: 1, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  tableRow: { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 10 },
  tableCell: { flex: 1, fontSize: 12, fontWeight: '600' },
  flagRow: { alignItems: 'center', borderBottomWidth: StyleSheet.hairlineWidth, flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12 },
  flagLabel: { fontSize: 14, fontWeight: '700' },
  flagInput: { borderRadius: 14, borderWidth: 1, fontSize: 14, fontWeight: '800', paddingHorizontal: 10, paddingVertical: 8, width: 64, textAlign: 'center' },
  saveBtn: { marginTop: 12 },
  portalGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  logTabRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  logBtnRow: { flexDirection: 'row', gap: 8 },
  logBtn: { flex: 1 },
  logBox: { borderRadius: 18, marginTop: 12, padding: 6 },
  logLine: { fontFamily: 'monospace', fontSize: 11, lineHeight: 18, paddingHorizontal: 4 },
  parsedLogRow: { alignItems: 'flex-start', borderBottomWidth: StyleSheet.hairlineWidth, flexDirection: 'row', gap: 8, paddingHorizontal: 4, paddingVertical: 8 },
  parsedLogLevel: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5, paddingTop: 2, width: 34 },
  parsedLogEvent: { fontSize: 12, fontWeight: '700', lineHeight: 17 },
  parsedLogMeta: { fontSize: 10, fontWeight: '600', marginTop: 2 },
  cronRow: { paddingHorizontal: 16, paddingVertical: 14 },
  cronHeader: { alignItems: 'center', flexDirection: 'row', gap: 10, justifyContent: 'space-between', marginBottom: 6 },
  cronName: { flex: 1, fontSize: 13, fontWeight: '800' },
  cronMeta: { fontSize: 11, fontWeight: '600', marginBottom: 10 },
  cronActions: { flexDirection: 'row', gap: 8 },
  cronBtn: { flex: 1, minHeight: 40 },
  cronMonitorBtn: { marginTop: 12 },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  quickBtn: { minHeight: 52, minWidth: '47%', flex: 1 },
});
