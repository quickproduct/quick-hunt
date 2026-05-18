import React, { useCallback, useEffect } from 'react';
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
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, EmptyState, GlassCard, PageHeader, ScreenError, SectionHeader, SkeletonBlock, StatusPill } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useCandidatesStore } from '../../store/candidatesStore';
import { Candidate } from '../../types';
import { CandidatesStackParamList } from '../../navigation/AppNavigator';

type Nav = NativeStackNavigationProp<CandidatesStackParamList, 'CandidatesList'>;

function avatarColor(email: string): string {
  const palette = ['#39D0C8', '#4AE3A2', '#FFB84D', '#FF6B5F', '#A78BFA', '#38BDF8'];
  let hash = 0;
  for (let i = 0; i < email.length; i++) hash = (hash * 31 + email.charCodeAt(i)) & 0xffffffff;
  return palette[Math.abs(hash) % palette.length] ?? palette[0]!;
}

function CandidateCard({
  candidate,
  isActive,
  onEdit,
  onSetActive,
}: {
  candidate: Candidate;
  isActive: boolean;
  onEdit: () => void;
  onSetActive: () => void;
}) {
  const { colors } = useTheme();
  const bg = avatarColor(candidate.email);

  return (
    <GlassCard
      style={isActive ? { borderColor: colors.primary, borderWidth: 2 } : undefined}
    >
      <View style={styles.cardHeader}>
        {/* Active indicator strip */}
        {isActive && (
          <View style={[styles.activeDot, { backgroundColor: colors.primary }]} />
        )}
        <View style={[styles.avatar, { backgroundColor: bg }]}>
          <Text style={styles.avatarText}>{candidate.name[0]?.toUpperCase() ?? '?'}</Text>
        </View>
        <View style={styles.cardInfo}>
          <View style={styles.nameRow}>
            <Text style={[styles.name, { color: colors.text }]} numberOfLines={1}>{candidate.name}</Text>
            {isActive && (
              <View style={[styles.activeBadge, { backgroundColor: colors.primary }]}>
                <Text style={styles.activeBadgeText}>Active</Text>
              </View>
            )}
          </View>
          <Text style={[styles.cardEmail, { color: colors.textMuted }]} numberOfLines={1}>{candidate.email}</Text>
          <View style={styles.pills}>
            <StatusPill label={candidate.is_active ? 'Active' : 'Inactive'} tone={candidate.is_active ? 'mint' : 'neutral'} compact />
            {candidate.resume_url ? <StatusPill label="Resume ✓" tone="cyan" compact /> : <StatusPill label="No Resume" tone="neutral" compact />}
            {candidate.static_cover_letter ? <StatusPill label="Static Cover" tone="amber" compact /> : null}
          </View>
        </View>
      </View>

      {candidate.skills.length > 0 && (
        <View style={styles.skills}>
          {candidate.skills.slice(0, 5).map((s) => (
            <View key={s} style={[styles.skill, { backgroundColor: colors.primarySoft, borderColor: colors.border }]}>
              <Text style={[styles.skillText, { color: colors.primary }]}>{s}</Text>
            </View>
          ))}
          {candidate.skills.length > 5 && (
            <Text style={[styles.more, { color: colors.textMuted }]}>+{candidate.skills.length - 5} more</Text>
          )}
        </View>
      )}

      {/* Quick actions row */}
      <View style={[styles.actionRow, { borderTopColor: colors.border }]}>
        {!isActive && (
          <Pressable onPress={onSetActive} style={styles.setActiveBtn} hitSlop={6}>
            <Ionicons name="person-circle-outline" size={18} color={colors.textMuted} />
            <Text style={[styles.setActiveTxt, { color: colors.textMuted }]}>Set active</Text>
          </Pressable>
        )}
        <View style={{ flex: 1 }} />
        <AppButton
          label="Edit"
          icon="create-outline"
          variant="secondary"
          onPress={onEdit}
          style={styles.editBtn}
        />
      </View>
    </GlassCard>
  );
}

export default function CandidatesScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<Nav>();
  const { candidates, activeCandidateId, loading, error, fetchCandidates, setActiveCandidate } = useCandidatesStore();
  const [refreshing, setRefreshing] = React.useState(false);

  useEffect(() => { void fetchCandidates(); }, [fetchCandidates]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchCandidates();
    setRefreshing(false);
  }, [fetchCandidates]);

  const goEdit = (candidateId?: string) => navigation.navigate('CandidateEdit', { candidateId });

  if (loading && !refreshing && candidates.length === 0) {
    return (
      <SVGBackground>
        <View style={styles.loadingContent}>
          <SkeletonBlock width="58%" height={34} radius={17} />
          {[0, 1, 2].map((item) => (
            <GlassCard key={item} style={styles.loadingCard}>
              <View style={styles.loadingRow}>
                <SkeletonBlock width={48} height={48} radius={24} />
                <View style={styles.loadingText}>
                  <SkeletonBlock width="70%" height={18} />
                  <SkeletonBlock width="92%" height={12} style={styles.loadingGapSm} />
                </View>
              </View>
            </GlassCard>
          ))}
          <ActivityIndicator color={colors.primary} size="small" style={styles.loadingSpinner} />
        </View>
      </SVGBackground>
    );
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <FlatList
          data={candidates}
          keyExtractor={(c) => c.id}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          ListHeaderComponent={
            <>
              <View style={styles.header}>
                <PageHeader
                  title="Candidates"
                  subtitle={`${candidates.length} profile${candidates.length !== 1 ? 's' : ''}${activeCandidateId ? ' - 1 active' : ''}`}
                  action={<AppButton label="Add" icon="person-add-outline" onPress={() => goEdit()} style={styles.addBtn} />}
                />
              </View>
              {error && <ScreenError message={error} onRetry={() => void fetchCandidates()} />}
              <SectionHeader title="All Candidates" />
            </>
          }
          renderItem={({ item }) => (
            <CandidateCard
              candidate={item}
              isActive={item.id === activeCandidateId}
              onEdit={() => goEdit(item.id)}
              onSetActive={() => setActiveCandidate(item.id)}
            />
          )}
          ListEmptyComponent={
            !loading ? (
              <EmptyState
                icon="person-outline"
                title="No candidates yet"
                message="Add your first candidate to start applying for jobs."
                action={<AppButton label="Add Candidate" icon="person-add-outline" onPress={() => goEdit()} style={styles.emptyBtn} />}
              />
            ) : null
          }
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        />
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  loadingContent: { flex: 1, justifyContent: 'center', padding: 20 },
  loadingCard: { marginTop: 14 },
  loadingRow: { alignItems: 'center', flexDirection: 'row', gap: 12 },
  loadingText: { flex: 1 },
  loadingGapSm: { marginTop: 9 },
  loadingSpinner: { marginTop: 20 },
  content: { padding: 20, paddingBottom: 118 },
  header: { marginBottom: 24 },
  addBtn: { minWidth: 90 },
  cardHeader: { alignItems: 'flex-start', flexDirection: 'row', gap: 12, marginBottom: 4 },
  activeDot: { borderRadius: 4, height: '100%', left: -16, position: 'absolute', top: 0, width: 4 },
  avatar: { alignItems: 'center', borderRadius: 24, height: 48, justifyContent: 'center', width: 48, flexShrink: 0 },
  avatarText: { color: '#052727', fontSize: 20, fontWeight: '900' },
  cardInfo: { flex: 1 },
  nameRow: { alignItems: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 2 },
  name: { fontSize: 16, fontWeight: '800' },
  activeBadge: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  activeBadgeText: { color: '#fff', fontSize: 10, fontWeight: '900' },
  cardEmail: { fontSize: 12, fontWeight: '600', marginBottom: 8 },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  skills: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 14 },
  skill: { borderRadius: 999, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 4 },
  skillText: { fontSize: 11, fontWeight: '700' },
  more: { fontSize: 11, fontWeight: '700', paddingVertical: 4 },
  actionRow: {
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 10,
    marginTop: 14,
    paddingTop: 12,
  },
  setActiveBtn: { alignItems: 'center', flexDirection: 'row', gap: 6 },
  setActiveTxt: { fontSize: 13, fontWeight: '700' },
  editBtn: { minHeight: 40, minWidth: 80 },
  emptyBtn: { minWidth: 160 },
});
