import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate, Link } from 'react-router-dom';
import { 
  LayoutDashboard, 
  PlusCircle, 
  FileText, 
  ShieldCheck, 
  LogOut, 
  Activity,
  ChevronRight,
  User,
  Settings,
  Bell,
  ChevronDown
} from 'lucide-react';

import { authAPI } from '../api';

export default function Layout({ children, role }) {
  const navigate = useNavigate();
  const [userName, setUserName] = useState(localStorage.getItem('user_name') || (role === 'insurer' ? 'Sarah Chen' : 'Dr. Sarah Chen'));
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const stored = localStorage.getItem('theme');
    if (stored) return stored === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [showNotifications, setShowNotifications] = useState(false);

  useEffect(() => {
    const storedName = localStorage.getItem('user_name');
    if (storedName) {
      setUserName(storedName);
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.classList.remove('dark');
    localStorage.setItem('theme', 'light');
  }, []);

  const handleLogout = async () => {
    try {
      await authAPI.logout();
    } catch (e) {
      console.error('Logout error', e);
    } finally {
      localStorage.removeItem('user_role');
      localStorage.removeItem('user_id');
      localStorage.removeItem('user_name');
      window.location.href = '/login';
    }
  };

  const getInitials = (name) => {
    if (!name) return 'SC';
    const parts = name.replace(/^(Dr\.|Mr\.|Mrs\.|Ms\.)\s+/, '').split(' ');
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  // Mock Notifications
  const notifications = [
    {
      id: 'n1',
      title: 'PA Decision Issued',
      message: 'Request PA-2026-000184 (CT Head Scan) was APPROVED by Insurer.',
      time: '10 mins ago',
      unread: true,
      requestId: 'req_emergency_01'
    },
    {
      id: 'n2',
      title: 'Additional Info Requested',
      message: 'Insurer requested lumbar spine MRI clinical notes for PA-2026-000192.',
      time: '1 hour ago',
      unread: true,
      requestId: 'req_high_02'
    },
    {
      id: 'n3',
      title: 'Prior Approval Issued',
      message: 'Request PA-2026-000175 (Knee MRI w/ PT history) was APPROVED.',
      time: '3 hours ago',
      unread: false,
      requestId: 'req_med_03'
    },
    {
      id: 'n4',
      title: 'Decision Confirmed',
      message: 'Request PA-2026-000160 (Ambulatory X-Ray) confirmed Approved.',
      time: '1 day ago',
      unread: false,
      requestId: 'req_low_04'
    }
  ];

  return (
    <div className="flex min-h-screen bg-[#F8FAFC] dark:bg-[#0F172A] text-[#0F172A] dark:text-slate-100 font-sans transition-colors duration-200">
      {/* Sidebar - Deep Slate Navy #0F172A */}
      <aside className="w-64 bg-[#0F172A] dark:bg-slate-950 border-r border-slate-800 flex flex-col justify-between p-4 sticky top-0 h-screen z-20 text-white">
        <div>
          {/* Logo */}
          <div className="flex items-center space-x-3 px-3 py-4 mb-6 border-b border-slate-800">
            <img src="/logo.png" alt="PA-AUTH Logo" className="w-10 h-10 object-contain drop-shadow-md" />
            <div>
              <h1 className="font-extrabold text-base tracking-tight !text-white">PA-AUTH</h1>
              <p className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">
                {role === 'insurer' ? 'INSURER PORTAL' : 'HOSPITAL PORTAL'}
              </p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-2">
            {role === 'initiator' && (
              <>
                <NavLink
                  to="/dashboard"
                  className={({ isActive }) =>
                    `flex items-center space-x-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all ${
                      isActive
                        ? 'bg-[#2563EB] text-white shadow-md'
                        : 'text-slate-300 hover:bg-white/10 hover:text-white'
                    }`
                  }
                >
                  <LayoutDashboard className="w-4 h-4" />
                  <span>Dashboard</span>
                </NavLink>

                <NavLink
                  to="/new-request"
                  className={({ isActive }) =>
                    `flex items-center space-x-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all ${
                      isActive
                        ? 'bg-[#2563EB] text-white shadow-md'
                        : 'text-slate-300 hover:bg-white/10 hover:text-white'
                    }`
                  }
                >
                  <PlusCircle className="w-4 h-4" />
                  <span>New PA Request</span>
                </NavLink>
              </>
            )}

            {role === 'insurer' && (
              <NavLink
                to="/queue"
                className={({ isActive }) =>
                  `flex items-center space-x-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all ${
                    isActive
                      ? 'bg-[#2563EB] text-white shadow-md'
                      : 'text-slate-300 hover:bg-white/10 hover:text-white'
                  }`
                }
              >
                <ShieldCheck className="w-4 h-4" />
                <span>Review Queue</span>
              </NavLink>
            )}

            <NavLink
              to="/profile"
              className={({ isActive }) =>
                `flex items-center space-x-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all ${
                  isActive
                    ? 'bg-[#2563EB] text-white shadow-md'
                    : 'text-slate-300 hover:bg-white/10 hover:text-white'
                }`
              }
            >
              <User className="w-4 h-4" />
              <span>User Profile</span>
            </NavLink>
          </nav>
        </div>

        {/* User Info / Logout at Sidebar Bottom */}
        <div className="pt-4 border-t border-slate-800">
          <div className="flex items-center justify-between px-3 py-2">
            <Link to="/profile" className="flex items-center space-x-3 group">
              <div className="w-9 h-9 rounded-xl bg-[#2563EB] text-white font-black flex items-center justify-center text-xs shadow-md group-hover:ring-2 ring-blue-400 transition-all">
                {getInitials(userName)}
              </div>
              <div className="truncate">
                <p className="text-xs font-bold text-white group-hover:text-blue-300 truncate transition-colors">{userName}</p>
                <p className="text-[10px] text-slate-400 uppercase font-medium">
                  {role === 'insurer' ? 'Reviewer' : 'Hospital Staff'}
                </p>
              </div>
            </Link>
            <button
              onClick={handleLogout}
              title="Logout"
              className="p-2 text-slate-400 hover:text-red-400 hover:bg-white/10 rounded-xl transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#F8FAFC] dark:bg-[#0F172A] transition-colors duration-200">
        {/* Top Header */}
        <header className="h-16 bg-white dark:bg-slate-900 border-b border-[#E2E8F0] dark:border-slate-800 px-8 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div className="flex items-center space-x-2 text-xs text-[#64748B] dark:text-slate-400 font-medium">
            <span>Portal</span>
            <ChevronRight className="w-3.5 h-3.5" />
            <span>PA Requests</span>
            <ChevronRight className="w-3.5 h-3.5" />
            <span className="capitalize text-[#0F172A] dark:text-white font-bold">{role} Workspace</span>
          </div>

          <div className="flex items-center space-x-4">
            {/* Notifications Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowNotifications(!showNotifications)}
                className="p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 border border-[#E2E8F0] dark:border-slate-700 transition-colors relative"
              >
                <Bell className="w-4 h-4" />
                <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-[#2563EB] rounded-full ring-2 ring-white dark:ring-slate-900"></span>
              </button>

              {showNotifications && (
                <div className="absolute right-0 mt-3 w-96 bg-white dark:bg-slate-800 border border-[#E2E8F0] dark:border-slate-700 rounded-2xl shadow-2xl z-50 p-4 space-y-3 font-sans text-xs">
                  <div className="flex items-center justify-between border-b border-[#E2E8F0] dark:border-slate-700 pb-3">
                    <span className="font-extrabold text-sm text-[#0F172A] dark:text-white">Notifications</span>
                  </div>

                  <div className="space-y-2.5 max-h-80 overflow-y-auto">
                    {notifications.map((n) => (
                      <div key={n.id} className="p-3 bg-slate-50 dark:bg-slate-900/80 rounded-xl border border-[#E2E8F0] dark:border-slate-700/80 space-y-1 hover:border-[#2563EB] transition-all cursor-pointer">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-[#0F172A] dark:text-white text-xs">{n.title}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-300 text-[11px] leading-snug">{n.message}</p>
                        <span className="text-[10px] text-slate-400 block pt-1">{n.time}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Clickable Profile Header Block */}
            <button
              onClick={() => navigate('/profile')}
              className="flex items-center space-x-3 p-1.5 pr-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-[#E2E8F0] dark:border-slate-700 hover:border-[#2563EB] transition-all text-left group"
            >
              <div className="w-8 h-8 rounded-xl bg-[#0F172A] text-white font-black flex items-center justify-center text-xs shadow-md group-hover:bg-[#2563EB] transition-colors">
                {getInitials(userName)}
              </div>
              <div className="hidden sm:block">
                <p className="text-xs font-bold text-[#0F172A] dark:text-white leading-tight group-hover:text-[#2563EB] transition-colors">{userName}</p>
                <p className="text-[10px] text-[#64748B] dark:text-slate-400 font-medium">
                  {role === 'insurer' ? 'Insurance Reviewer' : 'Hospital Staff'}
                </p>
              </div>
            </button>
          </div>
        </header>

        {/* Page Body */}
        <main className="flex-1 p-8 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
