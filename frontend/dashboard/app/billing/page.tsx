'use client';

import { useState, useEffect } from 'react';
import {
  Check,
  Zap,
  Crown,
  ChevronDown,
  ChevronUp,
  Loader2,
  CreditCard,
  AlertCircle,
} from 'lucide-react';
import {
  getPlans,
  getSubscription,
  createCheckout,
  cancelSubscription,
  getMyTenant,
  Plan,
} from '@/lib/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatFeatureValue(value: number, unit: string) {
  if (value === -1) return { text: `Unlimited ${unit}`, unlimited: true };
  return { text: `${value} ${unit}`, unlimited: false };
}

function formatRenewalDate(dateStr: string) {
  try {
    return new Date(dateStr).toLocaleDateString('en-IN', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

// ── FAQ Accordion ─────────────────────────────────────────────────────────────

const FAQ_ITEMS = [
  {
    q: 'What payment methods are accepted?',
    a: 'We accept all major credit/debit cards via Razorpay. UPI and netbanking are also supported.',
  },
  {
    q: 'Can I cancel anytime?',
    a: "Yes, you can cancel at any time. You'll retain access until the end of your billing period.",
  },
  {
    q: 'What happens when I hit the limit?',
    a: 'Applications are paused until the next day. Your data is never deleted.',
  },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-gray-800 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-4 text-left text-sm font-medium text-gray-300 hover:text-gray-100 transition-colors"
      >
        <span>{q}</span>
        {open ? (
          <ChevronUp size={16} className="text-gray-500 flex-shrink-0 ml-4" />
        ) : (
          <ChevronDown size={16} className="text-gray-500 flex-shrink-0 ml-4" />
        )}
      </button>
      <div
        className={`overflow-hidden transition-all duration-200 ${
          open ? 'max-h-32 pb-4' : 'max-h-0'
        }`}
      >
        <p className="text-sm text-gray-500 leading-relaxed">{a}</p>
      </div>
    </div>
  );
}

// ── Plan card ─────────────────────────────────────────────────────────────────

function PlanCard({
  plan,
  isCurrent,
  isPopular,
  currentPlanId,
  onSelect,
  loading,
}: {
  plan: Plan;
  isCurrent: boolean;
  isPopular: boolean;
  currentPlanId: string;
  onSelect: (id: string) => void;
  loading: boolean;
}) {
  const appsPerDay = formatFeatureValue(plan.applications_per_day, 'applications/day');
  const aiCredits = formatFeatureValue(plan.ai_credits_per_month, 'AI credits/month');
  const automations = formatFeatureValue(plan.active_automations, 'active automations');

  const isPro = plan.id === 'pro';
  const isPremium = plan.id === 'premium';
  const isFree = plan.price_inr === 0;

  // Decide label: Upgrade vs Downgrade
  const planOrder: Record<string, number> = { free: 0, pro: 1, premium: 2 };
  const currentOrder = planOrder[currentPlanId] ?? 0;
  const thisOrder = planOrder[plan.id] ?? 0;
  const buttonLabel =
    thisOrder > currentOrder ? `Upgrade to ${plan.label}` : `Downgrade to ${plan.label}`;

  return (
    <div
      className={`relative flex flex-col rounded-2xl border transition-shadow duration-200 ${
        isCurrent
          ? 'border-blue-500/60 bg-blue-500/5'
          : isPro
          ? 'border-blue-500/30 bg-gray-900 shadow-xl shadow-blue-900/10'
          : 'border-gray-800 bg-gray-900'
      } ${isPro ? 'ring-1 ring-blue-500/20' : ''}`}
    >
      {/* Pro top accent */}
      {isPro && (
        <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-blue-500 to-blue-400" />
      )}

      {/* Most popular badge */}
      {isPopular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-blue-600 text-white text-xs font-semibold px-3 py-1 rounded-full shadow-lg">
            Most Popular
          </span>
        </div>
      )}

      <div className="p-6 flex flex-col flex-1 mt-1">
        {/* Header */}
        <div className="mb-5">
          <div className="flex items-center gap-2 mb-2">
            {isFree && <Zap size={16} className="text-gray-400" />}
            {isPro && <Zap size={16} className="text-blue-400" />}
            {isPremium && <Crown size={16} className="text-violet-400" />}
            <span className="text-base font-semibold text-gray-100">{plan.label}</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-bold text-gray-100">
              {isFree ? 'Free' : `₹${plan.price_inr.toLocaleString('en-IN')}`}
            </span>
            {!isFree && <span className="text-sm text-gray-500">/mo</span>}
          </div>
          {!isFree && <p className="text-xs text-gray-500 mt-0.5">per month, billed monthly</p>}
        </div>

        {/* Features */}
        <ul className="space-y-2.5 flex-1 mb-6">
          <FeatureItem text={appsPerDay.text} unlimited={appsPerDay.unlimited} />
          <FeatureItem text={aiCredits.text} unlimited={aiCredits.unlimited} />
          <FeatureItem text={automations.text} unlimited={automations.unlimited} />
          <FeatureItem text="Email tracking" />
          {(isPro || isPremium) && <FeatureItem text="Bulk operations" />}
          {isPremium && <FeatureItem text="Priority support" highlight />}
        </ul>

        {/* CTA button */}
        {isCurrent ? (
          <button
            disabled
            className="w-full border border-blue-500/40 text-blue-400 rounded-xl py-2.5 text-sm font-medium opacity-80 cursor-default"
          >
            Current plan
          </button>
        ) : (
          <button
            onClick={() => onSelect(plan.id)}
            disabled={loading}
            className={`w-full flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-medium transition-colors ${
              isPro
                ? 'bg-blue-600 hover:bg-blue-500 text-white'
                : 'bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700'
            } disabled:opacity-60`}
          >
            {loading && <Loader2 size={14} className="animate-spin" />}
            {loading ? 'Redirecting…' : buttonLabel}
          </button>
        )}
      </div>
    </div>
  );
}

function FeatureItem({
  text,
  unlimited,
  highlight,
}: {
  text: string;
  unlimited?: boolean;
  highlight?: boolean;
}) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      <div
        className={`flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center ${
          highlight
            ? 'bg-violet-500/20 text-violet-400'
            : unlimited
            ? 'bg-blue-500/20 text-blue-400'
            : 'bg-gray-700/80 text-gray-400'
        }`}
      >
        <Check size={10} strokeWidth={2.5} />
      </div>
      <span className={highlight ? 'text-violet-300' : unlimited ? 'text-blue-300' : 'text-gray-400'}>
        {text}
      </span>
    </li>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BillingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentPlan, setCurrentPlan] = useState<string>('free');
  const [subscription, setSubscription] = useState<{
    status: string;
    current_period_end?: string;
  } | null>(null);
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getPlans(), getMyTenant(), getSubscription()])
      .then(([p, t, s]) => {
        setPlans(p);
        setCurrentPlan(t.plan);
        setSubscription(s?.subscription ?? null);
      })
      .catch(() => setError('Failed to load billing information.'))
      .finally(() => setPageLoading(false));
  }, []);

  const handleSelect = async (planId: string) => {
    setLoadingPlan(planId);
    setError(null);
    try {
      const { payment_link_url } = await createCheckout(planId);
      window.location.href = payment_link_url;
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Checkout failed. Please try again.';
      setError(msg);
      setLoadingPlan(null);
    }
  };

  const handleCancel = async () => {
    if (!confirm('Cancel your subscription and revert to Free plan at end of billing period?'))
      return;
    setCancelling(true);
    try {
      await cancelSubscription();
      window.location.reload();
    } catch {
      setError('Failed to cancel subscription. Please try again.');
      setCancelling(false);
    }
  };

  const isFreePlan = currentPlan === 'free' || !currentPlan;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-xl font-semibold text-gray-100">Billing</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage your subscription and payment details
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm mb-6">
            <AlertCircle size={15} />
            {error}
          </div>
        )}

        {/* Current plan banner */}
        {!pageLoading && (
          <div
            className={`rounded-2xl border p-5 mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 ${
              isFreePlan
                ? 'bg-gray-900 border-gray-800'
                : 'bg-blue-500/5 border-blue-500/30'
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  isFreePlan ? 'bg-gray-800' : 'bg-blue-500/15'
                }`}
              >
                <CreditCard size={18} className={isFreePlan ? 'text-gray-400' : 'text-blue-400'} />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-100 capitalize">
                  {currentPlan || 'Free'} Plan
                </p>
                {isFreePlan ? (
                  <p className="text-xs text-gray-500 mt-0.5">
                    Upgrade to automate more applications
                  </p>
                ) : subscription ? (
                  <p className="text-xs text-gray-400 mt-0.5">
                    <span className="text-emerald-400 font-medium">Active</span>
                    {subscription.current_period_end && (
                      <> · renews {formatRenewalDate(subscription.current_period_end)}</>
                    )}
                  </p>
                ) : null}
              </div>
            </div>
            {!isFreePlan && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50"
              >
                {cancelling && <Loader2 size={12} className="animate-spin" />}
                Cancel subscription
              </button>
            )}
          </div>
        )}

        {/* Plan cards */}
        {pageLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-10">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="bg-gray-900 border border-gray-800 rounded-2xl p-6 animate-pulse"
              >
                <div className="h-5 bg-gray-800 rounded w-24 mb-3" />
                <div className="h-8 bg-gray-800 rounded w-32 mb-6" />
                <div className="space-y-2.5">
                  {[1, 2, 3, 4].map((j) => (
                    <div key={j} className="h-3.5 bg-gray-800 rounded w-full" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-10">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                isCurrent={plan.id === currentPlan}
                isPopular={plan.id === 'pro'}
                currentPlanId={currentPlan}
                onSelect={handleSelect}
                loading={loadingPlan === plan.id}
              />
            ))}
          </div>
        )}

        {/* FAQ section */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl px-6 pt-2 pb-2">
          <h2 className="text-sm font-semibold text-gray-200 pt-4 mb-2">
            Frequently asked questions
          </h2>
          {FAQ_ITEMS.map((item) => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      </div>
    </div>
  );
}
