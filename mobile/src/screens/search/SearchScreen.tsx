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
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, EmptyState, FilterChip, GlassCard, PageHeader, ScreenError, SectionHeader, SkeletonBlock, StatusPill } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useCandidatesStore } from '../../store/candidatesStore';
import apiService from '../../services/api';
import { SearchTask } from '../../types';
import { formatRelative } from '../../utils/format';

const PORTALS = [
  'naukri', 'indeed', 'glassdoor', 'linkedin', 'angellist',
  'shine', 'timesjobs', 'foundit', 'internshala', 'cutshort',
  'instahyre', 'wellfound', 'remoteok', 'remotive',
];

const PORTAL_PRESETS: Record<string, string[]> = {
  India: ['naukri', 'shine', 'foundit', 'timesjobs', 'internshala'],
  International: ['linkedin', 'indeed', 'glassdoor', 'wellfound', 'remoteok', 'remotive'],
  Startup: ['angellist', 'cutshort', 'instahyre', 'wellfound'],
};

export default function SearchScreen() {
  const { colors } = useTheme();
  const { candidates, activeCandidateId, setActiveCandidate, fetchCandidates } = useCandidatesStore();
  const [jobTitleInput, setJobTitleInput] = useState('');
  const [locationInput, setLocationInput] = useState('');
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>(['India']);
  const [portals, setPortals] = useState<string[]>(['naukri', 'indeed']);
  const [maxResults, setMaxResults] = useState('50');
  const [autoCovers, setAutoCovers] = useState(true);
  const [recentTasks, setRecentTasks] = useState<SearchTask[]>([]);
  const [taskId, setTaskId] = useState('');
  const [taskStatus, setTaskStatus] = useState<SearchTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPortalModal, setShowPortalModal] = useState(false);
  const [portalSearch, setPortalSearch] = useState('');
  // Inline validation errors
  const [validationErrors, setValidationErrors] = useState<{ candidate?: string; titles?: string; portals?: string }>({});

  const activeCandidate = useMemo(
    () => candidates.find((c) => c.id === activeCandidateId),
    [activeCandidateId, candidates]
  );

  const loadSearchData = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const [tasks] = await Promise.all([apiService.getSearchTasks(10), fetchCandidates()]);
      setRecentTasks(tasks);
    } catch (loadError: any) {
      setError(loadError.response?.data?.detail || 'Failed to load search tasks');
    } finally {
      setLoading(false);
    }
  }, [fetchCandidates]);

  useEffect(() => { void loadSearchData(true); }, [loadSearchData]);

  const loadSearchDataRef = useRef(loadSearchData);
  loadSearchDataRef.current = loadSearchData;

  // Poll running task
  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let delay = 2000;

    const poll = async () => {
      if (cancelled) return;
      try {
        const task = await apiService.getSearchTask(taskId);
        setTaskStatus(task);
        if (task.status === 'completed' || task.status === 'error') {
          void loadSearchDataRef.current(false);
          return;
        }
      } catch { /* keep retrying */ }
      delay = Math.min(delay * 2, 15000);
      timeoutId = setTimeout(poll, delay);
    };
    timeoutId = setTimeout(poll, delay);
    return () => { cancelled = true; if (timeoutId) clearTimeout(timeoutId); };
  }, [taskId]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadSearchData(false);
    setRefreshing(false);
  };

  const addTag = (value: string, list: string[], setList: (items: string[]) => void, clear: () => void) => {
    const trimmed = value.trim();
    if (!trimmed || list.includes(trimmed)) return;
    setList([...list, trimmed]);
    clear();
  };

  const togglePortal = (portal: string) => {
    setPortals((cur) => cur.includes(portal) ? cur.filter((p) => p !== portal) : [...cur, portal]);
  };

  const applyPortalPreset = (presetName: string) => {
    setPortals(PORTAL_PRESETS[presetName] ?? []);
  };

  const handleStartSearch = async () => {
    const titles = jobTitles.length ? jobTitles : jobTitleInput.trim() ? [jobTitleInput.trim()] : [];
    const errors: typeof validationErrors = {};
    if (!activeCandidateId) errors.candidate = 'Select a candidate before searching.';
    if (!titles.length) errors.titles = 'Add at least one job title to search for.';
    if (!portals.length) errors.portals = 'Select at least one portal.';

    setValidationErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const locs = locations.length ? locations : locationInput.trim() ? [locationInput.trim()] : ['India'];
    setSubmitting(true);
    setTaskStatus(null);
    try {
      const result = await apiService.triggerSearch({
        job_titles: titles,
        locations: locs,
        portals,
        max_results_per_portal: Math.min(500, Math.max(1, Number(maxResults) || 50)),
        candidate_id: activeCandidateId!,
        auto_generate_covers: autoCovers,
      });
      setTaskId(result.task_id);
      setValidationErrors({});
      Alert.alert('Search started', result.message);
      await loadSearchData(false);
    } catch (submitError: any) {
      Alert.alert('Search failed', submitError.response?.data?.detail || 'Failed to start search');
    } finally {
      setSubmitting(false);
    }
  };

  const filteredPortals = useMemo(
    () => PORTALS.filter((p) => !portalSearch || p.includes(portalSearch.toLowerCase())),
    [portalSearch]
  );

  const isTaskRunning = taskStatus && (taskStatus.status === 'running' || taskStatus.status === 'queued');

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.loadingContent}>
          <SkeletonBlock width="54%" height={34} radius={17} />
          <GlassCard style={styles.loadingCard}>
            <SkeletonBlock width="40%" height={18} />
            <SkeletonBlock width="100%" height={52} radius={18} style={styles.loadingGap} />
            <SkeletonBlock width="82%" height={52} radius={18} style={styles.loadingGap} />
            <SkeletonBlock width="62%" height={52} radius={18} style={styles.loadingGap} />
          </GlassCard>
          <ActivityIndicator color={colors.primary} size="small" style={styles.loadingSpinner} />
          <Text style={[styles.centerText, { color: colors.textMuted }]}>Loading search</Text>
        </View>
      </SVGBackground>
    );
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        {/* Sticky task progress banner */}
        {isTaskRunning && (
          <View style={[styles.taskBanner, { backgroundColor: colors.glassStrong, borderBottomColor: colors.border }]}>
            <ActivityIndicator size="small" color={colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={[styles.taskBannerTitle, { color: colors.text }]} numberOfLines={1}>
                Searching: {taskStatus!.job_titles.join(', ')}
              </Text>
              <Text style={[styles.taskBannerSub, { color: colors.textMuted }]}>
                {taskStatus!.tasks_completed}/{taskStatus!.tasks_total} portals · {taskStatus!.jobs_found} found
              </Text>
            </View>
            <StatusPill label={taskStatus!.status} tone="cyan" compact />
          </View>
        )}

        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          <PageHeader
            title="New Search"
            action={
              <FilterChip
                label="Auto covers"
                active={autoCovers}
                onPress={() => setAutoCovers((v) => !v)}
                icon={autoCovers ? 'checkmark-circle-outline' : 'ellipse-outline'}
              />
            }
          />

          {error ? <ScreenError message={error} onRetry={() => void loadSearchData(true)} /> : null}

          <GlassCard style={styles.formCard}>
            {/* Candidate */}
            <SectionHeader title="Candidate" subtitle={activeCandidate?.email || 'Required'} />
            {validationErrors.candidate ? (
              <Text style={[styles.fieldError, { color: colors.error }]}>{validationErrors.candidate}</Text>
            ) : null}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
              {candidates.map((c) => (
                <FilterChip
                  key={c.id}
                  label={c.name}
                  active={c.id === activeCandidateId}
                  onPress={() => { setActiveCandidate(c.id); setValidationErrors((e) => ({ ...e, candidate: undefined })); }}
                  icon="person-outline"
                />
              ))}
            </ScrollView>

            {/* Job Titles */}
            <FormInput
              label="Job Titles"
              value={jobTitleInput}
              onChangeText={setJobTitleInput}
              placeholder="e.g. React Native Developer"
              onAdd={() => {
                addTag(jobTitleInput, jobTitles, setJobTitles, () => setJobTitleInput(''));
                setValidationErrors((e) => ({ ...e, titles: undefined }));
              }}
              error={validationErrors.titles}
            />
            <TagRow tags={jobTitles} onRemove={(tag) => setJobTitles(jobTitles.filter((t) => t !== tag))} />

            {/* Locations */}
            <FormInput
              label="Locations"
              value={locationInput}
              onChangeText={setLocationInput}
              placeholder="e.g. Bangalore or Remote"
              onAdd={() => addTag(locationInput, locations, setLocations, () => setLocationInput(''))}
            />
            <TagRow tags={locations} onRemove={(tag) => setLocations(locations.filter((t) => t !== tag))} />

            {/* Portals */}
            <View style={styles.portalsHeader}>
              <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>Portals ({portals.length} selected)</Text>
              <Pressable onPress={() => setShowPortalModal(true)} hitSlop={8}>
                <Text style={[styles.editPortals, { color: colors.primary }]}>Edit →</Text>
              </Pressable>
            </View>
            {validationErrors.portals ? (
              <Text style={[styles.fieldError, { color: colors.error }]}>{validationErrors.portals}</Text>
            ) : null}
            {/* Portal preset quick-select */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowSm}>
              {Object.keys(PORTAL_PRESETS).map((preset) => (
                <FilterChip
                  key={preset}
                  label={preset}
                  active={JSON.stringify(portals.slice().sort()) === JSON.stringify((PORTAL_PRESETS[preset] ?? []).slice().sort())}
                  onPress={() => applyPortalPreset(preset)}
                />
              ))}
            </ScrollView>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowSm}>
              {portals.map((p) => (
                <FilterChip key={p} label={p} active onPress={() => togglePortal(p)} icon="close-outline" />
              ))}
            </ScrollView>

            {/* Max Results */}
            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>Max results per portal</Text>
            <TextInput
              value={maxResults}
              onChangeText={setMaxResults}
              keyboardType="number-pad"
              style={[styles.input, { backgroundColor: colors.input, borderColor: colors.border, color: colors.text }]}
              placeholderTextColor={colors.textMuted}
              placeholder="50"
            />

            <AppButton
              label={submitting ? 'Starting…' : 'Start Search'}
              icon="search-outline"
              loading={submitting}
              onPress={handleStartSearch}
              style={styles.startButton}
            />
          </GlassCard>

          {/* Non-running task status */}
          {taskStatus && !isTaskRunning && (
            <>
              <SectionHeader title="Last Task" />
              <GlassCard>
                <View style={styles.taskHeader}>
                  <View style={styles.taskText}>
                    <Text style={[styles.taskTitle, { color: colors.text }]}>{taskStatus.job_titles.join(', ') || 'Search task'}</Text>
                    <Text style={[styles.taskSubtitle, { color: colors.textMuted }]}>
                      {taskStatus.tasks_completed}/{taskStatus.tasks_total} portals · {taskStatus.jobs_found} jobs found
                    </Text>
                  </View>
                  <StatusPill
                    label={taskStatus.status}
                    tone={taskStatus.status === 'error' ? 'coral' : 'mint'}
                  />
                </View>
                {taskStatus.error ? <Text style={[styles.errorText, { color: colors.error }]}>{taskStatus.error}</Text> : null}
              </GlassCard>
            </>
          )}

          <SectionHeader title="Recent Searches" />
          {recentTasks.length === 0 ? (
            <EmptyState title="No searches yet" message="Start a search and its progress will show here." icon="search-outline" />
          ) : (
            <View style={styles.stack}>
              {recentTasks.map((task, index) => (
                <GlassCard key={task.id} delay={index * 40}>
                  <View style={styles.taskHeader}>
                    <View style={styles.taskText}>
                      <Text style={[styles.taskTitle, { color: colors.text }]} numberOfLines={1}>
                        {task.job_titles.join(', ') || 'Search task'}
                      </Text>
                      <Text style={[styles.taskSubtitle, { color: colors.textMuted }]} numberOfLines={2}>
                        {task.locations.join(', ') || 'Any location'} · {task.portals.length} portals · {task.jobs_found} found
                      </Text>
                      <Text style={[styles.taskMeta, { color: colors.textMuted }]}>{formatRelative(task.created_at)}</Text>
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
        </ScrollView>

        {/* Portal selection modal */}
        <PortalModal
          visible={showPortalModal}
          selected={portals}
          onToggle={togglePortal}
          onClose={() => setShowPortalModal(false)}
          search={portalSearch}
          onSearch={setPortalSearch}
          filteredPortals={filteredPortals}
        />
      </SafeAreaView>
    </SVGBackground>
  );
}

function PortalModal({
  visible, selected, onToggle, onClose, search, onSearch, filteredPortals,
}: {
  visible: boolean;
  selected: string[];
  onToggle: (portal: string) => void;
  onClose: () => void;
  search: string;
  onSearch: (v: string) => void;
  filteredPortals: string[];
}) {
  const { colors } = useTheme();
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <SVGBackground>
        <SafeAreaView style={{ flex: 1 }}>
          <View style={portalModalStyles.header}>
            <Text style={[portalModalStyles.title, { color: colors.text }]}>Select Portals</Text>
            <Pressable onPress={onClose} style={[portalModalStyles.closeBtn, { backgroundColor: colors.input, borderColor: colors.border }]}>
              <Ionicons name="close-outline" size={22} color={colors.text} />
            </Pressable>
          </View>

          {/* Preset buttons */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={portalModalStyles.presets}>
            {Object.keys(PORTAL_PRESETS).map((preset) => (
              <Pressable
                key={preset}
                onPress={() => {
                  const presetPortals = PORTAL_PRESETS[preset] ?? [];
                  presetPortals.forEach((p) => {
                    if (!selected.includes(p)) onToggle(p);
                  });
                }}
                style={[portalModalStyles.presetBtn, { backgroundColor: colors.input, borderColor: colors.border }]}
              >
                <Text style={[portalModalStyles.presetLabel, { color: colors.primary }]}>{preset}</Text>
              </Pressable>
            ))}
            <Pressable
              onPress={() => { PORTALS.forEach((p) => { if (!selected.includes(p)) onToggle(p); }); }}
              style={[portalModalStyles.presetBtn, { backgroundColor: colors.input, borderColor: colors.border }]}
            >
              <Text style={[portalModalStyles.presetLabel, { color: colors.primary }]}>All</Text>
            </Pressable>
            <Pressable
              onPress={() => { PORTALS.forEach((p) => { if (selected.includes(p)) onToggle(p); }); }}
              style={[portalModalStyles.presetBtn, { backgroundColor: colors.input, borderColor: colors.border }]}
            >
              <Text style={[portalModalStyles.presetLabel, { color: colors.error }]}>Clear</Text>
            </Pressable>
          </ScrollView>

          <View style={[portalModalStyles.searchRow, { backgroundColor: colors.input, borderColor: colors.border }]}>
            <Ionicons name="search-outline" size={16} color={colors.textMuted} />
            <TextInput
              value={search}
              onChangeText={onSearch}
              placeholder="Search portals…"
              placeholderTextColor={colors.textMuted}
              style={[portalModalStyles.searchInput, { color: colors.text }]}
              autoCapitalize="none"
            />
          </View>

          <FlatList
            data={filteredPortals}
            keyExtractor={(p) => p}
            contentContainerStyle={{ paddingBottom: 40 }}
            renderItem={({ item: portal }) => {
              const isSelected = selected.includes(portal);
              return (
                <Pressable
                  onPress={() => onToggle(portal)}
                  style={({ pressed }) => [
                    portalModalStyles.portalRow,
                    { borderBottomColor: colors.border, opacity: pressed ? 0.7 : 1 },
                  ]}
                >
                  <Ionicons
                    name={isSelected ? 'checkbox' : 'square-outline'}
                    size={22}
                    color={isSelected ? colors.primary : colors.textMuted}
                  />
                  <Text style={[portalModalStyles.portalName, { color: isSelected ? colors.text : colors.textSecondary }]}>
                    {portal}
                  </Text>
                  {isSelected && <Ionicons name="checkmark" size={16} color={colors.primary} />}
                </Pressable>
              );
            }}
          />

          <View style={[portalModalStyles.footer, { borderTopColor: colors.border }]}>
            <Text style={[portalModalStyles.selectedCount, { color: colors.textMuted }]}>
              {selected.length} portal{selected.length !== 1 ? 's' : ''} selected
            </Text>
            <AppButton label="Done" icon="checkmark-outline" onPress={onClose} style={{ minWidth: 100 }} />
          </View>
        </SafeAreaView>
      </SVGBackground>
    </Modal>
  );
}

const portalModalStyles = StyleSheet.create({
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', padding: 20, paddingBottom: 12 },
  title: { fontSize: 24, fontWeight: '900' },
  closeBtn: { alignItems: 'center', borderRadius: 18, borderWidth: 1, height: 40, justifyContent: 'center', width: 40 },
  presets: { gap: 8, paddingHorizontal: 20, paddingBottom: 12 },
  presetBtn: { borderRadius: 999, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 8 },
  presetLabel: { fontSize: 13, fontWeight: '800' },
  searchRow: {
    alignItems: 'center',
    borderRadius: 17,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginHorizontal: 20,
    marginBottom: 8,
    minHeight: 46,
    paddingHorizontal: 12,
  },
  searchInput: { flex: 1, fontSize: 14, fontWeight: '600' },
  portalRow: {
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 14,
    paddingHorizontal: 20,
    paddingVertical: 14,
  },
  portalName: { flex: 1, fontSize: 15, fontWeight: '700' },
  footer: { alignItems: 'center', borderTopWidth: StyleSheet.hairlineWidth, flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14 },
  selectedCount: { fontSize: 14, fontWeight: '700' },
});

function FormInput({
  label, value, placeholder, onChangeText, onAdd, error,
}: {
  label: string; value: string; placeholder: string;
  onChangeText: (v: string) => void; onAdd: () => void; error?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.inputGroup}>
      <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>{label}</Text>
      {error ? <Text style={[styles.fieldError, { color: colors.error }]}>{error}</Text> : null}
      <View style={styles.inputRow}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={colors.textMuted}
          style={[
            styles.input, styles.inputFlex,
            { backgroundColor: colors.input, borderColor: error ? colors.error : colors.border, color: colors.text },
          ]}
          returnKeyType="done"
          onSubmitEditing={onAdd}
        />
        <AppButton label="Add" onPress={onAdd} variant="secondary" style={styles.addButton} />
      </View>
    </View>
  );
}

function TagRow({ tags, onRemove }: { tags: string[]; onRemove: (tag: string) => void }) {
  if (!tags.length) return null;
  return (
    <View style={styles.wrapRow}>
      {tags.map((tag) => (
        <FilterChip key={tag} label={tag} active onPress={() => onRemove(tag)} icon="close-outline" />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 152 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  loadingContent: { flex: 1, justifyContent: 'center', padding: 20 },
  loadingCard: { marginTop: 22 },
  loadingGap: { marginTop: 14 },
  loadingSpinner: { marginTop: 20 },
  centerText: { fontSize: 14, fontWeight: '700', marginTop: 14 },
  taskBanner: {
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  taskBannerTitle: { fontSize: 13, fontWeight: '900' },
  taskBannerSub: { fontSize: 11, fontWeight: '800', marginTop: 2 },
  formCard: { marginBottom: 24 },
  chipRow: { gap: 8, paddingBottom: 16 },
  chipRowSm: { gap: 8, paddingBottom: 10 },
  portalsHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6, marginTop: 4 },
  editPortals: { fontSize: 13, fontWeight: '800' },
  fieldError: { fontSize: 12, fontWeight: '700', marginBottom: 6 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  inputGroup: { marginBottom: 14 },
  inputLabel: { fontSize: 12, fontWeight: '800', marginBottom: 8, marginTop: 2, textTransform: 'uppercase' },
  inputRow: { alignItems: 'center', flexDirection: 'row', gap: 10 },
  input: { borderRadius: 17, borderWidth: 1, fontSize: 14, fontWeight: '700', minHeight: 50, paddingHorizontal: 14 },
  inputFlex: { flex: 1 },
  addButton: { minHeight: 48, width: 72 },
  startButton: { marginTop: 12, minHeight: 52 },
  taskHeader: { alignItems: 'flex-start', flexDirection: 'row', gap: 12, justifyContent: 'space-between' },
  taskText: { flex: 1 },
  taskTitle: { fontSize: 15, fontWeight: '900', marginBottom: 5 },
  taskSubtitle: { fontSize: 12, fontWeight: '700', lineHeight: 17 },
  taskMeta: { fontSize: 11, fontWeight: '700', marginTop: 6 },
  errorText: { fontSize: 12, fontWeight: '700', marginTop: 12 },
  stack: { gap: 12 },
});
