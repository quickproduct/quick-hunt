import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import { GlassCard, ScreenError, SectionHeader } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import apiService from '../../services/api';
import { AdminQuota, QuotaEntry } from '../../types';
import { formatDate } from '../../utils/format';

function QuotaCard({ name, entry }: { name: string; entry: QuotaEntry }) {
  const { colors } = useTheme();
  const used = entry.used ?? 0;
  const limit = entry.limit ?? 0;
  const pct = limit > 0 ? Math.min(1, used / limit) : 0;
  const barColor =
    pct > 0.85 ? colors.error : pct > 0.6 ? colors.warning : colors.success;

  return (
    <GlassCard style={styles.quotaCard}>
      <View style={styles.quotaHeader}>
        <Text style={[styles.quotaName, { color: colors.text }]}>{name}</Text>
        <Text style={[styles.quotaCount, { color: colors.textMuted }]}>
          {used.toLocaleString()} / {limit.toLocaleString()}
          {entry.unit ? ` ${entry.unit}` : ''}
        </Text>
      </View>

      {/* Progress bar */}
      <View style={[styles.barTrack, { backgroundColor: colors.border }]}>
        <View style={[styles.barFill, { width: `${Math.round(pct * 100)}%` as any, backgroundColor: barColor }]} />
      </View>

      <View style={styles.quotaFooter}>
        <Text style={[styles.pctText, { color: barColor }]}>{Math.round(pct * 100)}% used</Text>
        {entry.resets_at && (
          <Text style={[styles.resetText, { color: colors.textMuted }]}>
            Resets {formatDate(entry.resets_at)}
          </Text>
        )}
      </View>
    </GlassCard>
  );
}

export default function AdminQuotaScreen() {
  const { colors } = useTheme();
  const [quota, setQuota] = useState<AdminQuota | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const data = await apiService.getAdminQuota();
      setQuota(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to load quota');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(true); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(false); };

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={[styles.centerText, { color: colors.textMuted }]}>Loading quotas...</Text>
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
          <Text style={[styles.title, { color: colors.text }]}>API Quotas</Text>
          <Text style={[styles.subtitle, { color: colors.textMuted }]}>External provider usage limits</Text>

          {error && <ScreenError message={error} onRetry={() => load(true)} />}

          {quota && !error && (
            <>
              {/* Groq */}
              {quota.groq && quota.groq.used != null && quota.groq.limit != null && (
                <>
                  <SectionHeader title="Groq (LLM)" />
                  <QuotaCard name="Groq API" entry={quota.groq} />
                </>
              )}

              {/* HR Email Providers */}
              {quota.hr_email_providers && Object.keys(quota.hr_email_providers).length > 0 && (
                <>
                  <SectionHeader title="HR Email Providers" />
                  {Object.entries(quota.hr_email_providers).map(([name, entry]) => {
                    if (!entry || entry.used == null || entry.limit == null) return null;
                    return <QuotaCard key={name} name={name} entry={entry} />;
                  })}
                </>
              )}

              {/* Any other top-level quota keys */}
              {Object.entries(quota)
                .filter(([k]) => k !== 'groq' && k !== 'hr_email_providers')
                .map(([key, val]) => {
                  if (!val || typeof val !== 'object' || !('used' in val)) return null;
                  const entry = val as QuotaEntry;
                  return (
                    <React.Fragment key={key}>
                      <SectionHeader title={key.replace(/_/g, ' ')} />
                      <QuotaCard name={key} entry={entry} />
                    </React.Fragment>
                  );
                })}

              {/* Empty state */}
              {!quota.groq && (!quota.hr_email_providers || Object.keys(quota.hr_email_providers).length === 0) && (
                <GlassCard>
                  <Text style={[styles.emptyText, { color: colors.textMuted }]}>No quota data available.</Text>
                </GlassCard>
              )}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerText: { fontSize: 14, fontWeight: '700', marginTop: 14 },
  content: { padding: 20, paddingBottom: 120 },
  title: { fontSize: 28, fontWeight: '900', marginTop: 10, marginBottom: 4 },
  subtitle: { fontSize: 13, fontWeight: '500', marginBottom: 20 },
  quotaCard: { marginBottom: 12 },
  quotaHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  quotaName: { fontSize: 16, fontWeight: '800', flex: 1 },
  quotaCount: { fontSize: 13, fontWeight: '700' },
  barTrack: { height: 9, borderRadius: 999, overflow: 'hidden', marginBottom: 8 },
  barFill: { height: 9, borderRadius: 999 },
  quotaFooter: { flexDirection: 'row', justifyContent: 'space-between' },
  pctText: { fontSize: 12, fontWeight: '800' },
  resetText: { fontSize: 12, fontWeight: '600' },
  emptyText: { fontSize: 14, fontWeight: '600', textAlign: 'center', paddingVertical: 8 },
});
