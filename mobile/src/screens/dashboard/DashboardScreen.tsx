import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, EmptyState, FilterChip, GlassCard, PageHeader, ScreenError, SectionCard, SectionHeader, SkeletonBlock, StatTile, StatusPill } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useAuthStore } from '../../store/authStore';
import { useCandidatesStore } from '../../store/candidatesStore';
import { useJobsStore } from '../../store/jobsStore';
import { MainTabParamList } from '../../navigation/AppNavigator';
import apiService from '../../services/api';
import { HrEmailPipelineStats, SearchTask, SendLog, Stats } from '../../types';
import { compactNumber, formatRelative, humanize, logStatusTone, percent } from '../../utils/format';

type TabNav = BottomTabNavigationProp<MainTabParamList>;

const EMPTY_STATS: Stats = {
  total_jobs: 0,
  jobs_by_status: {},
  jobs_by_portal: {},
  jobs_with_hr_email: 0,
  cover_letters_generated: 0,
  emails_sent: 0,
  emails_delivered: 0,
  emails_opened: 0,
  emails_clicked: 0,
  emails_bounced: 0,
  emails_soft_bounced: 0,
  jobs_ready: 0,
  jobs_missing_hr: 0,
  jobs_pending_approval: 0,
};

export default function DashboardScreen() {
  const { colors } = useTheme();
  const { user } = useAuthStore();
  const navigation = useNavigation<TabNav>();
  const { candidates, activeCandidateId, setActiveCandidate, fetchCandidates } = useCandidatesStore();
  const { setFilters } = useJobsStore();
  const [stats, setStats] = useState<Stats | null>(null);
  const [hrPipeline, setHrPipeline] = useState<HrEmailPipelineStats | null>(null);
  const [searches, setSearches] = useState<SearchTask[]>([]);
  const [logs, setLogs] = useState<SendLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const loadDashboardData = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const params = activeCandidateId ? { candidate_id: activeCandidateId } : undefined;
      const [statsData, logsData, searchesData, pipelineData] = await Promise.all([
        apiService.getStats(params),
        apiService.getSendLogs({ limit: 5 }),
        apiService.getSearchTasks(5),
        apiService.getHrEmailPipeline().catch(() => null),
      ]);
      setStats(statsData);
      setLogs(logsData);
      setSearches(searchesData);
      setHrPipeline(pipelineData);
      setLastRefresh(new Date());
    } catch (loadError: any) {
      setError(loadError.response?.data?.detail || 'Failed to load dashboard data. Check that the API is running.');
    } finally {
      setLoading(false);
    }
  }, [activeCandidateId]);

  useEffect(() => { void fetchCandidates(); }, [fetchCandidates]);

  useEffect(() => {
    void loadDashboardData(true);
    const id = setInterval(() => void loadDashboardData(false), 60_000);
    return () => clearInterval(id);
  }, [loadDashboardData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchCandidates(), loadDashboardData(false)]);
    setRefreshing(false);
  };

  const goToJobs = useCallback((filterOverride?: Parameters<typeof setFilters>[0]) => {
    if (filterOverride) setFilters(filterOverride);
    navigation.navigate('Jobs');
  }, [navigation, setFilters]);

  const data = stats ?? EMPTY_STATS;
  const sent = data.emails_sent;
  const delivered = data.emails_delivered;
  const opened = data.emails_opened;
  const clicked = data.emails_clicked;
  const bounced = data.emails_bounced + data.emails_soft_bounced;
  const deliveryRate = percent(delivered, delivered + bounced || sent);
  const openRate = percent(opened, delivered || sent);
  const clickRate = percent(clicked, opened || delivered || sent);

  const pipeline = useMemo(() => [
    { label: 'Scraped', value: data.total_jobs, total: data.total_jobs, color: colors.primary },
    { label: 'HR found', value: data.jobs_with_hr_email, total: data.total_jobs, color: colors.accentAmber },
    { label: 'Covers', value: data.cover_letters_generated, total: data.jobs_with_hr_email || data.total_jobs, color: colors.accentCoral },
    { label: 'Ready', value: data.jobs_ready, total: data.cover_letters_generated || data.total_jobs, color: colors.accentMint },
    { label: 'Sent', value: data.emails_sent, total: data.jobs_ready || data.total_jobs, color: colors.primary },
  ], [colors, data]);

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.loadingContent}>
          <SkeletonBlock width="52%" height={18} />
          <SkeletonBlock width="76%" height={34} radius={17} style={styles.loadingGap} />
          <View style={styles.loadingGrid}>
            {[0, 1, 2, 3].map((item) => (
              <GlassCard key={item} style={styles.loadingTile}>
                <SkeletonBlock width={38} height={38} radius={16} />
                <SkeletonBlock width="64%" height={24} style={styles.loadingGapSm} />
                <SkeletonBlock width="80%" height={12} />
              </GlassCard>
            ))}
          </View>
          <ActivityIndicator color={colors.primary} size="small" style={styles.loadingSpinner} />
          <Text style={[styles.centerText, { color: colors.textMuted }]}>Loading dashboard</Text>
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
          {/* Header */}
          <PageHeader
            title={user?.name || user?.email?.split('@')[0] || 'Job Hunt'}
            subtitle={lastRefresh ? `Updated ${formatRelative(lastRefresh.toISOString())}` : 'Live backend snapshot'}
          />

          {/* Candidate selector */}
          {candidates.length > 0 ? (
            <FlatList
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipRow}
              data={[{ id: '', name: 'All', icon: 'people-outline' as const }, ...candidates]}
              keyExtractor={(item) => item.id}
              renderItem={({ item }) => (
                <FilterChip
                  label={item.name}
                  active={item.id === (activeCandidateId || '')}
                  onPress={() => setActiveCandidate(item.id)}
                  icon={item.id ? 'person-outline' : 'people-outline'}
                />
              )}
            />
          ) : null}

          {error ? <ScreenError message={error} onRetry={() => void loadDashboardData(true)} /> : null}

          {!error && (
            <>
              {/* KPI stat tiles — tappable to navigate to filtered jobs */}
              <View style={styles.statsGrid}>
                <StatTile
                  label="Total Jobs"
                  value={compactNumber(data.total_jobs)}
                  icon="briefcase-outline"
                  accent="primary"
                  onPress={() => goToJobs({})}
                />
                <StatTile
                  label="HR Emails"
                  value={compactNumber(data.jobs_with_hr_email)}
                  icon="mail-outline"
                  accent="amber"
                  onPress={() => goToJobs({ has_hr_email: 'yes' })}
                />
                <StatTile
                  label="Covers"
                  value={compactNumber(data.cover_letters_generated)}
                  icon="document-text-outline"
                  accent="coral"
                  onPress={() => goToJobs({ has_cover: 'yes' })}
                />
                <StatTile
                  label="Ready"
                  value={compactNumber(data.jobs_ready)}
                  icon="checkmark-done-outline"
                  accent="mint"
                  onPress={() => goToJobs({ has_hr_email: 'yes', has_cover: 'yes', status: 'cover_generated' })}
                />
              </View>

              {/* Quick navigation row */}
              <View style={styles.quickRow}>
                <QuickAction icon="search-outline" label="Search" onPress={() => navigation.navigate('Search')} colors={colors} />
                <QuickAction icon="briefcase-outline" label="All Jobs" onPress={() => navigation.navigate('Jobs')} colors={colors} />
                <QuickAction icon="mail-outline" label="Send Logs" onPress={() => navigation.navigate('More')} colors={colors} />
                <QuickAction icon="people-outline" label="Candidates" onPress={() => navigation.navigate('Candidates')} colors={colors} />
              </View>

              {/* Application Pipeline */}
              <SectionHeader title="Application Pipeline" subtitle="Conversion across the hunt" />
              <SectionCard>
                {pipeline.map((step) => (
                  <View key={step.label} style={styles.pipelineRow}>
                    <View style={styles.pipelineLabelWrap}>
                      <Text style={[styles.pipelineLabel, { color: colors.textSecondary }]}>{step.label}</Text>
                      <Text style={[styles.pipelineValue, { color: colors.text }]}>{compactNumber(step.value)}</Text>
                    </View>
                    <View style={[styles.progressTrack, { backgroundColor: colors.borderStrong }]}>
                      <View
                        style={[
                          styles.progressFill,
                          {
                            backgroundColor: step.color,
                            width: `${Math.min(100, step.total ? Math.round((step.value / step.total) * 100) : 0)}%`,
                          },
                        ]}
                      />
                    </View>
                  </View>
                ))}
              </SectionCard>

              {/* Email Performance */}
              <SectionHeader title="Email Performance" subtitle={`${compactNumber(sent)} emails sent`} />
              <SectionCard>
                <MetricRow label="Delivery Rate" value={deliveryRate} detail={`${delivered} / ${sent}`} color={colors.accentMint} />
                <MetricRow label="Open Rate" value={openRate} detail={`${opened} / ${delivered || sent}`} color={colors.primary} />
                <MetricRow label="Click Rate" value={clickRate} detail={`${clicked} / ${opened || delivered || sent}`} color={colors.accentAmber} />
              </SectionCard>

              {/* Bottlenecks */}
              <SectionHeader title="Bottlenecks" />
              <SectionCard>
                <BottleneckRow
                  icon="mail-unread-outline"
                  label="Missing HR email"
                  value={data.jobs_missing_hr}
                  tone="coral"
                  onPress={() => goToJobs({ has_hr_email: 'no' })}
                />
                <BottleneckRow
                  icon="time-outline"
                  label="Pending approval"
                  value={data.jobs_pending_approval}
                  tone="amber"
                  onPress={() => goToJobs({ status: 'pending_approval' })}
                />
                <BottleneckRow icon="warning-outline" label="Bounced" value={bounced} tone="coral" />
              </SectionCard>

              {/* HR Email Pipeline */}
              {hrPipeline && (
                <>
                  <SectionHeader title="HR Email Pipeline" subtitle="Discovery health" />
                  <GlassCard>
                    <BottleneckRow icon="hourglass-outline" label="Pending Discovery" value={hrPipeline.jobs_pending_discovery} tone="amber" />
                    <BottleneckRow icon="wifi-outline" label="Unreachable" value={hrPipeline.jobs_unreachable} tone="coral" />
                    <BottleneckRow icon="checkmark-circle-outline" label="HR Found" value={hrPipeline.jobs_found} tone="amber" />
                    <BottleneckRow icon="alert-circle-outline" label="Cover Ready, Missing HR" value={hrPipeline.cover_ready_missing_hr} tone="coral" />
                  </GlassCard>
                </>
              )}

              {/* Recent Searches */}
              <SectionHeader
                title="Recent Searches"
                action={
                  <Pressable onPress={() => navigation.navigate('Search')} hitSlop={8}>
                    <Text style={[styles.viewAll, { color: colors.primary }]}>Search →</Text>
                  </Pressable>
                }
              />
              {searches.length === 0 ? (
                <EmptyState title="No searches yet" message="Start a search and live task progress will appear here." icon="search-outline" />
              ) : (
                <View style={styles.stack}>
                  {searches.map((task, index) => (
                    <GlassCard key={task.id} delay={index * 40}>
                      <View style={styles.listHeader}>
                        <View style={styles.listText}>
                          <Text style={[styles.listTitle, { color: colors.text }]} numberOfLines={1}>
                            {task.job_titles.join(', ') || 'Search task'}
                          </Text>
                          <Text style={[styles.listSubtitle, { color: colors.textMuted }]} numberOfLines={2}>
                            {task.locations.join(', ') || 'Any location'} · {task.portals.join(', ') || 'No portals'} · {task.jobs_found} found
                          </Text>
                        </View>
                        <StatusPill
                          label={task.status}
                          tone={task.status === 'completed' ? 'mint' : task.status === 'error' ? 'coral' : 'cyan'}
                          compact
                        />
                      </View>
                    </GlassCard>
                  ))}
                </View>
              )}

              {/* Recent Applications */}
              <SectionHeader
                title="Recent Applications"
                action={
                  <Pressable onPress={() => navigation.navigate('More')} hitSlop={8}>
                    <Text style={[styles.viewAll, { color: colors.primary }]}>Logs →</Text>
                  </Pressable>
                }
              />
              {logs.length === 0 ? (
                <EmptyState title="No applications yet" message="Sent applications and delivery events will show here." icon="mail-open-outline" />
              ) : (
                <View style={styles.stack}>
                  {logs.map((log, index) => (
                    <GlassCard key={log.id} delay={index * 40}>
                      <View style={styles.listHeader}>
                        <View style={styles.listText}>
                          <Text style={[styles.listTitle, { color: colors.text }]} numberOfLines={1}>
                            {log.job_title || log.subject || log.to_email}
                          </Text>
                          <Text style={[styles.listSubtitle, { color: colors.textMuted }]} numberOfLines={1}>
                            {log.company ? `${log.company} · ` : ''}{log.to_email}
                          </Text>
                          <Text style={[styles.listMeta, { color: colors.textMuted }]}>{formatRelative(log.sent_at)}</Text>
                        </View>
                        <StatusPill label={humanize(log.status)} tone={logStatusTone(log.status)} compact />
                      </View>
                    </GlassCard>
                  ))}
                </View>
              )}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

function QuickAction({
  icon,
  label,
  onPress,
  colors,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  colors: ReturnType<typeof useTheme>['colors'];
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.quickAction,
        { backgroundColor: colors.surfaceStrong, borderColor: colors.border, opacity: pressed ? 0.8 : 1 },
      ]}
    >
      <View style={[styles.quickActionIcon, { backgroundColor: colors.primarySoft }]}>
        <Ionicons name={icon} size={20} color={colors.primary} />
      </View>
      <Text style={[styles.quickActionLabel, { color: colors.textSecondary }]} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

function MetricRow({ label, value, detail, color }: { label: string; value: string; detail: string; color: string }) {
  const { colors } = useTheme();
  const numeric = value.endsWith('%') ? Number(value.replace('%', '')) : 0;
  return (
    <View style={styles.metricRow}>
      <View style={styles.metricHeader}>
        <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{label}</Text>
        <Text style={[styles.metricValue, { color: colors.text }]}>
          {value} <Text style={{ color: colors.textMuted }}>({detail})</Text>
        </Text>
      </View>
      <View style={[styles.progressTrack, { backgroundColor: colors.borderStrong }]}>
        <View style={[styles.progressFill, { width: `${Math.min(100, numeric)}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
}

function BottleneckRow({
  icon,
  label,
  value,
  tone,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: number;
  tone: 'amber' | 'coral' | 'mint';
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  const color = tone === 'amber' ? colors.accentAmber : tone === 'mint' ? colors.accentMint : colors.accentCoral;
  const textColor = tone === 'amber' ? colors.warning : tone === 'mint' ? colors.success : colors.error;

  const inner = (
    <View style={styles.bottleneckRow}>
      <View style={styles.bottleneckLabel}>
        <Ionicons name={icon} size={17} color={color} />
        <Text style={[styles.bottleneckText, { color: colors.textSecondary }]}>{label}</Text>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
        <Text style={[styles.bottleneckValue, { color: textColor }]}>{value}</Text>
        {onPress ? <Ionicons name="chevron-forward" size={14} color={colors.textMuted} /> : null}
      </View>
    </View>
  );

  if (onPress) {
    return (
      <Pressable onPress={onPress} style={({ pressed }) => [{ opacity: pressed ? 0.7 : 1 }]}>
        {inner}
      </Pressable>
    );
  }
  return inner;
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  loadingContent: { flex: 1, justifyContent: 'center', padding: 20 },
  loadingGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, justifyContent: 'space-between', marginTop: 20 },
  loadingTile: { minHeight: 104, width: '47.5%' },
  loadingGap: { marginTop: 10 },
  loadingGapSm: { marginTop: 14, marginBottom: 8 },
  loadingSpinner: { marginTop: 20 },
  centerText: { fontSize: 14, fontWeight: '700', marginTop: 14 },
  chipRow: { gap: 8, paddingBottom: 18 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, justifyContent: 'space-between', marginBottom: 20 },
  quickRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 24, justifyContent: 'space-between' },
  quickAction: {
    alignItems: 'flex-start',
    borderRadius: 22,
    borderWidth: 1,
    gap: 10,
    minHeight: 96,
    paddingHorizontal: 14,
    paddingVertical: 14,
    width: '47.5%',
  },
  quickActionIcon: { alignItems: 'center', borderRadius: 14, height: 42, justifyContent: 'center', width: 42 },
  quickActionLabel: { fontSize: 13, fontWeight: '800' },
  pipelineRow: { marginBottom: 14 },
  pipelineLabelWrap: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  pipelineLabel: { fontSize: 13, fontWeight: '700' },
  pipelineValue: { fontSize: 13, fontWeight: '900' },
  progressTrack: { borderRadius: 999, height: 8, overflow: 'hidden' },
  progressFill: { borderRadius: 999, height: '100%' },
  metricRow: { marginBottom: 16 },
  metricHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  metricLabel: { fontSize: 13, fontWeight: '700' },
  metricValue: { fontSize: 12, fontWeight: '900' },
  bottleneckRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10 },
  bottleneckLabel: { alignItems: 'center', flexDirection: 'row', gap: 10 },
  bottleneckText: { fontSize: 14, fontWeight: '700' },
  bottleneckValue: { fontSize: 15, fontWeight: '900' },
  stack: { gap: 12, marginBottom: 24 },
  listHeader: { alignItems: 'flex-start', flexDirection: 'row', gap: 12, justifyContent: 'space-between' },
  listText: { flex: 1 },
  listTitle: { fontSize: 15, fontWeight: '800', marginBottom: 5 },
  listSubtitle: { fontSize: 12, fontWeight: '600', lineHeight: 17 },
  listMeta: { fontSize: 11, fontWeight: '600', marginTop: 6 },
  viewAll: { fontSize: 13, fontWeight: '800' },
});
