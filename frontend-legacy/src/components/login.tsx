import { useState } from "react";
import jppLogo from "../assets/jpp.png";
import { loginUser } from "../api/users";
import type { UserRead } from "../api/users";

interface LoginProps {
  onLogin?: (user: UserRead) => void;
}



export default function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setLoading(true);
    try {
      const user = await loginUser(email, password);
      setLoading(false);
      onLogin?.(user);
    } catch (err: unknown) {
      setLoading(false);
      const message = err instanceof Error ? err.message : "";
      if (message === "banned") {
        setError("This account has been suspended. Please contact an administrator.");
      } else {
        setError("Invalid credentials. Please try again.");
      }
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm">
        {/* Logo + heading */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="grid h-14 w-14 place-items-center overflow-hidden rounded-xl bg-[#ce1b22] shadow-md">
            <img src={jppLogo} alt="JPP logo" className="h-full w-full object-cover" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold text-[#302d27]">Welcome back</h1>
            <p className="mt-1 text-sm text-stone-500">Sign in to Jablonsky Data Platform</p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-stone-200 bg-white p-8 shadow-sm">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {/* Email */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium text-[#302d27]">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10"
              />
            </div>

            {/* Password */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-sm font-medium text-[#302d27]">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10"
              />
            </div>

            {/* Error */}
            {error && (
              <p className="rounded-lg bg-red-50 px-4 py-2.5 text-sm text-[#ce1b22]">
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="mt-1 flex h-11 items-center justify-center rounded-lg bg-[#ce1b22] text-sm font-semibold text-white transition hover:bg-[#b01820] disabled:opacity-60"
            >
              {loading ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                "Sign in"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
