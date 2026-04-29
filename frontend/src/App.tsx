import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

type Merchant = {
  id: number;
  name: string;
};

type Payout = {
  id: number;
  amount_paise: number;
  status: "pending" | "processing" | "completed" | "failed";
  attempts: number;
  locked_at: string | null;
  created_at: string;
};

type DashboardResponse = {
  merchant: Merchant;
  balance_paise: number;
  payouts: Payout[];
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

function formatRupees(paise: number) {
  return `Rs ${(paise / 100).toFixed(2)}`;
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString();
}

export default function App() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState<number | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [amountPaise, setAmountPaise] = useState("1000");
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => crypto.randomUUID());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selectedMerchant = useMemo(
    () => merchants.find((merchant) => merchant.id === selectedMerchantId) ?? null,
    [merchants, selectedMerchantId]
  );

  useEffect(() => {
    void fetch(`${API_BASE}/merchants`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load merchants.");
        }
        return response.json() as Promise<Merchant[]>;
      })
      .then((merchantRows) => {
        setMerchants(merchantRows);
        if (merchantRows.length > 0) {
          setSelectedMerchantId(merchantRows[0].id);
        }
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedMerchantId) {
      return;
    }
    void refreshDashboard(selectedMerchantId);
  }, [selectedMerchantId]);

  async function refreshDashboard(merchantId: number) {
    const response = await fetch(`${API_BASE}/dashboard?merchant_id=${merchantId}`);
    if (!response.ok) {
      throw new Error("Failed to load dashboard data.");
    }
    const data = (await response.json()) as DashboardResponse;
    setDashboard(data);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!selectedMerchantId) {
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(`${API_BASE}/payouts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({
          merchant_id: selectedMerchantId,
          amount_paise: Number(amountPaise),
        }),
      });

      const data = (await response.json()) as { detail?: string; payout_id?: number; status?: string };
      if (!response.ok) {
        throw new Error(data.detail ?? "Payout request failed.");
      }

      setMessage(`Payout ${data.payout_id} is ${data.status}.`);
      setIdempotencyKey(crypto.randomUUID());
      await refreshDashboard(selectedMerchantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-5xl px-4 py-10">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold">Playto Payout Dashboard</h1>
          <p className="mt-2 text-sm text-slate-400">Track merchant balance, create payouts, and inspect payout history.</p>
        </header>

        <section className="mb-6 rounded-xl border border-slate-800 bg-slate-900 p-4">
          <label className="mb-2 block text-sm text-slate-300" htmlFor="merchant">
            Merchant
          </label>
          <select
            id="merchant"
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2"
            value={selectedMerchantId ?? ""}
            onChange={(event) => setSelectedMerchantId(Number(event.target.value))}
          >
            {merchants.map((merchant) => (
              <option key={merchant.id} value={merchant.id}>
                {merchant.name}
              </option>
            ))}
          </select>
        </section>

        <div className="mb-6 grid gap-4 md:grid-cols-2">
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="text-lg font-medium">Balance</h2>
            <p className="mt-2 text-3xl font-semibold text-emerald-400">
              {dashboard ? formatRupees(dashboard.balance_paise) : "Loading..."}
            </p>
            <p className="mt-1 text-xs text-slate-400">{selectedMerchant?.name ?? "-"}</p>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="text-lg font-medium">Request Payout</h2>
            <form className="mt-3 space-y-3" onSubmit={handleSubmit}>
              <input
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                type="number"
                min={1}
                value={amountPaise}
                onChange={(event) => setAmountPaise(event.target.value)}
                placeholder="Amount in paise"
              />
              <input
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                type="text"
                value={idempotencyKey}
                onChange={(event) => setIdempotencyKey(event.target.value)}
                placeholder="Idempotency key"
              />
              <button
                disabled={loading || !selectedMerchantId}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-indigo-900"
                type="submit"
              >
                {loading ? "Submitting..." : "Create payout"}
              </button>
            </form>
          </section>
        </div>

        {error ? <p className="mb-4 rounded-md border border-rose-800 bg-rose-950 px-3 py-2 text-sm text-rose-300">{error}</p> : null}
        {message ? (
          <p className="mb-4 rounded-md border border-emerald-800 bg-emerald-950 px-3 py-2 text-sm text-emerald-300">{message}</p>
        ) : null}

        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-3 text-lg font-medium">Payout History</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-slate-400">
                <tr>
                  <th className="px-2 py-2">ID</th>
                  <th className="px-2 py-2">Amount</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Attempts</th>
                  <th className="px-2 py-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {dashboard?.payouts.map((payout) => (
                  <tr key={payout.id} className="border-t border-slate-800">
                    <td className="px-2 py-2">{payout.id}</td>
                    <td className="px-2 py-2">{formatRupees(payout.amount_paise)}</td>
                    <td className="px-2 py-2 capitalize">{payout.status}</td>
                    <td className="px-2 py-2">{payout.attempts}</td>
                    <td className="px-2 py-2">{formatDate(payout.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {dashboard && dashboard.payouts.length === 0 ? (
              <p className="mt-3 text-sm text-slate-400">No payouts yet for this merchant.</p>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
