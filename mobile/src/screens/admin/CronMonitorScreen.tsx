import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  Pressable,
  RefreshControl,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTheme } from '../../context/ThemeContext';
import { MoreStackParamList } from '../../navigation/AppNavigator';
import { CronRunSummary } from '../../types';
import { apiService } from '../../services/api';
import AccordionRow from '../../components/AccordionRow';
import SVGBackground from '../../components/SVGBackground';
import { GlassCard } from '../../components/GlassKit';

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

function fmtRelative(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const STATUS_COLOR: Record<string, string> = {
  running: '#3B82F6',
  success: '#10B981',
  failure: '#EF4444',
  timeout: '#F97316',
  skipped: '#9CA3AF',
};

// ── Task groups ────────────────────────────────────────────────────────────────

const TASK_GROUPS: Record<string, string[]> = {
  Scraping: ['scheduled_scrape'],
  'AI / Cover Letters': [
    'fill_missing_covers_task',
    'refresh_cover_letters_task',
    'priority_cover_for_emailed_jobs_task',
    'check_cover_letter_status_task',
  ],
  'HR Email': [
    'backfill_hr_emails_task',
    'cover_ready_hr_fetch_task',
    'fix_placeholder_emails_task',
    'current_month_pipeline_task',
  ],
  Maintenance: [
    'deduplicate_jobs_task',
    'cleanup_old_jobs_task',
  ],
};

// ── Run row ───────────────────────────────────────────────────────────────────

function RunRow({
  run,
  onPress,
  colors,
}: {
  run: CronRunSummary;
  onPress: () => void;
  colors: ReturnType<typeof useTheme>['colors'];
}) {
  const dot = STATUS_COLOR[run.status] ?? '#9CA3AF';
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.runRow, { borderColor: colors.border, opacity: pressed ? 0.78 : 1 }]}>
      <View style={[styles.statusDot, { backgroundColor: dot }]} />
      <View style={{ flex: 1 }}>
        <Text style={[styles.taskName, { color: colors.text }]} numberOfLines={1}>
          {run.task_name}
        </Text>
        {run.error_summary ? (
          <Text style={styles.errorLine} numberOfLines={1}>{run.error_summary}</Text>
        ) : (
          <Text style={[styles.metaLine, { color: colors.textMuted }]}>
            {fmtRelative(run.started_at)} · {fmtDuration(run.duration_ms)}
          </Text>
        )}
      </View>
      <Text style={[styles.statusText, { color: dot }]}>{run.status}</Text>
    </Pressable>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────

type Nav = NativeStackNavigationProp<MoreStackParamList>;

export default function CronMonitorScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<Nav>();

  const [runs, setRuns] = useState<CronRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const data = await apiService.getCronRuns({ limit: 200 });
      setRuns(data);
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(true); }, [load]);

  // 15-second auto-poll
  useEffect(() => {
    const interval = setInterval(() => load(false), 15_000);
    return () => clearInterval(interval);
  }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    load(false);
  };

  // Group runs by task group
  const grouped = Object.entries(TASK_GROUPS).map(([groupName, taskNames]) => ({
    group: groupName,
    runs: runs.filter((r) => taskNames.includes(r.task_name)),
  }));

  // KPIs
  const running = runs.filter((r) => r.status === 'running').length;
  const failures = runs.filter((r) => r.status === 'failure').length;

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </SVGBackground>
    );
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <FlatList
          contentContainerStyle={styles.container}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          ListHeaderComponent={
            <View>
              <Text style={[styles.title, { color: colors.text }]}>Cron Monitor</Text>
              <Text style={[styles.subtitle, { color: colors.textMuted }]}>Live scheduled task health</Text>
              <View style={styles.kpiRow}>
                <KpiChip label="Running" value={running} color="#67E8F9" />
                <KpiChip label="Failures" value={failures} color="#FF7A70" />
                <KpiChip label="Total runs" value={runs.length} color={colors.text as string} />
              </View>
            </View>
          }
          data={grouped}
          keyExtractor={(item) => item.group}
          renderItem={({ item }) => (
            <GlassCard padded={false} style={styles.groupCard}>
              <AccordionRow
                title={item.group}
                subtitle={`${item.runs.length} run${item.runs.length !== 1 ? 's' : ''}`}
                badge={item.runs.filter((r) => r.status === 'failure').length > 0
                  ? `${item.runs.filter((r) => r.status === 'failure').length} failed`
                  : undefined}
                badgeColor="#FF7A70"
              >
                {item.runs.length === 0 ? (
                  <Text style={[styles.emptyText, { color: colors.textMuted }]}>No runs recorded</Text>
                ) : (
                  item.runs.map((run) => (
                    <RunRow
                      key={run.id}
                      run={run}
                      colors={colors}
                      onPress={() => navigation.navigate('CronRunDetail', { runId: run.id })}
                    />
                  ))
                )}
              </AccordionRow>
            </GlassCard>
          )}
        />
      </SafeAreaView>
    </SVGBackground>
  );
}

function KpiChip({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <View style={styles.kpiChip}>
      <Text style={[styles.kpiValue, { color }]}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  container: { padding: 20, paddingBottom: 120, gap: 12 },
  title: { fontSize: 28, fontWeight: '900', marginTop: 10, marginBottom: 4 },
  subtitle: { fontSize: 13, fontWeight: '700', marginBottom: 18 },
  kpiRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 4,
  },
  kpiChip: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 18,
    padding: 12,
    alignItems: 'center',
  },
  kpiValue: { fontSize: 22, fontWeight: '800' },
  kpiLabel: { fontSize: 11, color: '#9CA3AF', marginTop: 2 },
  groupCard: { paddingHorizontal: 16 },
  runRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  taskName: { fontSize: 13, fontWeight: '600' },
  metaLine: { fontSize: 11, marginTop: 1 },
  errorLine: { fontSize: 11, color: '#EF4444', marginTop: 1 },
  statusText: { fontSize: 11, fontWeight: '600', textTransform: 'capitalize' },
  emptyText: { fontSize: 13, padding: 8, textAlign: 'center' },
});
