'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ErrorBoundary } from '../components/ErrorBoundary';
import {
  LayoutDashboard,
  Briefcase,
  Building2,
  Search,
  Mail,
  AtSign,
  Settings,
  CreditCard,
  Users,
  UserCheck,
  Moon,
  Sun,
  LogOut,
  Bot,
  ChevronRight,
  User,
  ShieldOff,
  Send,
  ListChecks,
} from 'lucide-react';
import { Toaster } from 'react-hot-toast';
import { getAccessToken, clearTokens, getMe, type User as UserType } from '../lib/api';
import './globals.css';

// ── Nav config ────────────────────────────────────────────────────────────────

const MAIN_NAV = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/candidates', label: 'Candidates', icon: UserCheck },
  { href: '/jobs', label: 'Jobs', icon: Briefcase },
  { href: '/mnc-jobs', label: 'MNC Jobs', icon: Building2 },
  { href: '/mnc-companies', label: 'MNC List', icon: ListChecks },
  { href: '/consulting-jobs', label: 'Consulting Jobs', icon: Briefcase },
  { href: '/consulting-companies', label: 'Consulting List', icon: Users },
  { href: '/search', label: 'Search', icon: Search },
  { href: '/logs', label: 'Send Logs', icon: Mail },
  { href: '/hr-emails', label: 'HR Emails', icon: AtSign },
  { href: '/direct-send', label: 'Direct HR Send', icon: Send },
  { href: '/blacklist', label: 'Blacklist', icon: ShieldOff },
];

const ACCOUNT_NAV = [
  { href: '/settings', label: 'Settings', icon: Settings },
  { href: '/billing', label: 'Billing', icon: CreditCard },
  { href: '/users', label: 'Team', icon: Users },
];

// ── Page title map ─────────────────────────────────────────────────────────────

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/candidates': 'Candidates',
  '/jobs': 'Jobs',
  '/mnc-jobs': 'MNC Jobs',
  '/mnc-companies': 'MNC List',
  '/consulting-jobs': 'Consulting Jobs',
  '/consulting-companies': 'Consulting List',
  '/search': 'Search',
  '/logs': 'Send Logs',
  '/hr-emails': 'HR Email Analysis',
  '/direct-send': 'Direct HR Send',
  '/blacklist': 'Blacklist',
  '/settings': 'Settings',
  '/billing': 'Billing',
  '/users': 'Team',
  '/onboarding': 'Onboarding',
};

function getPageTitle(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  const segment = pathname.split('/').filter(Boolean).pop() ?? 'Page';
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}

// ── Sidebar nav item ──────────────────────────────────────────────────────────

function NavItem({
  href,
  label,
  icon: Icon,
  active,
  collapsed,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  active: boolean;
  collapsed: boolean;
}) {
  return (
    <Link
      href={href}
      title={collapsed ? label : undefined}
      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'
      }`}
    >
      <Icon size={18} className="shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({
  collapsed,
  onToggle,
  dark,
  onToggleDark,
  onLogout,
  user,
}: {
  collapsed: boolean;
  onToggle: () => void;
  dark: boolean;
  onToggleDark: () => void;
  onLogout: () => void;
  user: UserType | null;
}) {
  const pathname = usePathname();
  const initial = user?.email ? user.email[0].toUpperCase() : '?';

  return (
    <aside
      className={`${
        collapsed ? 'w-16' : 'w-60'
      } transition-all duration-200 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col shrink-0 h-screen`}
    >
      <div
        className={`flex items-center h-14 border-b border-gray-200 dark:border-gray-800 shrink-0 ${
          collapsed ? 'justify-center px-0' : 'justify-between px-4'
        }`}
      >
        {!collapsed && (
          <div className="flex items-center gap-2 min-w-0">
            <Bot size={20} className="text-blue-600 dark:text-blue-400 shrink-0" />
            <span className="font-bold text-gray-900 dark:text-gray-100 text-sm truncate">
              QuickHunt
            </span>
          </div>
        )}
        <button
          onClick={onToggle}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition-colors"
        >
          {collapsed ? (
            <Bot size={20} className="text-blue-600 dark:text-blue-400" />
          ) : (
            <ChevronRight size={18} className="rotate-180" />
          )}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-4">
        <div>
          {!collapsed && (
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
              Main
            </p>
          )}
          <div className="space-y-0.5">
            {MAIN_NAV.map(({ href, label, icon }) => (
              <NavItem
                key={href}
                href={href}
                label={label}
                icon={icon}
                active={pathname === href}
                collapsed={collapsed}
              />
            ))}
          </div>
        </div>

        <div>
          {!collapsed && (
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
              Account
            </p>
          )}
          <div className="space-y-0.5">
            {ACCOUNT_NAV.map(({ href, label, icon }) => (
              <NavItem
                key={href}
                href={href}
                label={label}
                icon={icon}
                active={pathname === href}
                collapsed={collapsed}
              />
            ))}
          </div>
        </div>

      </nav>

      <div className="border-t border-gray-200 dark:border-gray-800 p-2 space-y-0.5 shrink-0">
        <div
          className={`flex items-center gap-2.5 px-2 py-2 rounded-lg ${
            collapsed ? 'justify-center' : ''
          }`}
          title={collapsed ? (user?.email ?? '') : undefined}
        >
          <div className="w-7 h-7 rounded-full bg-blue-600 dark:bg-blue-500 flex items-center justify-center shrink-0">
            {user ? (
              <span className="text-xs font-semibold text-white">{initial}</span>
            ) : (
              <User size={14} className="text-white" />
            )}
          </div>
          {!collapsed && (
            <span className="text-xs text-gray-600 dark:text-gray-400 truncate flex-1">
              {user?.email ?? 'Loading...'}
            </span>
          )}
        </div>

        <button
          onClick={onToggleDark}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          className={`w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100 transition-colors ${
            collapsed ? 'justify-center' : ''
          }`}
        >
          {dark ? <Sun size={16} className="shrink-0" /> : <Moon size={16} className="shrink-0" />}
          {!collapsed && <span>{dark ? 'Light mode' : 'Dark mode'}</span>}
        </button>

        <button
          onClick={onLogout}
          title="Log out"
          className={`w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 transition-colors ${
            collapsed ? 'justify-center' : ''
          }`}
        >
          <LogOut size={16} className="shrink-0" />
          {!collapsed && <span>Log out</span>}
        </button>
      </div>
    </aside>
  );
}

// ── Header bar ────────────────────────────────────────────────────────────────

function Header() {
  const pathname = usePathname();
  const title = getPageTitle(pathname);

  return (
    <header className="h-14 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex items-center px-6 shrink-0">
      <nav className="flex items-center gap-1.5 text-sm">
        <span className="text-gray-400 dark:text-gray-500 font-medium">QuickHunt</span>
        <ChevronRight size={14} className="text-gray-300 dark:text-gray-600" />
        <span className="text-gray-900 dark:text-gray-100 font-semibold">{title}</span>
      </nav>
    </header>
  );
}

// ── Authenticated Layout Wrapper ─────────────────────────────────────────────

function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(false);
  const [user, setUser] = useState<UserType | null>(null);

  // Theme init
  useEffect(() => {
    const stored = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = stored ? stored === 'dark' : prefersDark;
    setDark(isDark);
    document.documentElement.classList.toggle('dark', isDark);
  }, []);

  // Sidebar collapse state persistence
  useEffect(() => {
    const stored = localStorage.getItem('sidebar_collapsed');
    if (stored === 'true') setCollapsed(true);
  }, []);

  // Auth guard
  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      router.replace('/auth/login');
      return;
    }
    getMe()
      .then((u) => {
        setUser(u);
        setAuthChecked(true);
      })
      .catch(() => {
        clearTokens();
        router.replace('/auth/login');
      });
  }, [router]);

  const toggleDark = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      document.documentElement.classList.toggle('dark', next);
      localStorage.setItem('theme', next ? 'dark' : 'light');
      return next;
    });
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('sidebar_collapsed', String(next));
      return next;
    });
  }, []);

  const handleLogout = useCallback(() => {
    clearTokens();
    router.replace('/auth/login');
  }, [router]);

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-200 dark:border-gray-700 border-t-blue-600" />
          <span className="text-sm text-gray-500 dark:text-gray-400">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
      <Sidebar
        collapsed={collapsed}
        onToggle={toggleCollapsed}
        dark={dark}
        onToggleDark={toggleDark}
        onLogout={handleLogout}
        user={user}
      />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}

// ── Root layout ───────────────────────────────────────────────────────────────

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isAuthPage = pathname.startsWith('/auth');
  const isLandingPage = pathname === '/';
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  
  useEffect(() => {
    const token = getAccessToken();
    setIsAuthenticated(!!token);
    
    // Redirect authenticated users from landing page to dashboard
    if (token && isLandingPage) {
      router.replace('/dashboard');
    }
  }, [pathname, router, isLandingPage]);

  // Show landing page for unauthenticated users on root
  // Show auth pages directly
  // Show dashboard layout for authenticated users
  const shouldShowLanding = isLandingPage && (isAuthenticated === false || isAuthenticated === null);
  const shouldShowAuth = isAuthPage;

  if (shouldShowLanding || shouldShowAuth) {
    return (
      <html lang="en" suppressHydrationWarning>
        <head>
          <title>AI Job Hunter</title>
          <meta name="description" content="AI-powered job application automation. Land your dream job faster with intelligent scraping, personalized cover letters, and automated outreach." />
          <script
            dangerouslySetInnerHTML={{
              __html: `
                (function(){
                  try {
                    var s = localStorage.getItem('theme');
                    var p = window.matchMedia('(prefers-color-scheme: dark)').matches;
                    if (s === 'dark' || (!s && p)) {
                      document.documentElement.classList.add('dark');
                    }
                  } catch(e){}
                })();
              `,
            }}
          />
        </head>
        <body className="bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100 min-h-screen antialiased">
          {children}
        </body>
      </html>
    );
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <title>AI Job Hunter</title>
        <meta name="description" content="AI-powered job application automation. Land your dream job faster with intelligent scraping, personalized cover letters, and automated outreach." />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function(){
                try {
                  var s = localStorage.getItem('theme');
                  var p = window.matchMedia('(prefers-color-scheme: dark)').matches;
                  if (s === 'dark' || (!s && p)) {
                    document.documentElement.classList.add('dark');
                  }
                } catch(e){}
              })();
            `,
          }}
        />
      </head>
      <body className="bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100 min-h-screen antialiased">
        <ErrorBoundary>
          <AuthenticatedLayout>{children}</AuthenticatedLayout>
        </ErrorBoundary>
      </body>
    </html>
  );
}
