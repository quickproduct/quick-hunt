import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRoute, useNavigation, RouteProp } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard, SectionHeader } from '../../components/GlassKit';
import TagInput from '../../components/TagInput';
import { useTheme } from '../../context/ThemeContext';
import { useCandidatesStore } from '../../store/candidatesStore';
import apiService from '../../services/api';
import { CandidatesStackParamList } from '../../navigation/AppNavigator';

type RouteT = RouteProp<CandidatesStackParamList, 'CandidateEdit'>;

export default function CandidateEditScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation();
  const route = useRoute<RouteT>();
  const candidateId = route.params?.candidateId;
  const { candidates, createCandidate, updateCandidate } = useCandidatesStore();

  const existing = candidateId ? candidates.find((c) => c.id === candidateId) : undefined;

  const [name, setName] = useState(existing?.name ?? '');
  const [email, setEmail] = useState(existing?.email ?? '');
  const [skills, setSkills] = useState<string[]>(existing?.skills ?? []);
  const [targetRoles, setTargetRoles] = useState<string[]>(existing?.target_roles ?? []);
  const [targetLocations, setTargetLocations] = useState<string[]>(existing?.target_locations ?? []);
  const [yearsExp, setYearsExp] = useState(existing?.years_experience?.toString() ?? '');
  const [linkedin, setLinkedin] = useState(existing?.linkedin_url ?? '');
  const [github, setGithub] = useState(existing?.github_url ?? '');
  const [bio, setBio] = useState(existing?.bio ?? '');
  const [coverTemplate, setCoverTemplate] = useState(existing?.cover_letter_template ?? '');
  const [staticCover, setStaticCover] = useState(existing?.static_cover_letter ?? '');
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);
  const [optionalOpen, setOptionalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadingResume, setUploadingResume] = useState(false);
  const [resumeUrl, setResumeUrl] = useState(existing?.resume_url ?? '');

  async function handleSave() {
    if (!name.trim() || !email.trim()) {
      Alert.alert('Error', 'Name and email are required');
      return;
    }
    if (skills.length === 0) {
      Alert.alert('Error', 'Add at least one skill');
      return;
    }
    setSaving(true);
    try {
      const data = {
        name: name.trim(),
        email: email.trim(),
        skills,
        target_roles: targetRoles,
        target_locations: targetLocations,
        years_experience: yearsExp ? parseInt(yearsExp, 10) : undefined,
        linkedin_url: linkedin.trim() || undefined,
        github_url: github.trim() || undefined,
        bio: bio.trim() || undefined,
        cover_letter_template: coverTemplate.trim() || undefined,
        static_cover_letter: staticCover.trim() || undefined,
        is_active: isActive,
      };

      if (candidateId) {
        await updateCandidate(candidateId, data);
        Alert.alert('Saved', 'Candidate updated successfully');
      } else {
        await createCandidate(data);
        Alert.alert('Created', 'Candidate created successfully');
      }
      navigation.goBack();
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to save candidate');
    } finally {
      setSaving(false);
    }
  }

  async function handleUploadResume() {
    if (!candidateId) {
      Alert.alert('Save first', 'Save the candidate before uploading a resume');
      return;
    }
    try {
      // expo-document-picker is imported dynamically to avoid crash if not installed
      const DocumentPicker = await import('expo-document-picker').catch(() => null);
      if (!DocumentPicker) {
        Alert.alert('Not available', 'Document picker not installed');
        return;
      }
      const result = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      setUploadingResume(true);
      const updated = await apiService.uploadResume(candidateId, asset.uri, asset.name ?? 'resume.pdf');
      setResumeUrl(updated.resume_url ?? '');
      Alert.alert('Uploaded', 'Resume uploaded successfully');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Upload failed');
    } finally {
      setUploadingResume(false);
    }
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
            <Text style={[styles.title, { color: colors.text }]}>
              {candidateId ? 'Edit Candidate' : 'New Candidate'}
            </Text>

            {/* Required fields */}
            <SectionHeader title="Required" />
            <GlassCard>
              <TextInput
                value={name}
                onChangeText={setName}
                placeholder="Full name"
                placeholderTextColor={colors.textMuted}
                style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
              />
              <TextInput
                value={email}
                onChangeText={setEmail}
                placeholder="Email"
                placeholderTextColor={colors.textMuted}
                keyboardType="email-address"
                autoCapitalize="none"
                style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
              />
              <TagInput label="Skills" tags={skills} onChange={setSkills} placeholder="e.g. React" />
              <TagInput label="Target Roles" tags={targetRoles} onChange={setTargetRoles} placeholder="e.g. Frontend Developer" />
              <TagInput label="Target Locations" tags={targetLocations} onChange={setTargetLocations} placeholder="e.g. Remote" />
            </GlassCard>

            {/* Optional fields */}
            <Pressable onPress={() => setOptionalOpen((v) => !v)} style={styles.optionalToggle}>
              <Ionicons name={optionalOpen ? 'chevron-up-circle-outline' : 'chevron-down-circle-outline'} size={18} color={colors.primary} />
              <Text style={[styles.optionalToggleText, { color: colors.primary }]}>
                {optionalOpen ? 'Hide' : 'Show'} optional fields
              </Text>
            </Pressable>

            {optionalOpen && (
              <GlassCard style={styles.optionalCard}>
                <TextInput
                  value={yearsExp}
                  onChangeText={setYearsExp}
                  placeholder="Years of experience"
                  placeholderTextColor={colors.textMuted}
                  keyboardType="numeric"
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <TextInput
                  value={linkedin}
                  onChangeText={setLinkedin}
                  placeholder="LinkedIn URL"
                  placeholderTextColor={colors.textMuted}
                  autoCapitalize="none"
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <TextInput
                  value={github}
                  onChangeText={setGithub}
                  placeholder="GitHub URL"
                  placeholderTextColor={colors.textMuted}
                  autoCapitalize="none"
                  style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <TextInput
                  value={bio}
                  onChangeText={setBio}
                  placeholder="Bio / summary"
                  placeholderTextColor={colors.textMuted}
                  multiline
                  numberOfLines={3}
                  style={[styles.input, styles.multiline, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>COVER LETTER TEMPLATE</Text>
                <TextInput
                  value={coverTemplate}
                  onChangeText={setCoverTemplate}
                  placeholder="Custom cover letter template (optional)"
                  placeholderTextColor={colors.textMuted}
                  multiline
                  numberOfLines={4}
                  style={[styles.input, styles.multiline, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>STATIC COVER LETTER</Text>
                <TextInput
                  value={staticCover}
                  onChangeText={setStaticCover}
                  placeholder="Static cover letter for direct HR send"
                  placeholderTextColor={colors.textMuted}
                  multiline
                  numberOfLines={4}
                  style={[styles.input, styles.multiline, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                />
                <View style={[styles.switchRow, { borderTopColor: colors.border }]}>
                  <Text style={[styles.switchLabel, { color: colors.text }]}>Active</Text>
                  <Switch
                    value={isActive}
                    onValueChange={setIsActive}
                    trackColor={{ false: colors.border, true: colors.primary }}
                    thumbColor={colors.primaryText}
                  />
                </View>
              </GlassCard>
            )}

            {/* Resume */}
            {candidateId && (
              <>
                <SectionHeader title="Resume (PDF)" />
                <GlassCard>
                  {resumeUrl ? (
                    <View style={styles.resumeRow}>
                      <Ionicons name="document-text-outline" size={20} color={colors.success} />
                      <Text style={[styles.resumeLabel, { color: colors.text }]}>Resume uploaded</Text>
                    </View>
                  ) : (
                    <Text style={[styles.noResume, { color: colors.textMuted }]}>No resume uploaded yet</Text>
                  )}
                  <AppButton
                    label={uploadingResume ? 'Uploading...' : resumeUrl ? 'Replace Resume' : 'Upload PDF Resume'}
                    icon="cloud-upload-outline"
                    onPress={handleUploadResume}
                    loading={uploadingResume}
                    variant="secondary"
                    style={styles.uploadBtn}
                  />
                </GlassCard>
              </>
            )}

            <AppButton label={saving ? 'Saving...' : 'Save Candidate'} icon="save-outline" onPress={handleSave} loading={saving} style={styles.saveBtn} />
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  title: { fontSize: 28, fontWeight: '900', marginBottom: 20, paddingTop: 10 },
  input: { borderRadius: 17, borderWidth: 1, fontSize: 14, fontWeight: '700', marginBottom: 12, paddingHorizontal: 14, paddingVertical: 13 },
  multiline: { minHeight: 80, textAlignVertical: 'top' },
  fieldLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6, marginTop: 4 },
  optionalToggle: { alignItems: 'center', flexDirection: 'row', gap: 7, justifyContent: 'center', marginVertical: 12 },
  optionalToggleText: { fontSize: 13, fontWeight: '900' },
  optionalCard: { marginBottom: 12 },
  switchRow: { alignItems: 'center', borderTopWidth: StyleSheet.hairlineWidth, flexDirection: 'row', justifyContent: 'space-between', paddingTop: 14 },
  switchLabel: { fontSize: 14, fontWeight: '700' },
  resumeRow: { alignItems: 'center', flexDirection: 'row', gap: 8, marginBottom: 12 },
  resumeLabel: { fontSize: 14, fontWeight: '600' },
  noResume: { fontSize: 13, fontWeight: '600', marginBottom: 12 },
  uploadBtn: { marginTop: 4 },
  saveBtn: { marginTop: 16 },
});
