/**
 * DeviceLogsViewer.tsx
 *
 * Reusable component that reads structured log entries from the device's
 * file storage (via logger.readLogs) and displays them in a scrollable list.
 *
 * Features:
 *  - Level filter tabs: All / Error / Critical
 *  - Reload, Share, and Clear actions
 *  - JSON-parsed structured display with level pill + event title + context fields
 *  - Fallback raw-monospace display for unparseable lines
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  FlatList,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { AppButton, FilterChip, StatusPill } from './GlassKit';
import { useTheme } from '../context/ThemeContext';
import { logger, LogEntry, LogFile } from '../utils/logger';
import { formatDateTime } from '../utils/format';

// ─── Level → GlassKit tone ─────────────────────────────────────────────────────
type Tone = 'mint' | 'cyan' | 'amber' | 'coral' | 'neutral';

function levelTone(level?: string): Tone {
  switch (level?.toUpperCase()) {
    case 'CRITICAL': return 'coral';
    case 'ERROR':    return 'coral';
    case 'WARN':     return 'amber';
    case 'INFO':     return 'cyan';
    case 'DEBUG':    return 'neutral';
    default:         return 'neutral';
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function LogItem({ entry }: { entry: LogEntry }) {
  const { colors } = useTheme();

  // Collect context fields (exclude standard top-level fields)
  const STANDARD = new Set(['timestamp', 'level', 'event', 'service', 'environment', '_raw']);
  const ctxEntries = Object.entries(entry).filter(([k, v]) => !STANDARD.has(k) && v !== undefined && v !== null && v !== '');

  return (
    <View style={[styles.logItem, { borderBottomColor: colors.border }]}>
      {/* Top row: level pill + timestamp */}
      <View style={styles.logTop}>
        <StatusPill label={entry.level ?? '?'} tone={levelTone(entry.level)} compact />
        <Text style={[styles.logTime, { color: colors.textMuted }]}>
          {entry.timestamp ? formatDateTime(entry.timestamp) : '—'}
        </Text>
      </View>

      {/* Event name */}
      <Text style={[styles.logEvent, { color: colors.text }]} numberOfLines={2}>
        {entry.event || entry._raw as string || '(no event)'}
      </Text>

      {/* Context fields */}
      {ctxEntries.length > 0 && (
        <View style={styles.ctxBlock}>
          {ctxEntries.slice(0, 6).map(([k, v]) => (
            <Text key={k} style={[styles.ctxLine, { color: colors.textMuted }]} numberOfLines={2}>
              <Text style={{ fontWeight: '700' }}>{k}: </Text>
              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

const LEVEL_TABS: Array<{ label: string; file: LogFile }> = [
  { label: 'All',      file: 'app'      },
  { label: 'Errors',   file: 'error'    },
  { label: 'Critical', file: 'critical' },
];

interface Props {
  initialLevel?: LogFile;
}

export default function DeviceLogsViewer({ initialLevel = 'app' }: Props) {
  const { colors } = useTheme();
  const [activeFile, setActiveFile] = useState<LogFile>(initialLevel);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await logger.readLogs(activeFile, 120);
      setEntries(data);
    } finally {
      setLoading(false);
    }
  }, [activeFile]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleShare() {
    setShareLoading(true);
    try {
      await logger.shareLog(activeFile);
    } catch (e: any) {
      Alert.alert('Share failed', e?.message ?? 'Could not share log file');
    } finally {
      setShareLoading(false);
    }
  }

  function handleClear() {
    Alert.alert(
      'Clear device logs',
      'This will permanently delete all log files from this device.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            await logger.clearLogs();
            setEntries([]);
          },
        },
      ]
    );
  }

  return (
    <View style={styles.container}>
      {/* Level tabs */}
      <View style={styles.tabRow}>
        {LEVEL_TABS.map((tab) => (
          <FilterChip
            key={tab.file}
            label={tab.label}
            active={activeFile === tab.file}
            onPress={() => setActiveFile(tab.file)}
          />
        ))}
      </View>

      {/* Actions */}
      <View style={styles.actionRow}>
        <AppButton
          label={loading ? 'Loading…' : 'Reload'}
          icon="refresh-outline"
          variant="secondary"
          loading={loading}
          onPress={reload}
          style={styles.actionBtn}
        />
        <AppButton
          label={shareLoading ? 'Sharing…' : 'Share'}
          icon="share-outline"
          variant="secondary"
          loading={shareLoading}
          onPress={handleShare}
          style={styles.actionBtn}
        />
        <AppButton
          label="Clear"
          icon="trash-outline"
          variant="danger"
          onPress={handleClear}
          style={styles.actionBtn}
        />
      </View>

      {/* Entry count */}
      {entries.length > 0 && (
        <Text style={[styles.countLine, { color: colors.textMuted }]}>
          {entries.length} entr{entries.length === 1 ? 'y' : 'ies'} (newest first)
        </Text>
      )}

      {/* Empty state */}
      {!loading && entries.length === 0 && (
        <Text style={[styles.emptyText, { color: colors.textMuted }]}>No log entries yet.</Text>
      )}

      {/* Log list (non-scrollable — parent ScrollView handles scroll) */}
      {entries.map((entry, idx) => (
        <LogItem key={`${entry.timestamp}-${idx}`} entry={entry} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 12 },
  tabRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 },
  actionRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  actionBtn: { flex: 1, minHeight: 40 },
  countLine: { fontSize: 11, fontWeight: '600', marginBottom: 8 },
  emptyText: { fontSize: 13, fontWeight: '600', textAlign: 'center', paddingVertical: 16 },
  logItem: { borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 10, gap: 4 },
  logTop: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  logTime: { fontSize: 11, fontWeight: '600' },
  logEvent: { fontSize: 13, fontWeight: '800' },
  ctxBlock: { gap: 2, marginTop: 2 },
  ctxLine: { fontSize: 11, fontWeight: '500', lineHeight: 16 },
});
