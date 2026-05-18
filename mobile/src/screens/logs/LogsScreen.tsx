import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { EmptyState, FilterChip, GlassCard, ScreenError, SectionHeader, StatusPill } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useSendLogsStore } from '../../store/sendLogsStore';
import { SendLog, SendLogStatus } from '../../types';
import { formatDateTime, humanize, logStatusTone } from '../../utils/format';

const ALL_STATUSES: Array<{ label: string; value: '' | SendLogStatus }> = [
  { label: 'All', value: '' },
  { label: 'Sent', value: 'sent' },
  { label: 'Delivered', value: 'delivered' },
  { label: 'Opened', value: 'opened' },
  { label: 'Clicked', value: 'clicked' },
  { label: 'Bounced', value: 'bounced' },
  { label: 'Soft Bounce', value: 'soft_bounced' },
  { label: 'Deferred', value: 'deferred' },
  { label: 'Blocked', value: 'blocked' },
  { label: 'Spam', value: 'failed' },
  { label: 'Queued', value: 'queued' },
  { label: 'Dry Run', value: 'dry_run' },
];

function LogRow({ log }: { log: SendLog }) {
  const { colors } = useTheme();
  const [expanded, setExpanded] = useState(false);

  return (
    <GlassCard>
      <Pressable onPress={() => setExpanded((v) => !v)}>
        <View style={styles.logHeader}>
          <View style={styles.logText}>
            <Text style={[styles.logTitle, { color: colors.text }]} numberOfLines={2}>
              {log.subject || log.job_title || 'Application email'}
            </Text>
            <Text style={[styles.logEmail, { color: colors.textMuted }]} numberOfLines={1}>
              {log.company ? `${log.company} · ` : ''}{log.to_email}
            </Text>
          </View>
          <View style={styles.logRight}>
            <StatusPill label={humanize(log.status)} tone={logStatusTone(log.status)} compact />
            <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={colors.textMuted} style={{ marginTop: 4 }} />
          </View>
        </View>

        <View style={[styles.logMetaRow, { borderTopColor: colors.border }]}>
          <Text style={[styles.logMeta, { color: colors.textMuted }]}>{formatDateTime(log.sent_at)}</Text>
          {log.provider ? <Text style={[styles.logMeta, { color: colors.textMuted }]}>{log.provider}</Text> : null}
          {log.retry_count > 0 && (
            <Text style={[styles.logMeta, { color: colors.warning }]}>Retries: {log.retry_count}</Text>
          )}
        </View>

        {log.error_message && !expanded && (
          <Text style={[styles.errorText, { color: colors.error }]} numberOfLines={1}>{log.error_message}</Text>
        )}
      </Pressable>

      {expanded && (
        <View style={[styles.expandedBody, { borderTopColor: colors.border }]}>
          {log.subject && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Subject</Text>
              <Text style={[styles.expandValue, { color: colors.text }]}>{log.subject}</Text>
            </View>
          )}
          {log.body_snippet && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Preview</Text>
              <Text style={[styles.expandValue, { color: colors.textSecondary }]} numberOfLines={3}>{log.body_snippet}</Text>
            </View>
          )}
          {log.provider_message_id && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Message ID</Text>
              <Text style={[styles.expandValue, { color: colors.text }]} numberOfLines={1}>{log.provider_message_id}</Text>
            </View>
          )}
          {log.delivered_at && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Delivered</Text>
              <Text style={[styles.expandValue, { color: colors.success }]}>{formatDateTime(log.delivered_at)}</Text>
            </View>
          )}
          {log.opened_at && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Opened</Text>
              <Text style={[styles.expandValue, { color: colors.success }]}>{formatDateTime(log.opened_at)}</Text>
            </View>
          )}
          {log.clicked_at && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Clicked</Text>
              <Text style={[styles.expandValue, { color: colors.accentMint }]}>{formatDateTime(log.clicked_at)}</Text>
            </View>
          )}
          {log.error_message && (
            <View style={styles.expandRow}>
              <Text style={[styles.expandLabel, { color: colors.textMuted }]}>Error</Text>
              <Text style={[styles.expandValue, { color: colors.error }]}>{log.error_message}</Text>
            </View>
          )}
        </View>
      )}
    </GlassCard>
  );
}

export default function LogsScreen() {
  const { colors } = useTheme();
  const { logs, statusFilter, loading, isFetchingMore, hasMore, error, fetchLogs, loadMore, setStatusFilter } = useSendLogsStore();
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs, statusFilter]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchLogs();
    setRefreshing(false);
  }, [fetchLogs]);

  const handleLoadMore = useCallback(() => {
    if (!isFetchingMore && hasMore && !loading) void loadMore();
  }, [isFetchingMore, hasMore, loading, loadMore]);

  // Count logs by status for chip counts
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const log of logs) {
      counts[log.status] = (counts[log.status] ?? 0) + 1;
    }
    return counts;
  }, [logs]);

  const ListHeader = useMemo(() => (
    <View>
      <View style={styles.header}>
        <View>
          <Text style={[styles.title, { color: colors.text }]}>Email Logs</Text>
          <Text style={[styles.subtitle, { color: colors.textMuted }]}>Tap a row to expand details</Text>
        </View>
        <StatusPill label={`${logs.length}`} tone="cyan" />
      </View>

      {/* Status filter chips with counts */}
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipRow}
        data={ALL_STATUSES}
        keyExtractor={(f) => f.label}
        renderItem={({ item: f }) => (
          <FilterChip
            label={f.label}
            active={statusFilter === f.value}
            onPress={() => setStatusFilter(f.value)}
            count={f.value ? statusCounts[f.value] : undefined}
          />
        )}
      />

      {error ? <ScreenError message={error} onRetry={() => void fetchLogs()} /> : null}

      {!error && (
        <SectionHeader
          title="Activity"
          subtitle={statusFilter ? humanize(statusFilter) : `All statuses · ${logs.length} loaded`}
        />
      )}
    </View>
  ), [colors, logs.length, statusFilter, statusCounts, error, fetchLogs, setStatusFilter]);

  const ListFooter = useMemo(() => {
    if (isFetchingMore) {
      return (
        <View style={styles.footerLoader}>
          <ActivityIndicator color={colors.primary} />
          <Text style={[styles.footerText, { color: colors.textMuted }]}>Loading more…</Text>
        </View>
      );
    }
    if (!hasMore && logs.length > 0 && !loading) {
      return <Text style={[styles.footerText, { color: colors.textMuted, textAlign: 'center', paddingVertical: 20 }]}>All logs loaded</Text>;
    }
    return <View style={{ height: 20 }} />;
  }, [isFetchingMore, hasMore, logs.length, loading, colors]);

  if (loading && !refreshing && logs.length === 0) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={[styles.centerText, { color: colors.textMuted }]}>Loading logs</Text>
        </View>
      </SVGBackground>
    );
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <FlatList
          data={logs}
          keyExtractor={(log) => log.id}
          renderItem={({ item }) => <LogRow log={item} />}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          ListHeaderComponent={ListHeader}
          ListFooterComponent={ListFooter}
          ListEmptyComponent={
            !loading && !error ? (
              <EmptyState
                title="No logs found"
                message="Email events will appear here once applications are sent."
                icon="mail-open-outline"
              />
            ) : null
          }
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.4}
          removeClippedSubviews
        />
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  centerText: { fontSize: 14, fontWeight: '700', marginTop: 14 },
  header: { alignItems: 'flex-start', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16, paddingTop: 10 },
  title: { fontSize: 30, fontWeight: '900' },
  subtitle: { fontSize: 12, fontWeight: '700', marginTop: 4 },
  chipRow: { gap: 8, paddingBottom: 18 },
  logHeader: { alignItems: 'flex-start', flexDirection: 'row', gap: 12, justifyContent: 'space-between' },
  logText: { flex: 1 },
  logRight: { alignItems: 'flex-end', gap: 2 },
  logTitle: { fontSize: 15, fontWeight: '900', lineHeight: 21, marginBottom: 5 },
  logEmail: { fontSize: 12, fontWeight: '700' },
  logMetaRow: { borderTopWidth: StyleSheet.hairlineWidth, flexDirection: 'row', gap: 12, justifyContent: 'space-between', marginTop: 14, paddingTop: 12 },
  logMeta: { fontSize: 11, fontWeight: '700' },
  errorText: { fontSize: 12, fontWeight: '700', marginTop: 8 },
  expandedBody: { borderTopWidth: StyleSheet.hairlineWidth, gap: 10, marginTop: 12, paddingTop: 12 },
  expandRow: { gap: 2 },
  expandLabel: { fontSize: 10, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  expandValue: { fontSize: 13, fontWeight: '600', lineHeight: 18 },
  footerLoader: { alignItems: 'center', flexDirection: 'row', gap: 10, justifyContent: 'center', paddingVertical: 20 },
  footerText: { fontSize: 13, fontWeight: '700' },
});
