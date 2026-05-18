'use client';

import { useEffect, useState, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { verifyCallback } from '@/lib/api';

type State = 'verifying' | 'success' | 'failed';

export default function BillingSuccessPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [state, setState] = useState<State>('verifying');
  const [plan, setPlan] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(5);
  const called = useRef(false);

  useEffect(() => {
    if (called.current) return;
    called.current = true;

    const payment_id = searchParams.get('razorpay_payment_id');
    const link_id = searchParams.get('razorpay_payment_link_id');
    const ref_id = searchParams.get('razorpay_payment_link_reference_id');
    const link_status = searchParams.get('razorpay_payment_link_status');
    const signature = searchParams.get('razorpay_signature');

    if (!payment_id || !link_id || !ref_id || !link_status || !signature) {
      setState('failed');
      return;
    }

    verifyCallback({
      razorpay_payment_id: payment_id,
      razorpay_payment_link_id: link_id,
      razorpay_payment_link_reference_id: ref_id,
      razorpay_payment_link_status: link_status,
      razorpay_signature: signature,
    })
      .then((res) => {
        if (res.activated) {
          setPlan(res.plan ?? null);
          setState('success');
        } else {
          setState('failed');
        }
      })
      .catch(() => setState('failed'));
  }, [searchParams]);

  // Countdown redirect on success
  useEffect(() => {
    if (state !== 'success') return;
    if (countdown <= 0) {
      router.push('/billing');
      return;
    }
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [state, countdown, router]);

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center">
        {state === 'verifying' && (
          <>
            <Loader2 size={48} className="animate-spin text-blue-400 mx-auto mb-4" />
            <h1 className="text-lg font-semibold text-gray-100 mb-2">
              Verifying your payment…
            </h1>
            <p className="text-sm text-gray-500">This will only take a moment.</p>
          </>
        )}

        {state === 'success' && (
          <>
            <CheckCircle size={48} className="text-emerald-400 mx-auto mb-4" />
            <h1 className="text-lg font-semibold text-gray-100 mb-2">
              Payment successful!
            </h1>
            <p className="text-sm text-gray-400 mb-1">
              {plan
                ? `You're now on the ${plan.charAt(0).toUpperCase() + plan.slice(1)} plan.`
                : 'Your plan has been activated.'}
            </p>
            <p className="text-xs text-gray-600 mb-6">
              Redirecting to billing in {countdown}s…
            </p>
            <button
              onClick={() => router.push('/billing')}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded-xl py-2.5 text-sm font-medium transition-colors"
            >
              View my plan
            </button>
          </>
        )}

        {state === 'failed' && (
          <>
            <XCircle size={48} className="text-red-400 mx-auto mb-4" />
            <h1 className="text-lg font-semibold text-gray-100 mb-2">
              Payment verification failed
            </h1>
            <p className="text-sm text-gray-500 mb-6">
              Your payment may still be processing. Check your billing page or contact support if
              the issue persists.
            </p>
            <button
              onClick={() => router.push('/billing')}
              className="w-full bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 rounded-xl py-2.5 text-sm font-medium transition-colors"
            >
              Back to billing
            </button>
          </>
        )}
      </div>
    </div>
  );
}
