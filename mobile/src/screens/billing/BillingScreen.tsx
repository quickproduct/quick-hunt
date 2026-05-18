import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Linking,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import SVGBackground from '../../components/SVGBackground';
import { AppButton, GlassCard, ScreenError, SectionHeader, StatusPill } from '../../components/GlassKit';
import AccordionRow from '../../components/AccordionRow';
import { useTheme } from '../../context/ThemeContext';
import { useBillingStore } from '../../store/billingStore';

const FAQ_ITEMS = [
  { q: 'What payment methods are accepted?', a: 'We accept all major credit/debit cards and UPI via Razorpay.' },
  { q: 'Can I cancel anytime?', a: 'Yes. Cancel anytime from this screen. Your plan stays active until the end of the billing period.' },
  { q: "What happens if I hit my plan's limits?", a: "Applications and scraping will pause until the next billing cycle or you upgrade." },
];

export default function BillingScreen() {
  const { colors } = useTheme();
  const { plans, subscription, loading, error, fetchPlans, fetchSubscription, createCheckout, cancelSubscription } = useBillingStore();
  const [refreshing, setRefreshing] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState('');

  const load = useCallback(async () => {
    await Promise.all([fetchPlans(), fetchSubscription()]);
  }, [fetchPlans, fetchSubscription]);

  useEffect(() => {
    void load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  async function handleUpgrade(plan: string) {
    setCheckoutLoading(plan);
    try {
      const url = await createCheckout(plan);
      if (url) {
        await Linking.openURL(url);
      } else {
        Alert.alert('Error', 'Could not get checkout URL');
      }
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Checkout failed');
    } finally {
      setCheckoutLoading('');
    }
  }

  function handleCancel() {
    Alert.alert(
      'Cancel Subscription',
      'Are you sure you want to cancel? Your plan stays active until the end of the billing period.',
      [
        { text: 'Keep Plan', style: 'cancel' },
        {
          text: 'Cancel Subscription',
          style: 'destructive',
          onPress: async () => {
            try {
              await cancelSubscription();
              Alert.alert('Cancelled', 'Subscription cancelled successfully');
            } catch (e: any) {
              Alert.alert('Error', e.response?.data?.detail || 'Failed to cancel');
            }
          },
        },
      ]
    );
  }

  const currentPlan = subscription?.plan ?? 'free';

  return (
    <SVGBackground>
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          <Text style={[styles.title, { color: colors.text }]}>Billing</Text>
          <Text style={[styles.subtitle, { color: colors.textMuted }]}>Manage your subscription</Text>

          {/* Current plan banner */}
          {subscription?.subscription && (
            <GlassCard style={styles.currentBanner}>
              <View style={styles.bannerRow}>
                <Ionicons name="card-outline" size={20} color={colors.primary} />
                <Text style={[styles.bannerText, { color: colors.text }]}>
                  {currentPlan.toUpperCase()} plan active
                </Text>
                <StatusPill label="Active" tone="mint" />
              </View>
              {subscription.subscription.current_period_end && (
                <Text style={[styles.renewDate, { color: colors.textMuted }]}>
                  Renews {new Date(subscription.subscription.current_period_end).toLocaleDateString()}
                </Text>
              )}
            </GlassCard>
          )}

          {error && <ScreenError message={error} onRetry={() => void load()} />}

          {/* Plan cards */}
          <SectionHeader title="Plans" />
          {plans.map((plan) => {
            const isCurrentPlan = currentPlan === plan.name.toLowerCase();
            return (
              <GlassCard key={plan.name} style={[styles.planCard, isCurrentPlan && { borderColor: colors.primary }]}>
                <View style={styles.planHeader}>
                  <Text style={[styles.planName, { color: colors.text }]}>{plan.name}</Text>
                  <Text style={[styles.planPrice, { color: colors.primary }]}>
                    {plan.price === 0 ? 'Free' : `₹${plan.price}/mo`}
                  </Text>
                </View>
                <View style={styles.features}>
                  {Object.entries(plan.features).map(([key, value]) => (
                    <View key={key} style={styles.featureRow}>
                      <Ionicons name="checkmark-circle-outline" size={14} color={colors.success} />
                      <Text style={[styles.featureText, { color: colors.textSecondary }]}>
                        {String(value)} {key.replace(/_/g, ' ')}
                      </Text>
                    </View>
                  ))}
                </View>
                {isCurrentPlan ? (
                  <AppButton label="Current Plan" variant="secondary" disabled style={styles.planBtn} />
                ) : (
                  <AppButton
                    label={plan.price > (plans.find(p => p.name.toLowerCase() === currentPlan)?.price ?? 0) ? 'Upgrade' : 'Downgrade'}
                    icon="arrow-up-circle-outline"
                    onPress={() => handleUpgrade(plan.name.toLowerCase())}
                    loading={checkoutLoading === plan.name.toLowerCase()}
                    style={styles.planBtn}
                  />
                )}
              </GlassCard>
            );
          })}

          {/* FAQ */}
          <SectionHeader title="FAQ" />
          <GlassCard padded={false} style={{ paddingHorizontal: 16 }}>
            {FAQ_ITEMS.map((item) => (
              <AccordionRow key={item.q} title={item.q}>
                <Text style={[styles.faqAnswer, { color: colors.textSecondary }]}>{item.a}</Text>
              </AccordionRow>
            ))}
          </GlassCard>

          {/* Cancel */}
          {subscription?.subscription && (
            <>
              <SectionHeader title="Danger Zone" />
              <GlassCard>
                <AppButton label="Cancel Subscription" icon="close-circle-outline" variant="danger" onPress={handleCancel} />
              </GlassCard>
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </SVGBackground>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  content: { padding: 20, paddingBottom: 118 },
  title: { fontSize: 28, fontWeight: '900', marginTop: 10 },
  subtitle: { fontSize: 13, fontWeight: '500', marginBottom: 20, marginTop: 4 },
  currentBanner: { marginBottom: 20 },
  bannerRow: { alignItems: 'center', flexDirection: 'row', gap: 10, marginBottom: 4 },
  bannerText: { flex: 1, fontSize: 15, fontWeight: '800' },
  renewDate: { fontSize: 12, fontWeight: '600' },
  planCard: { marginBottom: 12 },
  planHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  planName: { fontSize: 18, fontWeight: '900' },
  planPrice: { fontSize: 18, fontWeight: '900' },
  features: { gap: 8, marginBottom: 16 },
  featureRow: { alignItems: 'center', flexDirection: 'row', gap: 8 },
  featureText: { flex: 1, fontSize: 13, fontWeight: '600' },
  planBtn: { alignSelf: 'stretch' },
  faqAnswer: { fontSize: 13, fontWeight: '500', lineHeight: 20 },
});
