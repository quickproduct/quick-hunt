import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Clipboard,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  ToastAndroid,
  TouchableOpacity,
  View,
  Platform,
  Alert,
} from 'react-native';
import { RouteProp, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import { EmptyState, GlassCard, KeyValueRow, ScreenError, SectionHeader, StatusPill } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { MoreStackParamList } from '../../navigation/AppNavigator';
import apiService from '../../services/api';
import { CronRunDetail } from '../../types';
import { formatDateTime, formatRelative } from '../../utils/format';

type RouteT = RouteProp<MoreStackParamList, 'CronRunDetail'>;

function fmtDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

const STATUS_TONE: Record<string, 'mint' | 'cyan' | 'coral' | 'amber' | 'neutral'> = {
  success: 'mint',
  running: 'cyan',
  failure: 'coral',
  timeout: 'amber',
  skipped: 'neutral',
};

function copyToClipboard(value: string) {
  Clipboard.setString(value);
  if (Platform.OS === 'android') {
    ToastAndroid.show('Copied!', ToastAndroid.SHORT);
  } else {
    Alert.alert('Copied', value.slice(0, 60));
  }
}

export default function CronRunDetailScreen() {
  const route = useRoute<RouteT>();
  const { colors } = useTheme();
  const { runId } = route.params;

  const [run, setRun] = useState<CronRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const data = await apiService.getCronRun(runId);
      setRun(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to load run details');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [runId]);

  useEffect(() => { load(true); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(false); };

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={[styles.centerText, { color: colors.textMuted }]}>Loading run details...</Text>
        </View>
      </SVGBackground>
    );
  }

  if (error) {
    return (
      <SVGBackground>
        <SafeAreaView style={styles.safeArea} edges={['top']}>
          <ScreenError message={error} onRetry={() => load(true)} />
        </SafeAreaView>
      </SVGBackground>
    );
  }

  if (!run) {
    return (
      <SVGBackground>
        <SafeAreaView style={styles.safeArea} edges={['top']}>
          <EmptyState title="Run not found" message="This cron run may have been cleaned up." icon="time-outline" />
        </SafeAreaView>
      </SVGBackground>
    );
  }

  const errorCount = run.steps.filter((s) => !s.ok).length;
  const tone = STATUS_TONE[run.status] ?? 'neutral';

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          {/* Header */}
          <View style={styles.header}>
            <Text style={[styles.taskName, { color: colors.textMuted }]}>{run.task_name}</Text>
            <View style={styles.headerRow}>
              <StatusPill label={run.status} tone={tone} />
              <Text style={[styles.relTime, { color: colors.textMuted }]}>{formatRelative(run.started_at)}</Text>
            </View>
          </View>

          {/* KPI strip */}
          <View style={styles.kpiRow}>
            <KpiCard label="Duration" value={fmtDuration(run.duration_ms)} color={colors.primary} />
            <KpiCard label="Steps" value={String(run.steps.length)} color={colors.text as string} />
            <KpiCard label="Errors" value={String(errorCount)} color={errorCount > 0 ? colors.error : colors.success} />
          </View>

          {/* Steps */}
          {run.steps.length > 0 && (
            <>
              <SectionHeader title="Steps" />
              <GlassCard padded={false}>
                {run.steps.map((step, i) => (
                  <View
                    key={`${step.label}-${i}`}
                    style={[
                      styles.stepRow,
                      { borderBottomColor: colors.border, borderBottomWidth: i < run.steps.length - 1 ? StyleSheet.hairlineWidth : 0 },
                    ]}
                  >
                    <View style={[styles.stepDot, { backgroundColor: step.ok ? colors.success : colors.error }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.stepLabel, { color: colors.text }]}>{step.label}</Text>
                      <Text style={[styles.stepMeta, { color: colors.textMuted }]}>
                        {formatDateTime(step.started_at)}
                        {step.ended_at && step.started_at
                          ? ` · ${fmtDuration(new Date(step.ended_at).getTime() - new Date(step.started_at).getTime())}`
                          : ''}
                      </Text>
                    </View>
                    <Ionicons
                      name={step.ok ? 'checkmark-circle' : 'close-circle'}
                      size={18}
                      color={step.ok ? colors.success : colors.error}
                    />
                  </View>
                ))}
              </GlassCard>
            </>
          )}

          {/* Error detail */}
          {(run.error_summary || run.error_traceback) && (
            <>
              <SectionHeader title="Error" />
              <GlassCard style={[styles.errorCard, { borderColor: colors.error, backgroundColor: colors.error + '12' }]}>
                {run.error_summary && (
                  <Text style={[styles.errorSummary, { color: colors.error }]}>{run.error_summary}</Text>
                )}
                {run.error_traceback && (
                  <Text style={[styles.traceback, { color: colors.textSecondary }]}>{run.error_traceback}</Text>
                )}
              </GlassCard>
            </>
          )}

          {/* Metadata */}
          <SectionHeader title="Metadata" />
          <GlassCard>
            <KeyValueRow label="Status" value={run.status} />
            <KeyValueRow label="Triggered By" value={run.triggered_by} />
            <KeyValueRow label="Started" value={formatDateTime(run.started_at)} />
            <KeyValueRow label="Ended" value={formatDateTime(run.ended_at)} />
            <KeyValueRow label="Worker" value={run.worker_host} />
            <TouchableOpacity onPress={() => copyToClipboard(run.id)} style={styles.copyRow}>
              <Text style={[styles.copyLabel, { color: colors.textMuted }]}>RUN ID</Text>
              <Text style={[styles.copyValue, { color: colors.text }]} numberOfLines={1}>{run.id}</Text>
              <Ionicons name="copy-outline" size={14} color={colors.textMuted} />
            </TouchableOpacity>
          </GlassCard>
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

function KpiCard({ label, value, color }: { label: string; value: string; color: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.kpiCard, { backgroundColor: colors.glass, borderColor: colors.border }]}>
      <Text style={[styles.kpiValue, { color }]}>{value}</Text>
      <Text style={[styles.kpiLabel, { color: colors.textMuted }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerText: { fontSize: 14, fontWeight: '700', marginTop: 14 },
  content: { padding: 20, paddingBottom: 120 },
  header: { marginBottom: 20, paddingTop: 10 },
  taskName: { fontSize: 13, fontWeight: '800', marginBottom: 8 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  relTime: { fontSize: 13, fontWeight: '600' },
  kpiRow: { flexDirection: 'row', gap: 10, marginBottom: 4 },
  kpiCard: { flex: 1, borderRadius: 18, borderWidth: 1, padding: 12, alignItems: 'center' },
  kpiValue: { fontSize: 22, fontWeight: '900', marginBottom: 2 },
  kpiLabel: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12 },
  stepDot: { width: 10, height: 10, borderRadius: 5, marginTop: 2 },
  stepLabel: { fontSize: 13, fontWeight: '700', marginBottom: 2 },
  stepMeta: { fontSize: 11, fontWeight: '600' },
  errorCard: { borderWidth: 1 },
  errorSummary: { fontSize: 14, fontWeight: '700', marginBottom: 8 },
  traceback: { fontFamily: 'monospace', fontSize: 11, lineHeight: 16 },
  copyRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8 },
  copyLabel: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase', width: 60 },
  copyValue: { flex: 1, fontSize: 11, fontWeight: '600' },
});
