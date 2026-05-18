import React, { useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard } from '../../components/GlassKit';
import { useTheme } from '../../context/ThemeContext';
import { useAuthStore } from '../../store/authStore';
import { useTenantStore } from '../../store/tenantStore';
import { RootStackParamList } from '../../navigation/AppNavigator';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const STEPS = ['Welcome', 'Configure', 'Done'] as const;
type Step = typeof STEPS[number];

export default function OnboardingScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<Nav>();
  const { user } = useAuthStore();
  const { updateTenant } = useTenantStore();

  const [step, setStep] = useState<Step>('Welcome');
  const [scoreThreshold, setScoreThreshold] = useState(50);
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [autoSend, setAutoSend] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSaveConfigure() {
    setSaving(true);
    try {
      await updateTenant({ score_threshold: scoreThreshold, requires_approval: requiresApproval, auto_send: autoSend });
      setStep('Done');
    } catch {
      setStep('Done');
    } finally {
      setSaving(false);
    }
  }

  const stepIndex = STEPS.indexOf(step);

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea}>
        {/* Step indicator */}
        <View style={styles.stepRow}>
          {STEPS.map((s, i) => (
            <View key={s} style={styles.stepItem}>
              <View style={[
                styles.stepDot,
                {
                  backgroundColor: i <= stepIndex ? colors.primary : colors.border,
                  borderColor: i <= stepIndex ? colors.primary : colors.border,
                },
              ]}>
                {i < stepIndex && <Ionicons name="checkmark" size={12} color={colors.primaryText} />}
              </View>
              {i < STEPS.length - 1 && (
                <View style={[styles.stepLine, { backgroundColor: i < stepIndex ? colors.primary : colors.border }]} />
              )}
            </View>
          ))}
        </View>

        <View style={styles.content}>
          {step === 'Welcome' && (
            <View style={styles.stepContent}>
              <View style={[styles.botIcon, { backgroundColor: colors.primarySoft }]}>
                <Ionicons name="hardware-chip-outline" size={48} color={colors.primary} />
              </View>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Welcome to QuickHunt</Text>
              <Text style={[styles.stepSubtitle, { color: colors.textSecondary }]}>
                Your AI-powered job application engine. Let's get{' '}
                <Text style={{ color: colors.primary }}>{user?.email?.split('@')[0] ?? 'you'}</Text> set up.
              </Text>
              <GlassCard style={styles.featureCard}>
                {[
                  { icon: 'search-outline' as const, text: 'Scrape jobs from 14+ portals' },
                  { icon: 'sparkles-outline' as const, text: 'AI-generated cover letters' },
                  { icon: 'paper-plane-outline' as const, text: 'Auto email to HR contacts' },
                  { icon: 'stats-chart-outline' as const, text: 'Relevance scoring & filtering' },
                ].map((f) => (
                  <View key={f.text} style={styles.featureRow}>
                    <Ionicons name={f.icon} size={16} color={colors.primary} />
                    <Text style={[styles.featureText, { color: colors.textSecondary }]}>{f.text}</Text>
                  </View>
                ))}
              </GlassCard>
              <AppButton label="Get Started" icon="arrow-forward-outline" onPress={() => setStep('Configure')} style={styles.mainBtn} />
            </View>
          )}

          {step === 'Configure' && (
            <View style={styles.stepContent}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Configure Preferences</Text>
              <Text style={[styles.stepSubtitle, { color: colors.textSecondary }]}>
                These settings control how jobs are filtered and sent.
              </Text>
              <GlassCard>
                <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>SCORE THRESHOLD: {scoreThreshold}%</Text>
                <View style={styles.scoreChips}>
                  {[30, 50, 60, 70, 80].map((v) => (
                    <Pressable
                      key={v}
                      onPress={() => setScoreThreshold(v)}
                      style={[
                        styles.scoreChip,
                        { backgroundColor: scoreThreshold === v ? colors.primary : colors.input, borderColor: scoreThreshold === v ? colors.primary : colors.border },
                      ]}
                    >
                      <Text style={[styles.scoreChipText, { color: scoreThreshold === v ? colors.primaryText : colors.textMuted }]}>{v}%</Text>
                    </Pressable>
                  ))}
                </View>

                <View style={[styles.switchRow, { borderTopColor: colors.border }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.switchLabel, { color: colors.text }]}>Requires Approval</Text>
                    <Text style={[styles.switchHint, { color: colors.textMuted }]}>Review before sending</Text>
                  </View>
                  <Switch
                    value={requiresApproval}
                    onValueChange={(v) => { setRequiresApproval(v); if (v) setAutoSend(false); }}
                    trackColor={{ false: colors.border, true: colors.primary }}
                  />
                </View>

                <View style={[styles.switchRow, { borderTopColor: colors.border }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.switchLabel, { color: colors.text }]}>Auto Send</Text>
                    <Text style={[styles.switchHint, { color: colors.textMuted }]}>Send after cover generation</Text>
                  </View>
                  <Switch
                    value={autoSend}
                    onValueChange={setAutoSend}
                    disabled={requiresApproval}
                    trackColor={{ false: colors.border, true: colors.primary }}
                  />
                </View>
              </GlassCard>
              <AppButton label={saving ? 'Saving...' : 'Save & Continue'} icon="checkmark-outline" onPress={handleSaveConfigure} loading={saving} style={styles.mainBtn} />
            </View>
          )}

          {step === 'Done' && (
            <View style={styles.stepContent}>
              <View style={[styles.botIcon, { backgroundColor: colors.success + '22' }]}>
                <Ionicons name="checkmark-circle" size={56} color={colors.success} />
              </View>
              <Text style={[styles.stepTitle, { color: colors.text }]}>You're all set!</Text>
              <Text style={[styles.stepSubtitle, { color: colors.textSecondary }]}>
                Here's what to do next:
              </Text>
              <GlassCard style={styles.nextSteps}>
                {[
                  { icon: 'person-add-outline' as const, title: 'Add a Candidate', sub: 'Add your profile and resume' },
                  { icon: 'search-outline' as const, title: 'Search for Jobs', sub: 'Scrape matching jobs from portals' },
                  { icon: 'grid-outline' as const, title: 'View Dashboard', sub: 'Monitor your application pipeline' },
                ].map((item, i) => (
                  <View
                    key={item.title}
                    style={[styles.nextItem, { borderTopColor: colors.border, borderTopWidth: i > 0 ? StyleSheet.hairlineWidth : 0 }]}
                  >
                    <View style={[styles.nextIcon, { backgroundColor: colors.primarySoft }]}>
                      <Ionicons name={item.icon} size={18} color={colors.primary} />
                    </View>
                    <View>
                      <Text style={[styles.nextTitle, { color: colors.text }]}>{item.title}</Text>
                      <Text style={[styles.nextSub, { color: colors.textMuted }]}>{item.sub}</Text>
                    </View>
                  </View>
                ))}
              </GlassCard>
              <AppButton
                label="Go to Dashboard"
                icon="grid-outline"
                onPress={() => navigation.replace('Main')}
                style={styles.mainBtn}
              />
            </View>
          )}
        </View>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  stepRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'center', paddingTop: 24 },
  stepItem: { alignItems: 'center', flexDirection: 'row' },
  stepDot: { alignItems: 'center', borderRadius: 14, borderWidth: 2, height: 28, justifyContent: 'center', width: 28 },
  stepLine: { height: 2, width: 40 },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: 24, paddingBottom: 40 },
  stepContent: { alignItems: 'stretch', gap: 16 },
  botIcon: { alignItems: 'center', alignSelf: 'center', borderRadius: 32, height: 96, justifyContent: 'center', marginBottom: 8, width: 96 },
  stepTitle: { fontSize: 28, fontWeight: '900', textAlign: 'center' },
  stepSubtitle: { fontSize: 15, lineHeight: 22, textAlign: 'center' },
  featureCard: { gap: 12 },
  featureRow: { alignItems: 'center', flexDirection: 'row', gap: 10 },
  featureText: { flex: 1, fontSize: 14, fontWeight: '600' },
  mainBtn: { marginTop: 8 },
  fieldLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 12 },
  scoreChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  scoreChip: { borderRadius: 999, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 8 },
  scoreChipText: { fontSize: 13, fontWeight: '700' },
  switchRow: { alignItems: 'center', flexDirection: 'row', gap: 12, paddingTop: 14 },
  switchLabel: { fontSize: 14, fontWeight: '700' },
  switchHint: { fontSize: 12, fontWeight: '500', marginTop: 2 },
  nextSteps: { gap: 0 },
  nextItem: { alignItems: 'center', flexDirection: 'row', gap: 14, paddingVertical: 14 },
  nextIcon: { alignItems: 'center', borderRadius: 12, height: 40, justifyContent: 'center', width: 40 },
  nextTitle: { fontSize: 14, fontWeight: '800' },
  nextSub: { fontSize: 12, fontWeight: '500', marginTop: 2 },
});
