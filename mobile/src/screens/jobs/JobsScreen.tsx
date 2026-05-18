import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, EmptyState, FilterChip, GlassCard, PageHeader, ScreenError, SectionHeader, StatusPill } from '../../components/GlassKit';
import InlineEditField from '../../components/InlineEditField';
import { useTheme } from '../../context/ThemeContext';
import { JobsStackParamList } from '../../navigation/AppNavigator';
import { useCandidatesStore } from '../../store/candidatesStore';
import { DEFAULT_FILTERS, useJobsStore } from '../../store/jobsStore';
import { Job, JobFilters, JobStatus } from '../../types';
import { daysAgoISO, formatDate, formatScore, formatSalary, humanize, jobStatusTone, todayISO } from '../../utils/format';

const PORTALS = [
  'naukri', 'indeed', 'glassdoor', 'linkedin', 'angellist',
  'shine', 'timesjobs', 'foundit', 'internshala', 'cutshort',
  'instahyre', 'wellfound', 'remoteok', 'remotive',
];

const STATUSES: JobStatus[] = [
  'new', 'scoring', 'filtered', 'pending_approval', 'cover_generated',
  'sending', 'sent', 'applied', 'bounced', 'ignored', 'error',
];

const JOB_TYPES = ['full-time', 'contract', 'part-time', 'internship'];

function countActiveFilters(filters: JobFilters): number {
  let count = 0;
  if (filters.status) count++;
  if (filters.portal) count++;
  if (filters.job_type) count++;
  if (filters.has_hr_email) count++;
  if (filters.has_cover) count++;
  if (filters.min_score > 0) count++;
  if (filters.scraped_after) count++;
  if (filters.posted_after) count++;
  if (filters.sort_by !== DEFAULT_FILTERS.sort_by || filters.sort_dir !== DEFAULT_FILTERS.sort_dir) count++;
  return count;
}

export default function JobsScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<JobsStackParamList, 'JobsList'>>();
  const { colors } = useTheme();
  const {
    jobs,
    totalCount,
    loading,
    isFetchingMore,
    error,
    filters,
    selected,
    hasMore,
    fetchJobs,
    loadMore,
    setFilters,
    resetFilters,
    toggleSelect,
    selectAllPage,
    selectAllMatching,
    clearSelection,
    generateCoverLetter,
    bulkGenerateCovers,
    sendApplication,
    bulkSendApplications,
    setHrEmail,
  } = useJobsStore();
  const { candidates, activeCandidateId, setActiveCandidate, fetchCandidates } = useCandidatesStore();
  const [showFilters, setShowFilters] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [searchText, setSearchText] = useState(filters.search);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    void fetchCandidates();
  }, [fetchCandidates]);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  // Debounce search input
  const handleSearchChange = useCallback((text: string) => {
    setSearchText(text);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setFilters({ search: text });
    }, 400);
  }, [setFilters]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchCandidates(), fetchJobs()]);
    setRefreshing(false);
  }, [fetchCandidates, fetchJobs]);

  const handleGenerate = useCallback(async (jobId: string) => {
    if (!activeCandidateId) {
      Alert.alert('Select a candidate', 'Choose a candidate before generating a cover letter.');
      return;
    }
    setActionLoading(`cover:${jobId}`);
    try {
      await generateCoverLetter(jobId, activeCandidateId);
      Alert.alert('Queued', 'Cover letter generation was queued.');
    } catch (generateError: any) {
      Alert.alert('Could not queue cover', generateError.response?.data?.detail || 'Try again after checking the API.');
    } finally {
      setActionLoading(null);
    }
  }, [activeCandidateId, generateCoverLetter]);

  const handleSend = useCallback((job: Job) => {
    if (!activeCandidateId) {
      Alert.alert('Select a candidate', 'Choose a candidate before sending.');
      return;
    }
    if (!job.hr_email || !job.cover_letter) {
      Alert.alert('Not ready', 'This job needs both an HR email and a generated cover letter.');
      return;
    }
    Alert.alert('Send application', `Send this application to ${job.hr_email}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Send',
        onPress: async () => {
          setActionLoading(`send:${job.id}`);
          try {
            await sendApplication(job.id, activeCandidateId);
            Alert.alert('Queued', 'Application send was queued.');
          } catch (sendError: any) {
            Alert.alert('Could not send', sendError.response?.data?.detail || 'Try again.');
          } finally {
            setActionLoading(null);
          }
        },
      },
    ]);
  }, [activeCandidateId, sendApplication]);

  const handleBulkGenerate = useCallback(async () => {
    if (!activeCandidateId || selected.size === 0) return;
    setActionLoading('bulk-cover');
    try {
      const queued = await bulkGenerateCovers([...selected], activeCandidateId);
      clearSelection();
      Alert.alert('Queued', `Cover generation queued for ${queued} job${queued === 1 ? '' : 's'}.`);
    } catch (bulkError: any) {
      Alert.alert('Bulk generation failed', bulkError.response?.data?.detail || 'Try again.');
    } finally {
      setActionLoading(null);
    }
  }, [activeCandidateId, selected, bulkGenerateCovers, clearSelection]);

  const handleBulkSend = useCallback(async () => {
    if (!activeCandidateId || selected.size === 0) return;
    Alert.alert('Send selected', `Send applications for ${selected.size} selected job${selected.size === 1 ? '' : 's'}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Send',
        onPress: async () => {
          setActionLoading('bulk-send');
          try {
            const queued = await bulkSendApplications([...selected], activeCandidateId);
            clearSelection();
            Alert.alert('Queued', `Application send queued for ${queued} job${queued === 1 ? '' : 's'}.`);
          } catch (bulkError: any) {
            Alert.alert('Bulk send failed', bulkError.response?.data?.detail || 'Try again.');
          } finally {
            setActionLoading(null);
          }
        },
      },
    ]);
  }, [activeCandidateId, selected, bulkSendApplications, clearSelection]);

  const applyPreset = useCallback((preset: 'ready' | 'recent') => {
    if (preset === 'ready') {
      setFilters({ has_hr_email: 'yes', has_cover: 'yes', status: 'cover_generated' });
    } else {
      setFilters({ scraped_after: daysAgoISO(7) });
    }
  }, [setFilters]);

  const handleLoadMore = useCallback(() => {
    if (!isFetchingMore && hasMore && !loading) {
      void loadMore();
    }
  }, [isFetchingMore, hasMore, loading, loadMore]);

  const activeFilterCount = useMemo(() => countActiveFilters(filters), [filters]);

  const renderItem = useCallback(({ item, index }: { item: Job; index: number }) => (
    <JobCard
      key={item.id}
      job={item}
      index={index}
      selected={selected.has(item.id)}
      onToggle={() => toggleSelect(item.id)}
      onOpen={() => navigation.navigate('JobDetail', { jobId: item.id })}
      onGenerate={() => void handleGenerate(item.id)}
      onSend={() => handleSend(item)}
      onSetHrEmail={(email) => setHrEmail(item.id, email)}
      actionLoading={actionLoading}
    />
  ), [selected, toggleSelect, navigation, handleGenerate, handleSend, setHrEmail, actionLoading]);

  const ListHeader = useMemo(() => (
    <View>
      {/* Search bar — always visible */}
      <View style={[styles.searchRow, { backgroundColor: colors.input, borderColor: colors.border }]}>
        <Ionicons name="search-outline" size={18} color={colors.textMuted} />
        <TextInput
          value={searchText}
          onChangeText={handleSearchChange}
          placeholder="Search jobs, companies, skills..."
          placeholderTextColor={colors.textMuted}
          style={[styles.searchInput, { color: colors.text }]}
          returnKeyType="search"
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
        />
        {searchText.length > 0 && (
          <Pressable onPress={() => handleSearchChange('')} hitSlop={8}>
            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
          </Pressable>
        )}
      </View>

      {/* Candidate selector chips */}
      {candidates.length > 0 ? (
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipRow}
          data={candidates}
          keyExtractor={(c) => c.id}
          renderItem={({ item }) => (
            <FilterChip
              label={item.name}
              active={item.id === activeCandidateId}
              onPress={() => setActiveCandidate(item.id)}
              icon="person-outline"
            />
          )}
        />
      ) : null}

      {/* Quick preset chips */}
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipRow}
        data={[
          {
            label: 'Ready to Apply',
            active: filters.status === 'cover_generated' && filters.has_hr_email === 'yes',
            onPress: () => applyPreset('ready'),
          },
          {
            label: 'Last 7 days',
            active: filters.scraped_after === daysAgoISO(7),
            onPress: () => applyPreset('recent'),
          },
          {
            label: 'Clear filters',
            active: false,
            onPress: () => { setSearchText(''); resetFilters(); },
            icon: 'close-outline' as const,
          },
        ]}
        keyExtractor={(_, i) => i.toString()}
        renderItem={({ item }) => (
          <FilterChip label={item.label} active={item.active} onPress={item.onPress} icon={item.icon} />
        )}
      />

      {/* Count row */}
      <View style={styles.countRow}>
        <Text style={[styles.countText, { color: colors.textMuted }]}>
          {loading ? 'Loading…' : `${totalCount} job${totalCount !== 1 ? 's' : ''}`}
        </Text>
        {activeFilterCount > 0 && (
          <View style={[styles.filterBadge, { backgroundColor: colors.primary }]}>
            <Text style={styles.filterBadgeText}>{activeFilterCount} filter{activeFilterCount !== 1 ? 's' : ''} active</Text>
          </View>
        )}
      </View>

      {error ? <ScreenError message={error} onRetry={() => void fetchJobs()} /> : null}
    </View>
  ), [
    colors, searchText, handleSearchChange, candidates, activeCandidateId, setActiveCandidate,
    filters, applyPreset, resetFilters, totalCount, loading, error, fetchJobs, activeFilterCount,
  ]);

  const ListFooter = useMemo(() => {
    if (isFetchingMore) {
      return (
        <View style={styles.footerLoader}>
          <ActivityIndicator color={colors.primary} />
          <Text style={[styles.footerText, { color: colors.textMuted }]}>Loading more…</Text>
        </View>
      );
    }
    if (!hasMore && jobs.length > 0 && !loading) {
      return (
        <Text style={[styles.footerText, styles.footerEnd, { color: colors.textMuted }]}>
          All {totalCount} jobs loaded
        </Text>
      );
    }
    return <View style={styles.footerSpacer} />;
  }, [isFetchingMore, hasMore, jobs.length, loading, totalCount, colors]);

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        {/* Header */}
        <PageHeader
          title="Jobs"
          action={
            <AppButton
              label="Filters"
              icon="options-outline"
              variant="secondary"
              onPress={() => setShowFilters(true)}
              style={styles.filterButton}
              badge={activeFilterCount}
            />
          }
        />

        <FlatList
          data={jobs}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          ListHeaderComponent={ListHeader}
          ListFooterComponent={ListFooter}
          ListEmptyComponent={
            !loading && !error ? (
              <EmptyState
                title="No jobs match"
                message="Try clearing filters or run a fresh search."
                icon="briefcase-outline"
              />
            ) : null
          }
          ItemSeparatorComponent={() => <View style={{ height: 14 }} />}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.4}
          removeClippedSubviews
          maxToRenderPerBatch={10}
          windowSize={10}
        />

        {/* Sticky bulk action bar */}
        {selected.size > 0 && (
          <View style={[styles.bulkBar, { backgroundColor: colors.glassStrong, borderTopColor: colors.border }]}>
            <View style={styles.bulkBarInner}>
              <Text style={[styles.bulkCount, { color: colors.text }]}>{selected.size} selected</Text>
              <View style={styles.bulkActions}>
                <AppButton
                  label="Covers"
                  icon="sparkles-outline"
                  variant="secondary"
                  onPress={handleBulkGenerate}
                  loading={actionLoading === 'bulk-cover'}
                  style={styles.bulkBtn}
                />
                <AppButton
                  label="Send"
                  icon="send-outline"
                  onPress={handleBulkSend}
                  loading={actionLoading === 'bulk-send'}
                  style={styles.bulkBtn}
                />
              </View>
            </View>
            <View style={styles.bulkLinks}>
              <Pressable onPress={() => void selectAllMatching()}>
                <Text style={[styles.linkText, { color: colors.primary }]}>Select all {totalCount} matching</Text>
              </Pressable>
              <Pressable onPress={clearSelection}>
                <Text style={[styles.linkText, { color: colors.error }]}>Clear</Text>
              </Pressable>
            </View>
          </View>
        )}

        <FiltersModal
          visible={showFilters}
          filters={filters}
          onClose={() => setShowFilters(false)}
          onApply={(nextFilters) => {
            setFilters(nextFilters);
            setShowFilters(false);
          }}
          onSelectAllPage={selectAllPage}
        />
      </SafeAreaView>
    </SVGBackground>
  );
}

const JobCard = React.memo(function JobCard({
  job,
  index,
  selected,
  onToggle,
  onOpen,
  onGenerate,
  onSend,
  onSetHrEmail,
  actionLoading,
}: {
  job: Job;
  index: number;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
  onGenerate: () => void;
  onSend: () => void;
  onSetHrEmail: (email: string) => Promise<void>;
  actionLoading: string | null;
}) {
  const { colors } = useTheme();
  const salary = formatSalary(job);

  return (
    <GlassCard delay={index * 35} style={selected ? { borderColor: colors.primary, borderWidth: 2 } : undefined}>
      <Pressable onPress={onOpen}>
        <View style={styles.jobHeader}>
          <View style={styles.jobTitleWrap}>
            <Text style={[styles.jobTitle, { color: colors.text }]} numberOfLines={2}>
              {job.job_title}
            </Text>
            <Text style={[styles.company, { color: colors.textMuted }]} numberOfLines={1}>
              {job.company}
            </Text>
          </View>
          <StatusPill label={humanize(job.status)} tone={jobStatusTone(job.status)} compact />
        </View>

        <View style={styles.jobMetaWrap}>
          {job.location ? <Meta icon="location-outline" label={job.location} /> : null}
          <Meta icon="stats-chart-outline" label={formatScore(job)} />
          {salary ? <Meta icon="cash-outline" label={salary} /> : null}
          {job.source_portal ? <Meta icon="compass-outline" label={job.source_portal} /> : null}
          {job.scraped_at ? <Meta icon="calendar-outline" label={formatDate(job.scraped_at)} /> : null}
        </View>

        <View style={styles.jobCapabilities}>
          <StatusPill label={job.cover_letter ? 'Cover ready' : 'No cover'} tone={job.cover_letter ? 'cyan' : 'neutral'} compact />
          {job.hr_email ? <StatusPill label="HR email set" tone="mint" compact /> : null}
        </View>
      </Pressable>

      <InlineEditField
        label="HR Email"
        value={job.hr_email}
        placeholder="Set HR email..."
        keyboardType="email-address"
        onSave={onSetHrEmail}
      />

      <View style={[styles.jobActions, { borderTopColor: colors.border }]}>
        <Pressable onPress={onToggle} style={styles.selectAction} hitSlop={8}>
          <Ionicons name={selected ? 'checkbox' : 'square-outline'} color={selected ? colors.primary : colors.textMuted} size={24} />
          <Text style={[styles.selectText, { color: selected ? colors.primary : colors.textMuted }]}>
            {selected ? 'Selected' : 'Select'}
          </Text>
        </Pressable>
        <AppButton
          label="Cover"
          icon="sparkles-outline"
          variant="secondary"
          loading={actionLoading === `cover:${job.id}`}
          onPress={onGenerate}
          style={styles.smallAction}
        />
        <AppButton
          label="Send"
          icon="send-outline"
          disabled={!job.hr_email || !job.cover_letter}
          loading={actionLoading === `send:${job.id}`}
          onPress={onSend}
          style={styles.smallAction}
        />
      </View>
    </GlassCard>
  );
});

const Meta = React.memo(function Meta({ icon, label }: { icon: keyof typeof Ionicons.glyphMap; label: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.metaItem}>
      <Ionicons name={icon} size={12} color={colors.textMuted} />
      <Text style={[styles.metaText, { color: colors.textMuted }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
});

// Collapsible accordion section inside the filter modal
function FilterSection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <View style={filterStyles.section}>
      <Pressable onPress={() => setOpen((v) => !v)} style={filterStyles.sectionToggle}>
        <Text style={[filterStyles.sectionTitle, { color: colors.textSecondary }]}>{title}</Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
      </Pressable>
      {open ? <View style={filterStyles.wrapRow}>{children}</View> : null}
    </View>
  );
}

const FiltersModal = React.memo(function FiltersModal({
  visible,
  filters,
  onClose,
  onApply,
  onSelectAllPage,
}: {
  visible: boolean;
  filters: JobFilters;
  onClose: () => void;
  onApply: (filters: Partial<JobFilters>) => void;
  onSelectAllPage: () => void;
}) {
  const { colors } = useTheme();
  const [local, setLocal] = useState<JobFilters>(filters);

  useEffect(() => {
    setLocal(filters);
  }, [filters, visible]);

  const handleClear = () => {
    setLocal(DEFAULT_FILTERS);
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <SVGBackground>
        <SafeAreaView style={filterStyles.safeArea}>
          <View style={[filterStyles.header, { borderBottomColor: colors.border }]}>
            <View>
              <Text style={[filterStyles.eyebrow, { color: colors.textMuted }]}>Refine results</Text>
              <Text style={[filterStyles.title, { color: colors.text }]}>Filters</Text>
            </View>
            <Pressable onPress={onClose} style={[filterStyles.closeBtn, { backgroundColor: colors.input, borderColor: colors.border }]}>
              <Ionicons name="close-outline" size={22} color={colors.text} />
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={filterStyles.content} showsVerticalScrollIndicator={false}>
            <FilterSection title="Status">
              <FilterChip label="All" active={!local.status} onPress={() => setLocal({ ...local, status: '' })} />
              {STATUSES.map((s) => (
                <FilterChip key={s} label={humanize(s)} active={local.status === s} onPress={() => setLocal({ ...local, status: s })} />
              ))}
            </FilterSection>

            <FilterSection title="Portal">
              <FilterChip label="All" active={!local.portal} onPress={() => setLocal({ ...local, portal: '' })} />
              {PORTALS.map((p) => (
                <FilterChip key={p} label={p} active={local.portal === p} onPress={() => setLocal({ ...local, portal: p })} />
              ))}
            </FilterSection>

            <FilterSection title="Job Type">
              <FilterChip label="Any" active={!local.job_type} onPress={() => setLocal({ ...local, job_type: '' })} />
              {JOB_TYPES.map((jt) => (
                <FilterChip key={jt} label={jt} active={local.job_type === jt} onPress={() => setLocal({ ...local, job_type: jt })} />
              ))}
            </FilterSection>

            <FilterSection title="Readiness" defaultOpen={false}>
              <FilterChip label="Any HR email" active={!local.has_hr_email} onPress={() => setLocal({ ...local, has_hr_email: '' })} />
              <FilterChip label="Has HR email" active={local.has_hr_email === 'yes'} onPress={() => setLocal({ ...local, has_hr_email: 'yes' })} />
              <FilterChip label="No HR email" active={local.has_hr_email === 'no'} onPress={() => setLocal({ ...local, has_hr_email: 'no' })} />
              <FilterChip label="Has cover" active={local.has_cover === 'yes'} onPress={() => setLocal({ ...local, has_cover: 'yes' })} />
              <FilterChip label="No cover" active={local.has_cover === 'no'} onPress={() => setLocal({ ...local, has_cover: 'no' })} />
            </FilterSection>

            <FilterSection title="Scraped After" defaultOpen={false}>
              <FilterChip label="Any time" active={!local.scraped_after} onPress={() => setLocal({ ...local, scraped_after: '' })} />
              <FilterChip label="Today" active={local.scraped_after === todayISO()} onPress={() => setLocal({ ...local, scraped_after: todayISO() })} />
              <FilterChip label="Last 7 days" active={local.scraped_after === daysAgoISO(7)} onPress={() => setLocal({ ...local, scraped_after: daysAgoISO(7) })} />
              <FilterChip label="Last 30 days" active={local.scraped_after === daysAgoISO(30)} onPress={() => setLocal({ ...local, scraped_after: daysAgoISO(30) })} />
            </FilterSection>

            <FilterSection title="Posted After" defaultOpen={false}>
              <FilterChip label="Any time" active={!local.posted_after} onPress={() => setLocal({ ...local, posted_after: '' })} />
              <FilterChip label="Today" active={local.posted_after === todayISO()} onPress={() => setLocal({ ...local, posted_after: todayISO() })} />
              <FilterChip label="Last 7 days" active={local.posted_after === daysAgoISO(7)} onPress={() => setLocal({ ...local, posted_after: daysAgoISO(7) })} />
              <FilterChip label="Last 30 days" active={local.posted_after === daysAgoISO(30)} onPress={() => setLocal({ ...local, posted_after: daysAgoISO(30) })} />
            </FilterSection>

            <FilterSection title="Min Score" defaultOpen={false}>
              <TextInput
                value={local.min_score > 0 ? String(local.min_score) : ''}
                onChangeText={(v) => setLocal({ ...local, min_score: Math.min(100, Math.max(0, Number(v) || 0)) })}
                placeholder="0–100"
                keyboardType="number-pad"
                placeholderTextColor={colors.textMuted}
                style={[filterStyles.input, { backgroundColor: colors.input, borderColor: colors.border, color: colors.text }]}
              />
            </FilterSection>

            <FilterSection title="Sort" defaultOpen={false}>
              {(['scraped_at', 'relevance_score', 'company', 'job_title'] as const).map((sort) => (
                <FilterChip key={sort} label={humanize(sort)} active={local.sort_by === sort} onPress={() => setLocal({ ...local, sort_by: sort })} />
              ))}
              <FilterChip label="Descending" active={local.sort_dir === 'desc'} onPress={() => setLocal({ ...local, sort_dir: 'desc' })} />
              <FilterChip label="Ascending" active={local.sort_dir === 'asc'} onPress={() => setLocal({ ...local, sort_dir: 'asc' })} />
            </FilterSection>

            <View style={[filterStyles.actions, { backgroundColor: colors.glass, borderColor: colors.border }]}>
              <AppButton label="Select page" icon="checkbox-outline" variant="secondary" onPress={onSelectAllPage} style={filterStyles.actionBtn} />
              <AppButton label="Clear all" icon="close-outline" variant="danger" onPress={handleClear} style={filterStyles.actionBtn} />
              <AppButton label="Apply" icon="checkmark-outline" onPress={() => onApply(local)} style={filterStyles.applyBtn} />
            </View>
          </ScrollView>
        </SafeAreaView>
      </SVGBackground>
    </Modal>
  );
});

// Separate StyleSheet for filter modal to keep it organized
const filterStyles = StyleSheet.create({
  safeArea: { flex: 1 },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 20,
    paddingBottom: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  eyebrow: { fontSize: 11, fontWeight: '900', marginBottom: 3, textTransform: 'uppercase' },
  title: { fontSize: 28, fontWeight: '900' },
  closeBtn: {
    alignItems: 'center',
    borderRadius: 18,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  content: { padding: 20, paddingBottom: 40 },
  section: { marginBottom: 4 },
  sectionToggle: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  wrapRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingBottom: 8,
  },
  input: {
    borderRadius: 16,
    borderWidth: 1,
    fontSize: 14,
    fontWeight: '700',
    minHeight: 48,
    paddingHorizontal: 14,
    width: '100%',
  },
  actions: {
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginTop: 24,
    padding: 12,
  },
  actionBtn: { minWidth: 110 },
  applyBtn: { flex: 1, minWidth: 140 },
});

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  staticHeader: {
    paddingHorizontal: 20,
  },
  filterButton: { minHeight: 44, minWidth: 104 },
  searchRow: {
    alignItems: 'center',
    borderRadius: 19,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
  },
  chipRow: { gap: 8, paddingBottom: 16 },
  countRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  countText: { fontSize: 13, fontWeight: '700' },
  filterBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  filterBadgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  content: { padding: 20, paddingBottom: 176 },
  jobHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
  jobTitleWrap: { flex: 1 },
  jobTitle: { fontSize: 17, fontWeight: '900', lineHeight: 23, marginBottom: 4 },
  company: { fontSize: 13, fontWeight: '700' },
  jobMetaWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 14 },
  metaItem: { alignItems: 'center', flexDirection: 'row', gap: 4, maxWidth: '48%' },
  metaText: { fontSize: 11, fontWeight: '700' },
  jobCapabilities: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
  jobActions: {
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
    paddingTop: 14,
  },
  selectAction: { alignItems: 'center', flexDirection: 'row', gap: 6, marginRight: 'auto' },
  selectText: { fontSize: 12, fontWeight: '800' },
  smallAction: { minHeight: 40, minWidth: 82 },
  footerLoader: { alignItems: 'center', flexDirection: 'row', gap: 10, justifyContent: 'center', paddingVertical: 20 },
  footerText: { fontSize: 13, fontWeight: '700', textAlign: 'center' },
  footerEnd: { paddingVertical: 20 },
  footerSpacer: { height: 20 },
  bulkBar: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingBottom: 30,
    paddingHorizontal: 20,
    paddingTop: 14,
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
  },
  bulkBarInner: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  bulkCount: { fontSize: 16, fontWeight: '900' },
  bulkActions: { flexDirection: 'row', gap: 8 },
  bulkBtn: { minHeight: 40, minWidth: 90 },
  bulkLinks: { flexDirection: 'row', gap: 18, marginTop: 10 },
  linkText: { fontSize: 12, fontWeight: '800' },
});
