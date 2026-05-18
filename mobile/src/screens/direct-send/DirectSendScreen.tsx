import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard, SectionHeader } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useCandidatesStore } from '../../store/candidatesStore';
import apiService from '../../services/api';
import { DirectSendResult } from '../../types';

function isValidEmail(e: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e.trim());
}

function parseEmails(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((e) => e.trim())
    .filter((e) => e.length > 0);
}

export default function DirectSendScreen() {
  const { colors } = useTheme();
  const { candidates, fetchCandidates } = useCandidatesStore();
  const [selectedId, setSelectedId] = useState('');
  const [emailsText, setEmailsText] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<DirectSendResult | null>(null);

  useEffect(() => {
    if (candidates.length === 0) void fetchCandidates();
  }, []);

  const candidate = candidates.find((c) => c.id === selectedId);
  const emails = parseEmails(emailsText);
  const validEmails = emails.filter(isValidEmail);
  const invalidEmails = emails.filter((e) => !isValidEmail(e));
  const hasStaticCover = !!candidate?.static_cover_letter;
  const canSend = selectedId && validEmails.length > 0 && hasStaticCover;

  async function handleSend() {
    if (!canSend) return;
    Alert.alert(
      'Confirm Send',
      `Send resume to ${validEmails.length} HR email${validEmails.length > 1 ? 's' : ''}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Send',
          style: 'default',
          onPress: async () => {
            setSending(true);
            try {
              const res = await apiService.directHRSend(selectedId, validEmails);
              setResult(res);
            } catch (e: any) {
              Alert.alert('Error', e.response?.data?.detail || 'Send failed');
            } finally {
              setSending(false);
            }
          },
        },
      ]
    );
  }

  function handleReset() {
    setResult(null);
    setEmailsText('');
  }

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
            <Text style={[styles.title, { color: colors.text }]}>Direct HR Send</Text>
            <Text style={[styles.subtitle, { color: colors.textMuted }]}>
              Send your resume + static cover letter directly to HR contacts (no job posting required)
            </Text>

            {result ? (
              <GlassCard style={styles.resultCard}>
                <View style={styles.resultRow}>
                  <Ionicons name="checkmark-circle" size={22} color={colors.success} />
                  <Text style={[styles.resultLabel, { color: colors.text }]}>
                    {result.sent} email{result.sent !== 1 ? 's' : ''} sent successfully
                  </Text>
                </View>
                {result.skipped.length > 0 && (
                  <Text style={[styles.resultSub, { color: colors.textMuted }]}>
                    {result.skipped.length} skipped (already sent)
                  </Text>
                )}
                {result.failed.length > 0 && (
                  <View style={styles.failedList}>
                    <Text style={[styles.failedTitle, { color: colors.error }]}>Failed:</Text>
                    {result.failed.map((f, i) => (
                      <Text key={i} style={[styles.failedItem, { color: colors.textSecondary }]}>
                        {f.email}: {f.reason}
                      </Text>
                    ))}
                  </View>
                )}
                <AppButton label="Send More" icon="refresh-outline" onPress={handleReset} variant="secondary" style={styles.resetBtn} />
              </GlassCard>
            ) : (
              <>
                {/* Candidate picker */}
                <SectionHeader title="Select Candidate" />
                <GlassCard padded={false} style={styles.pickerCard}>
                  {candidates.map((c, i) => (
                    <Pressable
                      key={c.id}
                      onPress={() => setSelectedId(c.id)}
                      style={[
                        styles.candidateRow,
                        { borderBottomColor: colors.border, borderBottomWidth: i < candidates.length - 1 ? StyleSheet.hairlineWidth : 0 },
                        selectedId === c.id && { backgroundColor: colors.primarySoft },
                      ]}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.candidateName, { color: colors.text }]}>{c.name}</Text>
                        <Text style={[styles.candidateSub, { color: colors.textMuted }]}>
                          {c.static_cover_letter ? 'Static cover ready' : 'No static cover letter'}
                        </Text>
                      </View>
                      {selectedId === c.id && (
                        <Ionicons name="checkmark-circle" size={20} color={colors.primary} />
                      )}
                    </Pressable>
                  ))}
                </GlassCard>

                {candidate && !hasStaticCover && (
                  <View style={[styles.warning, { backgroundColor: colors.accentAmber + '22', borderColor: colors.accentAmber }]}>
                    <Ionicons name="warning-outline" size={16} color={colors.accentAmber} />
                    <Text style={[styles.warningText, { color: colors.warning }]}>
                      This candidate does not have a static cover letter. Add one in Candidates, then Edit before sending.
                    </Text>
                  </View>
                )}

                {/* Email input */}
                <SectionHeader title="HR Email Addresses" subtitle="Comma or newline separated" />
                <GlassCard>
                  <TextInput
                    value={emailsText}
                    onChangeText={setEmailsText}
                    placeholder={'hr@company1.com\nhr@company2.com'}
                    placeholderTextColor={colors.textMuted}
                    multiline
                    numberOfLines={6}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    style={[styles.emailInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.input }]}
                  />
                  {invalidEmails.length > 0 && (
                    <Text style={[styles.invalidHint, { color: colors.error }]}>
                      {invalidEmails.length} invalid email{invalidEmails.length > 1 ? 's' : ''} will be skipped
                    </Text>
                  )}
                  {validEmails.length > 0 && (
                    <Text style={[styles.validHint, { color: colors.success }]}>
                      {validEmails.length} valid email{validEmails.length > 1 ? 's' : ''} ready to send
                    </Text>
                  )}
                </GlassCard>

                <AppButton
                  label={sending ? 'Sending...' : `Send to ${validEmails.length || 0} HR Contact${validEmails.length !== 1 ? 's' : ''}`}
                  icon="paper-plane-outline"
                  onPress={handleSend}
                  loading={sending}
                  disabled={!canSend}
                  style={styles.sendBtn}
                />
              </>
            )}
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  title: { fontSize: 28, fontWeight: '900', marginTop: 10 },
  subtitle: { fontSize: 13, fontWeight: '500', lineHeight: 20, marginBottom: 24, marginTop: 6 },
  pickerCard: { overflow: 'hidden' },
  candidateRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 15 },
  candidateName: { fontSize: 14, fontWeight: '700' },
  candidateSub: { fontSize: 12, fontWeight: '600', marginTop: 2 },
  warning: { alignItems: 'flex-start', borderRadius: 17, borderWidth: 1, flexDirection: 'row', gap: 8, marginBottom: 16, padding: 13 },
  warningText: { flex: 1, fontSize: 13, fontWeight: '600', lineHeight: 18 },
  emailInput: { borderRadius: 17, borderWidth: 1, fontSize: 14, fontWeight: '700', minHeight: 112, paddingHorizontal: 14, paddingVertical: 13, textAlignVertical: 'top' },
  invalidHint: { fontSize: 12, fontWeight: '600', marginTop: 8 },
  validHint: { fontSize: 12, fontWeight: '600', marginTop: 4 },
  sendBtn: { marginTop: 16 },
  resultCard: { alignItems: 'flex-start' },
  resultRow: { alignItems: 'center', flexDirection: 'row', gap: 10, marginBottom: 8 },
  resultLabel: { fontSize: 16, fontWeight: '800' },
  resultSub: { fontSize: 13, fontWeight: '600', marginBottom: 8 },
  failedList: { marginTop: 8 },
  failedTitle: { fontSize: 13, fontWeight: '800', marginBottom: 4 },
  failedItem: { fontSize: 12, fontWeight: '600', marginBottom: 2 },
  resetBtn: { marginTop: 16, alignSelf: 'stretch' },
});
