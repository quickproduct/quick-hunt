import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { RouteProp, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, EmptyState, GlassCard, KeyValueRow, ScreenError, SectionHeader, StatusPill } from '../../components/GlassKit';
import InlineEditField from '../../components/InlineEditField';
import { useTheme } from '../../context/ThemeContext';
import { JobsStackParamList } from '../../navigation/AppNavigator';
import apiService from '../../services/api';
import { useCandidatesStore } from '../../store/candidatesStore';
import { useJobsStore } from '../../store/jobsStore';
import { Job, JobTimeline } from '../../types';
import { formatDate, formatDateTime, formatScore, formatSalary, humanize, jobStatusTone } from '../../utils/format';

type JobDetailRoute = RouteProp<JobsStackParamList, 'JobDetail'>;
const DESC_PREVIEW_LENGTH = 400;

export default function JobDetailScreen() {
  const route = useRoute<JobDetailRoute>();
  const { colors } = useTheme();
  const { jobId } = route.params;
  const { activeCandidateId, candidates, fetchCandidates } = useCandidatesStore();
  const { generateCoverLetter, sendApplication } = useJobsStore();
  const [job, setJob] = useState<Job | null>(null);
  const [timeline, setTimeline] = useState<JobTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [descExpanded, setDescExpanded] = useState(false);
  const [coverExpanded, setCoverExpanded] = useState(false);

  const activeCandidate = candidates.find((c) => c.id === activeCandidateId);

  const loadJob = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const [jobData, timelineData] = await Promise.all([
        apiService.getJob(jobId),
        apiService.getJobTimeline(jobId).catch(() => null),
        fetchCandidates(),
      ]);
      setJob(jobData);
      setTimeline(timelineData);
    } catch (loadError: any) {
      setError(loadError.response?.data?.detail || 'Failed to load job details');
    } finally {
      setLoading(false);
    }
  }, [fetchCandidates, jobId]);

  useEffect(() => {
    void loadJob(true);
  }, [loadJob]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadJob(false);
    setRefreshing(false);
  };

  const handleGenerateCover = async () => {
    if (!activeCandidateId) {
      Alert.alert('Select a candidate', 'Choose a candidate before generating a cover letter.');
      return;
    }
    setActionLoading('cover');
    try {
      await generateCoverLetter(jobId, activeCandidateId);
      Alert.alert('Queued', 'Cover letter generation was queued.');
      await loadJob(false);
    } catch (generateError: any) {
      Alert.alert('Could not queue cover', generateError.response?.data?.detail || 'Try again.');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSendApplication = () => {
    if (!job) return;
    if (!activeCandidateId) {
      Alert.alert('Select a candidate', 'Choose a candidate before sending.');
      return;
    }
    if (!job.hr_email || !job.cover_letter) {
      Alert.alert('Not ready', 'This job needs both an HR email and a generated cover letter.');
      return;
    }
    Alert.alert(
      'Send application',
      `Send as ${activeCandidate?.name || 'selected candidate'} to ${job.hr_email}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Send',
          onPress: async () => {
            setActionLoading('send');
            try {
              await sendApplication(jobId, activeCandidateId);
              Alert.alert('Queued', 'Application send was queued.');
              await loadJob(false);
            } catch (sendError: any) {
              Alert.alert('Could not send', sendError.response?.data?.detail || 'Try again.');
            } finally {
              setActionLoading(null);
            }
          },
        },
      ]
    );
  };

  const handleShareJob = async () => {
    if (!job) return;
    await Share.share({ message: `${job.job_title} at ${job.company}\n${job.job_url}` });
  };

  const handleOpenJob = async () => {
    if (!job?.job_url) return;
    const canOpen = await Linking.canOpenURL(job.job_url);
    if (canOpen) await Linking.openURL(job.job_url);
    else Alert.alert('Could not open link', job.job_url);
  };

  if (loading) {
    return (
      <SVGBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={[styles.centerText, { color: colors.textMuted }]}>Loading job details</Text>
        </View>
      </SVGBackground>
    );
  }

  if (error) {
    return (
      <SVGBackground>
        <SafeAreaView style={styles.safeArea} edges={['top']}>
          <View style={styles.contentPad}>
            <ScreenError message={error} onRetry={() => void loadJob(true)} />
          </View>
        </SafeAreaView>
      </SVGBackground>
    );
  }

  if (!job) {
    return (
      <SVGBackground>
        <SafeAreaView style={styles.safeArea} edges={['top']}>
          <View style={styles.contentPad}>
            <EmptyState title="Job not found" message="This job may have been removed." icon="briefcase-outline" />
          </View>
        </SafeAreaView>
      </SVGBackground>
    );
  }

  const isReady = !!job.hr_email && !!job.cover_letter;
  const descText = job.job_description ?? '';
  const isLongDesc = descText.length > DESC_PREVIEW_LENGTH;
  const displayDesc = descExpanded || !isLongDesc ? descText : descText.slice(0, DESC_PREVIEW_LENGTH) + '…';

  const coverText = job.cover_letter ?? '';
  const isLongCover = coverText.length > DESC_PREVIEW_LENGTH;
  const displayCover = coverExpanded || !isLongCover ? coverText : coverText.slice(0, DESC_PREVIEW_LENGTH) + '…';

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
            <Text style={[styles.companyLabel, { color: colors.textMuted }]}>{job.company}</Text>
            <Text style={[styles.title, { color: colors.text }]}>{job.job_title}</Text>
            <View style={styles.headerPills}>
              <StatusPill label={humanize(job.status)} tone={jobStatusTone(job.status)} />
              <StatusPill label={formatScore(job)} tone="cyan" />
              {isReady && <StatusPill label="Ready to send" tone="mint" />}
            </View>
          </View>

          {/* Readiness checklist */}
          <SectionHeader
            title="Readiness"
            subtitle={activeCandidate ? `Applying as ${activeCandidate.name}` : 'Select a candidate on Jobs screen'}
          />
          <GlassCard style={styles.readinessCard}>
            <View style={styles.readinessRow}>
              <ReadinessItem done={!!job.hr_email} label="HR email" />
              <ReadinessItem done={!!job.cover_letter} label="Cover letter" />
              <ReadinessItem done={job.status !== 'ignored' && job.status !== 'error'} label="Active status" />
            </View>
          </GlassCard>

          {/* Secondary actions */}
          <View style={styles.secondaryActions}>
            <AppButton label="Open" icon="open-outline" variant="secondary" onPress={handleOpenJob} style={styles.secBtn} />
            <AppButton label="Share" icon="share-outline" variant="secondary" onPress={handleShareJob} style={styles.secBtn} />
          </View>

          {/* Timeline */}
          <SectionHeader title="Timeline" />
          <GlassCard>
            {timeline?.events.length ? (
              timeline.events.map((event, index) => (
                <View key={`${event.event}-${index}`} style={styles.timelineRow}>
                  <View style={[styles.timelineDot, { backgroundColor: event.done ? colors.primary : colors.borderStrong }]} />
                  <View style={styles.timelineText}>
                    <Text style={[styles.timelineLabel, { color: colors.text }]}>{event.label}</Text>
                    {event.timestamp ? (
                      <Text style={[styles.timelineMeta, { color: colors.textMuted }]}>{formatDateTime(event.timestamp)}</Text>
                    ) : null}
                  </View>
                </View>
              ))
            ) : (
              <Text style={[styles.mutedText, { color: colors.textMuted }]}>No lifecycle events yet.</Text>
            )}
          </GlassCard>

          {/* Job Details */}
          <SectionHeader title="Job Details" />
          <GlassCard>
            <KeyValueRow label="Location" value={job.location} />
            <KeyValueRow label="Source" value={job.source_portal} />
            <KeyValueRow label="Job Type" value={job.job_type} />
            <KeyValueRow label="Experience" value={job.experience_required} />
            <KeyValueRow label="Salary" value={formatSalary(job)} />
            <KeyValueRow label="Scraped" value={formatDate(job.scraped_at)} />
            <InlineEditField
              label="HR Email"
              value={job.hr_email ?? ''}
              placeholder="hr@company.com"
              keyboardType="email-address"
              onSave={async (value) => {
                const updated = await apiService.setJobHrEmail(job.id, value);
                setJob(updated);
              }}
            />
            <KeyValueRow label="Recruiter" value={job.recruiter_name} />
            <KeyValueRow label="Company Website" value={job.company_website} />
          </GlassCard>

          {/* Cover Letter — collapsible */}
          {coverText ? (
            <>
              <SectionHeader title="Cover Letter" />
              <GlassCard>
                <Text style={[styles.bodyText, { color: colors.textSecondary }]}>{displayCover}</Text>
                {isLongCover && (
                  <Pressable onPress={() => setCoverExpanded((v) => !v)} style={styles.expandToggle}>
                    <Text style={[styles.expandLabel, { color: colors.primary }]}>
                      {coverExpanded ? 'Show less' : 'Read more'}
                    </Text>
                    <Ionicons name={coverExpanded ? 'chevron-up' : 'chevron-down'} size={14} color={colors.primary} />
                  </Pressable>
                )}
              </GlassCard>
            </>
          ) : null}

          {/* Job Description — collapsible */}
          {descText ? (
            <>
              <SectionHeader title="Description" />
              <GlassCard>
                <Text style={[styles.bodyText, { color: colors.textSecondary }]}>{displayDesc}</Text>
                {isLongDesc && (
                  <Pressable onPress={() => setDescExpanded((v) => !v)} style={styles.expandToggle}>
                    <Text style={[styles.expandLabel, { color: colors.primary }]}>
                      {descExpanded ? 'Show less' : 'Read more'}
                    </Text>
                    <Ionicons name={descExpanded ? 'chevron-up' : 'chevron-down'} size={14} color={colors.primary} />
                  </Pressable>
                )}
              </GlassCard>
            </>
          ) : null}
        </ScrollView>

        {/* Sticky footer action bar */}
        <View style={[styles.stickyFooter, { backgroundColor: colors.glassStrong, borderTopColor: colors.border }]}>
          <AppButton
            label="Generate Cover"
            icon="sparkles-outline"
            variant="secondary"
            onPress={handleGenerateCover}
            loading={actionLoading === 'cover'}
            style={styles.footerBtn}
          />
          <AppButton
            label="Send Application"
            icon="send-outline"
            onPress={handleSendApplication}
            loading={actionLoading === 'send'}
            disabled={!isReady}
            style={styles.footerBtnPrimary}
          />
        </View>
      </SafeAreaView>
    </SVGBackground>
  );
}

function ReadinessItem({ done, label }: { done: boolean; label: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.readinessItem}>
      <View style={[styles.readinessIcon, { backgroundColor: done ? colors.primary : colors.input }]}>
        <Ionicons name={done ? 'checkmark-outline' : 'close-outline'} size={18} color={done ? colors.primaryText : colors.textMuted} />
      </View>
      <Text style={[styles.readinessText, { color: colors.textSecondary }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  contentPad: { flex: 1, padding: 20 },
  center: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  centerText: { fontSize: 14, fontWeight: '700', marginTop: 14 },
  content: { padding: 20, paddingBottom: 210 },
  header: { marginBottom: 20, paddingTop: 6 },
  companyLabel: { fontSize: 14, fontWeight: '800', marginBottom: 8 },
  title: { fontSize: 26, fontWeight: '900', lineHeight: 34 },
  headerPills: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
  readinessCard: { marginBottom: 16 },
  readinessRow: { flexDirection: 'row', justifyContent: 'space-around' },
  readinessItem: { alignItems: 'center', flex: 1 },
  readinessIcon: {
    alignItems: 'center',
    borderRadius: 16,
    height: 42,
    justifyContent: 'center',
    marginBottom: 8,
    width: 42,
  },
  readinessText: { fontSize: 11, fontWeight: '800', textAlign: 'center' },
  secondaryActions: { flexDirection: 'row', gap: 10, marginBottom: 24 },
  secBtn: { flex: 1 },
  timelineRow: { flexDirection: 'row', gap: 12, paddingVertical: 10 },
  timelineDot: { borderRadius: 6, height: 12, marginTop: 3, width: 12 },
  timelineText: { flex: 1 },
  timelineLabel: { fontSize: 14, fontWeight: '900' },
  timelineMeta: { fontSize: 12, fontWeight: '700', marginTop: 3 },
  mutedText: { fontSize: 13, fontWeight: '700' },
  bodyText: { fontSize: 14, fontWeight: '600', lineHeight: 22 },
  expandToggle: { alignItems: 'center', flexDirection: 'row', gap: 4, marginTop: 12 },
  expandLabel: { fontSize: 13, fontWeight: '800' },
  stickyFooter: {
    borderTopWidth: StyleSheet.hairlineWidth,
    bottom: 86,
    flexDirection: 'row',
    gap: 12,
    left: 0,
    paddingBottom: 18,
    paddingHorizontal: 20,
    paddingTop: 14,
    position: 'absolute',
    right: 0,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -10 },
    shadowOpacity: 0.16,
    shadowRadius: 18,
  },
  footerBtn: { flex: 1 },
  footerBtnPrimary: { flex: 1.6 },
});
