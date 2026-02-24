import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { parseDashboardHtml, ParsedData } from '../utils/parser';
import {
  Activity, Users, Target, Layers, DollarSign,
  AlertTriangle, Settings, FileBox, ChevronLeft, ChevronRight,
  Eye, EyeOff, Plus, Trash2, Power, CheckCircle2, XCircle,
  TrendingUp, TrendingDown, Zap, Clock, Cpu, MemoryStick,
  Globe, ShoppingCart, Youtube, BookOpen, Twitter, Coffee,
  Package, BarChart3, RefreshCw, Terminal, Image, FileText,
  AlertCircle, Info, CheckCheck, Wifi, WifiOff
} from 'lucide-react';

const SECTIONS = [
  { id: 'status',    label: 'Статус',    icon: Activity },
  { id: 'agents',   label: 'Агенты',    icon: Users },
  { id: 'goals',    label: 'Цели',      icon: Target },
  { id: 'platforms',label: 'Платформы', icon: Layers },
  { id: 'finance',  label: 'Финансы',   icon: DollarSign },
  { id: 'events',   label: 'События',   icon: AlertTriangle },
  { id: 'config',   label: 'Конфиг',    icon: Settings },
  { id: 'output',   label: 'Вывод',     icon: FileBox },
];

// Platform icons mapping
const PLATFORM_ICONS: Record<string, { icon: React.ComponentType<any>; color: string; label: string }> = {
  'gumroad':   { icon: ShoppingCart, color: '#ff90e8', label: 'Gumroad' },
  'etsy':      { icon: ShoppingCart, color: '#f56400', label: 'Etsy' },
  'shopify':   { icon: Package,      color: '#96bf48', label: 'Shopify' },
  'amazon':    { icon: Package,      color: '#ff9900', label: 'Amazon KDP' },
  'kdp':       { icon: BookOpen,     color: '#ff9900', label: 'Amazon KDP' },
  'youtube':   { icon: Youtube,      color: '#ff0000', label: 'YouTube' },
  'wordpress': { icon: Globe,        color: '#21759b', label: 'WordPress' },
  'medium':    { icon: BookOpen,     color: '#00ab6c', label: 'Medium' },
  'twitter':   { icon: Twitter,      color: '#1da1f2', label: 'Twitter/X' },
  'kofi':      { icon: Coffee,       color: '#29abe0', label: 'Ko-fi' },
  'ko_fi':     { icon: Coffee,       color: '#29abe0', label: 'Ko-fi' },
  'telegram':  { icon: Zap,          color: '#2ca5e0', label: 'Telegram' },
  'replicate': { icon: Cpu,          color: '#8b5cf6', label: 'Replicate' },
  'openai':    { icon: Zap,          color: '#74aa9c', label: 'OpenAI' },
  'anthropic': { icon: Terminal,     color: '#d4a574', label: 'Anthropic' },
};

function getPlatformMeta(filename: string) {
  const name = filename.replace('.py', '').toLowerCase();
  for (const [key, meta] of Object.entries(PLATFORM_ICONS)) {
    if (name.includes(key)) return meta;
  }
  return { icon: Globe, color: '#64748b', label: filename.replace('.py', '') };
}

// Agent status inference
function getAgentStatus(module: string): 'active' | 'idle' | 'error' {
  const lower = module.toLowerCase();
  if (lower.includes('core') || lower.includes('decision') || lower.includes('memory')) return 'active';
  if (lower.includes('error') || lower.includes('fail')) return 'error';
  return 'idle';
}

function AgentStatusBadge({ status }: { status: 'active' | 'idle' | 'error' }) {
  const map = {
    active: { color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', dot: 'bg-emerald-400', label: 'Активен' },
    idle:   { color: 'bg-slate-700/50 text-slate-400 border-slate-600/30',       dot: 'bg-slate-500',   label: 'Простой' },
    error:  { color: 'bg-rose-500/20 text-rose-400 border-rose-500/30',           dot: 'bg-rose-400',    label: 'Ошибка' },
  };
  const s = map[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${s.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${status === 'active' ? 'animate-pulse' : ''}`} />
      {s.label}
    </span>
  );
}

function MetricCard({ label, value, sub, accent = false }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className={`bg-slate-800/60 backdrop-blur-sm p-5 rounded-2xl border transition-all group ${accent ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-slate-700 hover:border-slate-600'}`}>
      <div className="text-[10px] uppercase tracking-widest font-bold text-slate-500 mb-2 group-hover:text-slate-400 transition-colors">{label}</div>
      <div className={`text-2xl font-mono font-bold truncate ${accent ? 'text-emerald-400' : 'text-white'}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-1 truncate">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<ParsedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [direction, setDirection] = useState(0);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Config state
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [disabledKeys, setDisabledKeys] = useState<Record<string, boolean>>({});
  const [rssSources, setRssSources] = useState<Array<{ url: string; active: boolean }>>([]);
  const [newRss, setNewRss] = useState('');

  const fetchData = async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const res = await fetch('/api/proxy');
      const html = await res.text();
      const parsed = parseDashboardHtml(html);
      setData(parsed);
      setLastUpdate(new Date());
      setError('');
      if (rssSources.length === 0) {
        const rss = Object.keys(parsed.config)
          .filter(k => k.includes('RSS'))
          .map(k => ({ url: parsed.config[k], active: true }));
        setRssSources(rss);
      }
    } catch (err: any) {
      setError(err.message || 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const navigate = (newIndex: number) => {
    setDirection(newIndex > currentIndex ? 1 : -1);
    setCurrentIndex(newIndex);
  };

  const variants = {
    enter: (d: number) => ({ y: d > 0 ? 16 : -16, opacity: 0, scale: 0.99 }),
    center: { zIndex: 1, y: 0, opacity: 1, scale: 1 },
    exit: (d: number) => ({ zIndex: 0, y: d < 0 ? 16 : -16, opacity: 0, scale: 0.99 }),
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0f1e] flex flex-col items-center justify-center text-emerald-400">
        <div className="relative">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-emerald-500 flex items-center justify-center text-white font-black text-3xl shadow-2xl shadow-indigo-500/30 animate-pulse">V</div>
        </div>
        <p className="text-slate-500 font-medium mt-6 animate-pulse text-sm tracking-widest uppercase">Загрузка VITO...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0f1e] flex items-center justify-center p-6">
        <div className="text-center max-w-md bg-rose-950/20 p-8 rounded-3xl border border-rose-900/50">
          <WifiOff className="w-14 h-14 mx-auto mb-4 text-rose-400" />
          <h2 className="text-xl font-bold text-white mb-2">Нет соединения</h2>
          <p className="text-rose-300/70 mb-6 text-sm">{error}</p>
          <button onClick={() => fetchData(true)} className="px-6 py-2.5 bg-rose-600 hover:bg-rose-500 text-white rounded-xl transition-colors font-semibold text-sm">
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  const currentSection = SECTIONS[currentIndex];

  // ─── SECTION RENDERERS ──────────────────────────────────────────────────────

  const renderStatus = () => {
    if (!data) return null;
    const st = data.status;

    // Extract key metrics
    const statusValue = st['Статус'] || st['status'] || st['STATUS'] || 'ACTIVE';
    const uptimeValue = st['Аптайм'] || st['uptime'] || st['Uptime'] || '—';
    const cpuValue = st['CPU'] || st['cpu'] || '—';
    const ramValue = st['RAM'] || st['ram'] || st['Память'] || '—';
    const pidValue = st['PID'] || st['pid'] || '—';
    const taskValue = st['Задача'] || st['task'] || st['Текущая задача'] || st['current_task'] || null;

    // Find goal / current activity
    const goalEntries = Object.entries(st).filter(([k]) =>
      k.toLowerCase().includes('goal') || k.toLowerCase().includes('цел') || k.toLowerCase().includes('task')
    );

    return (
      <div className="space-y-6">
        {/* Hero status bar */}
        <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-sm rounded-3xl border border-slate-700 p-6 flex flex-wrap items-center gap-6 shadow-2xl">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="w-3 h-3 bg-emerald-400 rounded-full animate-pulse" />
              <div className="absolute inset-0 w-3 h-3 bg-emerald-400 rounded-full animate-ping opacity-40" />
            </div>
            <span className="text-emerald-400 font-bold text-sm uppercase tracking-widest">{statusValue}</span>
          </div>
          <div className="h-6 w-px bg-slate-700" />
          <div className="flex items-center gap-2 text-slate-400 text-sm"><Clock size={14} /><span>{uptimeValue}</span></div>
          {cpuValue !== '—' && <><div className="h-6 w-px bg-slate-700" /><div className="flex items-center gap-2 text-slate-400 text-sm"><Cpu size={14} /><span>CPU {cpuValue}</span></div></>}
          {ramValue !== '—' && <><div className="h-6 w-px bg-slate-700" /><div className="flex items-center gap-2 text-slate-400 text-sm"><MemoryStick size={14} /><span>RAM {ramValue}</span></div></>}
          {pidValue !== '—' && <><div className="h-6 w-px bg-slate-700" /><div className="flex items-center gap-2 text-slate-400 text-sm"><Terminal size={14} /><span>PID {pidValue}</span></div></>}
          <div className="ml-auto text-[11px] text-slate-600 font-mono">
            {lastUpdate ? `обновлено ${lastUpdate.toLocaleTimeString('ru')}` : ''}
          </div>
        </div>

        {/* Current task highlight */}
        {taskValue && (
          <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-2xl p-5">
            <div className="text-[10px] uppercase tracking-widest font-bold text-indigo-400 mb-2">Текущая задача</div>
            <div className="text-white font-medium text-sm leading-relaxed">{taskValue}</div>
          </div>
        )}

        {/* All status metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Object.entries(st)
            .filter(([k]) => !['Статус','status','STATUS'].includes(k))
            .map(([key, value]) => (
              <MetricCard key={key} label={key} value={value} />
            ))}
        </div>
      </div>
    );
  };

  const renderAgents = () => {
    if (!data) return null;
    const agents = data.agents;
    const active = agents.filter(a => getAgentStatus(a.module) === 'active').length;
    const idle = agents.filter(a => getAgentStatus(a.module) === 'idle').length;

    return (
      <div className="space-y-5">
        {/* Summary bar */}
        <div className="flex gap-4 flex-wrap">
          <div className="bg-slate-800/60 rounded-2xl border border-slate-700 px-5 py-3 flex items-center gap-3">
            <span className="text-2xl font-black text-white">{agents.length}</span>
            <span className="text-xs text-slate-400 uppercase tracking-wider">агентов</span>
          </div>
          <div className="bg-emerald-500/10 rounded-2xl border border-emerald-500/20 px-5 py-3 flex items-center gap-3">
            <span className="text-2xl font-black text-emerald-400">{active}</span>
            <span className="text-xs text-emerald-400/70 uppercase tracking-wider">активных</span>
          </div>
          <div className="bg-slate-800/40 rounded-2xl border border-slate-700/50 px-5 py-3 flex items-center gap-3">
            <span className="text-2xl font-black text-slate-400">{idle}</span>
            <span className="text-xs text-slate-500 uppercase tracking-wider">простой</span>
          </div>
        </div>

        {/* Agent cards grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {agents.map((agent, i) => {
            const status = getAgentStatus(agent.module);
            const name = agent.module.replace('.py', '').replace(/_/g, ' ');
            return (
              <div key={i} className={`bg-slate-800/50 backdrop-blur-sm p-4 rounded-2xl border transition-all ${
                status === 'active' ? 'border-emerald-500/30 bg-emerald-500/5' :
                status === 'error'  ? 'border-rose-500/30 bg-rose-500/5' :
                'border-slate-700 hover:border-slate-600'
              }`}>
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${
                    status === 'active' ? 'bg-emerald-500/20' :
                    status === 'error'  ? 'bg-rose-500/20' : 'bg-slate-700'
                  }`}>
                    <Terminal size={16} className={
                      status === 'active' ? 'text-emerald-400' :
                      status === 'error'  ? 'text-rose-400' : 'text-slate-500'
                    } />
                  </div>
                  <AgentStatusBadge status={status} />
                </div>
                <div className="font-mono text-sm text-white capitalize mb-1 truncate">{name}</div>
                <div className="text-[11px] text-slate-500">{agent.lastModified || 'нет данных'}</div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderGoals = () => {
    if (!data) return null;

    if (data.goals.length === 0) {
      return (
        <div className="bg-slate-800/50 p-16 rounded-3xl border border-slate-700 text-center">
          <Target className="w-14 h-14 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400 text-lg font-medium mb-2">Активных целей нет</p>
          <p className="text-slate-600 text-sm">VITO ожидает новых задач</p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        {data.goals.map((goal: any, i: number) => {
          const isObj = typeof goal === 'object';
          const title = isObj ? (goal.title || goal.name || goal.goal || `Цель ${i + 1}`) : String(goal);
          const status = isObj ? (goal.status || 'active') : 'active';
          const progress = isObj ? (goal.progress || 0) : 0;
          const steps = isObj ? (goal.steps || []) : [];

          return (
            <div key={i} className="bg-slate-800/60 rounded-2xl border border-slate-700 p-6 hover:border-indigo-500/30 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-indigo-500/20 flex items-center justify-center">
                    <Target size={16} className="text-indigo-400" />
                  </div>
                  <div>
                    <div className="font-semibold text-white text-sm">{title}</div>
                    {isObj && goal.type && <div className="text-[11px] text-slate-500 mt-0.5">{goal.type}</div>}
                  </div>
                </div>
                <span className={`text-[10px] uppercase tracking-wider px-2.5 py-1 rounded-full font-bold ${
                  status === 'completed' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                  status === 'failed'    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
                  'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
                }`}>{status}</span>
              </div>

              {progress > 0 && (
                <div className="mb-4">
                  <div className="flex justify-between text-[11px] text-slate-500 mb-1.5">
                    <span>Прогресс</span><span>{progress}%</span>
                  </div>
                  <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full transition-all" style={{ width: `${progress}%` }} />
                  </div>
                </div>
              )}

              {steps.length > 0 && (
                <div className="space-y-1.5">
                  {steps.slice(0, 4).map((step: any, j: number) => (
                    <div key={j} className="flex items-center gap-2 text-[12px]">
                      <CheckCheck size={12} className={step.done ? 'text-emerald-400' : 'text-slate-600'} />
                      <span className={step.done ? 'text-slate-400 line-through' : 'text-slate-300'}>{String(step.action || step)}</span>
                    </div>
                  ))}
                  {steps.length > 4 && <div className="text-[11px] text-slate-600 pl-5">+{steps.length - 4} шагов</div>}
                </div>
              )}

              {!isObj && (
                <pre className="text-[11px] text-slate-400 bg-slate-900/50 rounded-xl p-3 overflow-x-auto mt-2">{JSON.stringify(goal, null, 2)}</pre>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderPlatforms = () => {
    if (!data) return null;

    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {data.platforms.map((p, i) => {
          const meta = getPlatformMeta(p.file);
          const Icon = meta.icon;
          const isConnected = !p.file.includes('stub') && !p.file.includes('placeholder');

          return (
            <div key={i} className="bg-slate-800/50 p-5 rounded-2xl border border-slate-700 hover:border-slate-500 transition-all flex flex-col items-center text-center group cursor-default">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3 transition-all"
                style={{ backgroundColor: `${meta.color}18`, border: `1px solid ${meta.color}30` }}>
                <Icon size={22} style={{ color: meta.color }} />
              </div>
              <span className="text-xs font-bold text-white mb-1">{meta.label}</span>
              <span className="text-[10px] font-mono text-slate-600 mb-2 truncate w-full">{p.file}</span>
              <div className={`flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider ${isConnected ? 'text-emerald-400' : 'text-slate-600'}`}>
                <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                {isConnected ? 'Активен' : 'Откл.'}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderFinance = () => {
    if (!data) return null;

    const items = data.finance;
    const totalSpend = items.reduce((sum, f) => sum + parseFloat(f.spend || '0'), 0);
    const DAILY_LIMIT = 3.0;
    const progressPct = Math.min((totalSpend / DAILY_LIMIT) * 100, 100);

    // Try to find earned from config/status
    const earned = parseFloat((data.status as any)?.['Заработано'] || (data.config as any)?.['EARNED'] || '0');

    return (
      <div className="space-y-6">
        {/* P&L Header */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-rose-500/10 border border-rose-500/20 rounded-2xl p-5">
            <div className="text-[10px] uppercase tracking-widest font-bold text-rose-400/70 mb-1">Потрачено</div>
            <div className="text-3xl font-black text-rose-400 font-mono">${totalSpend.toFixed(4)}</div>
            <div className="text-[11px] text-rose-400/50 mt-1">из ${DAILY_LIMIT} лимита</div>
          </div>
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-2xl p-5">
            <div className="text-[10px] uppercase tracking-widest font-bold text-emerald-400/70 mb-1">Заработано</div>
            <div className="text-3xl font-black text-emerald-400 font-mono">${earned.toFixed(4)}</div>
            <div className="text-[11px] text-emerald-400/50 mt-1">доход от продаж</div>
          </div>
          <div className={`border rounded-2xl p-5 ${earned - totalSpend >= 0 ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-slate-800/50 border-slate-700'}`}>
            <div className="text-[10px] uppercase tracking-widest font-bold text-slate-400/70 mb-1">ROI</div>
            <div className={`text-3xl font-black font-mono flex items-center gap-2 ${earned - totalSpend >= 0 ? 'text-emerald-400' : 'text-slate-400'}`}>
              {earned - totalSpend >= 0 ? <TrendingUp size={24} /> : <TrendingDown size={24} />}
              ${(earned - totalSpend).toFixed(4)}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">прибыль/убыток</div>
          </div>
        </div>

        {/* Daily limit progress */}
        <div className="bg-slate-800/60 border border-slate-700 rounded-2xl p-5">
          <div className="flex justify-between text-xs mb-3">
            <span className="text-slate-400 font-semibold">Дневной лимит API</span>
            <span className={`font-mono font-bold ${progressPct > 80 ? 'text-rose-400' : progressPct > 50 ? 'text-amber-400' : 'text-emerald-400'}`}>
              ${totalSpend.toFixed(4)} / ${DAILY_LIMIT}
            </span>
          </div>
          <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${progressPct > 80 ? 'bg-rose-500' : progressPct > 50 ? 'bg-amber-500' : 'bg-emerald-500'}`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-600 mt-2">{progressPct.toFixed(1)}% использовано</div>
        </div>

        {/* Finance history */}
        <div className="bg-slate-800/50 rounded-2xl border border-slate-700 overflow-hidden">
          <div className="p-4 border-b border-slate-700 bg-slate-900/30">
            <h3 className="text-sm font-bold text-slate-300">История расходов</h3>
          </div>
          <div className="divide-y divide-slate-700/50">
            {items.map((f, i) => (
              <div key={i} className="flex items-center justify-between p-4 hover:bg-slate-700/20 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-rose-500/10 flex items-center justify-center">
                    <DollarSign size={14} className="text-rose-400" />
                  </div>
                  <span className="text-sm text-slate-300">{f.date}</span>
                </div>
                <span className="font-mono font-bold text-rose-400">${parseFloat(f.spend).toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const renderEvents = () => {
    if (!data) return null;

    const parseEvent = (ev: string) => {
      const isError   = /error|critical|fail/i.test(ev);
      const isWarning = /warning|warn/i.test(ev);
      const isSuccess = /success|complete|done|✓/i.test(ev);
      return { isError, isWarning, isSuccess };
    };

    return (
      <div className="space-y-2 max-h-[65vh] overflow-y-auto pr-1 custom-scrollbar">
        {data.events.length === 0 ? (
          <div className="bg-slate-800/50 p-12 rounded-2xl border border-slate-700 text-center">
            <CheckCheck className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-500">Нет событий</p>
          </div>
        ) : data.events.map((ev, i) => {
          const { isError, isWarning, isSuccess } = parseEvent(ev);
          return (
            <div key={i} className={`flex gap-3 p-4 rounded-xl border text-xs transition-all ${
              isError   ? 'bg-rose-950/30 border-rose-900/40 text-rose-200' :
              isWarning ? 'bg-amber-950/30 border-amber-900/40 text-amber-200' :
              isSuccess ? 'bg-emerald-950/30 border-emerald-900/40 text-emerald-200' :
              'bg-slate-800/40 border-slate-700/50 text-slate-300'
            }`}>
              <div className="shrink-0 mt-0.5">
                {isError   ? <AlertCircle size={14} className="text-rose-400" /> :
                 isWarning ? <AlertTriangle size={14} className="text-amber-400" /> :
                 isSuccess ? <CheckCircle2 size={14} className="text-emerald-400" /> :
                 <Info size={14} className="text-slate-500" />}
              </div>
              <span className="font-mono whitespace-pre-wrap break-all leading-relaxed">{ev}</span>
            </div>
          );
        })}
      </div>
    );
  };

  const renderConfig = () => {
    if (!data) return null;
    return (
      <div className="space-y-6">
        <div className="bg-slate-800/50 rounded-3xl border border-slate-700 overflow-hidden shadow-xl">
          <div className="p-5 border-b border-slate-700 bg-slate-900/30 flex justify-between items-center">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Settings size={16} className="text-indigo-400" /> Переменные окружения
            </h3>
            <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Secrets</span>
          </div>
          <div className="divide-y divide-slate-700/40">
            {Object.entries(data.config).map(([key, value]) => {
              const isSecret = value === '***' || /key|secret|token|password/i.test(key);
              const isDisabled = disabledKeys[key];
              const display = isSecret && !showSecrets[key] ? '••••••••••••••' : value;
              return (
                <div key={key} className={`flex items-center gap-4 p-4 transition-colors group ${isDisabled ? 'opacity-40' : 'hover:bg-slate-700/20'}`}>
                  <span className="font-mono text-xs text-emerald-400 w-1/3 truncate shrink-0">{key}</span>
                  <span className="font-mono text-xs text-slate-400 flex-1 truncate">{display}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    {isSecret && (
                      <button onClick={() => setShowSecrets(p => ({...p,[key]:!p[key]}))}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-white hover:bg-slate-700 transition-all">
                        {showSecrets[key] ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    )}
                    <button onClick={() => setDisabledKeys(p => ({...p,[key]:!p[key]}))}
                      className={`p-1.5 rounded-lg transition-all ${isDisabled ? 'text-rose-500 bg-rose-500/10' : 'text-emerald-500 hover:bg-emerald-500/10'}`}>
                      <Power size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-slate-800/50 rounded-3xl border border-slate-700 p-6 shadow-xl">
          <h3 className="text-sm font-bold text-white mb-5 flex items-center gap-2">
            <Globe size={16} className="text-indigo-400" /> Источники RSS
          </h3>
          <div className="space-y-3 mb-5">
            {rssSources.length === 0 && (
              <div className="text-center py-8 border-2 border-dashed border-slate-700 rounded-2xl">
                <p className="text-slate-500 text-sm">Список пуст</p>
              </div>
            )}
            {rssSources.map((rss, i) => (
              <div key={i} className={`flex items-center justify-between p-3 rounded-xl border ${rss.active ? 'bg-slate-900/50 border-slate-700' : 'opacity-50 border-slate-800'}`}>
                <div className="flex items-center gap-3 truncate mr-3">
                  <button onClick={() => {const u=[...rssSources];u[i].active=!u[i].active;setRssSources(u)}}
                    className={rss.active ? 'text-emerald-500 shrink-0' : 'text-slate-600 shrink-0'}>
                    {rss.active ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
                  </button>
                  <span className="text-xs text-slate-200 truncate">{rss.url}</span>
                </div>
                <button onClick={() => setRssSources(rssSources.filter((_,j)=>j!==i))}
                  className="text-rose-400 hover:text-white p-1.5 rounded-lg hover:bg-rose-500/20 transition-all shrink-0">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
          <form onSubmit={e=>{e.preventDefault();if(newRss.trim()){setRssSources([...rssSources,{url:newRss.trim(),active:true}]);setNewRss('')}}} className="flex gap-3">
            <input type="url" value={newRss} onChange={e=>setNewRss(e.target.value)} placeholder="URL RSS фида..."
              className="flex-1 bg-slate-900/50 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-all placeholder:text-slate-600" required />
            <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 transition-all font-bold text-sm">
              <Plus size={16} />
            </button>
          </form>
        </div>
      </div>
    );
  };

  const renderOutput = () => {
    if (!data) return null;

    const getFileIcon = (filename: string) => {
      if (/\.(png|jpg|jpeg|gif|webp)$/i.test(filename)) return <Image size={14} className="text-violet-400" />;
      if (/\.pdf$/i.test(filename)) return <FileText size={14} className="text-rose-400" />;
      if (/\.(md|txt)$/i.test(filename)) return <FileText size={14} className="text-blue-400" />;
      return <FileBox size={14} className="text-slate-400" />;
    };

    return (
      <div className="space-y-4">
        <div className="flex gap-3 text-xs text-slate-500">
          <span className="bg-slate-800 border border-slate-700 px-3 py-1.5 rounded-lg font-mono">{data.output.length} файлов</span>
        </div>
        <div className="bg-slate-800/50 rounded-2xl border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto max-h-[60vh] custom-scrollbar">
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-slate-900 border-b border-slate-700 z-10">
                <tr>
                  <th className="p-4 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Файл</th>
                  <th className="p-4 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Размер</th>
                  <th className="p-4 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Изменён</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/40">
                {data.output.map((out, i) => (
                  <tr key={i} className="hover:bg-slate-700/20 transition-colors group">
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        {getFileIcon(out.file)}
                        <span className="font-mono text-xs text-indigo-400 break-all">{out.file}</span>
                      </div>
                    </td>
                    <td className="p-4 text-xs text-slate-500 whitespace-nowrap font-mono">{out.size} B</td>
                    <td className="p-4 text-xs text-slate-400 whitespace-nowrap">{out.modified}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  };

  const renderContent = () => {
    switch (currentSection.id) {
      case 'status':    return renderStatus();
      case 'agents':    return renderAgents();
      case 'goals':     return renderGoals();
      case 'platforms': return renderPlatforms();
      case 'finance':   return renderFinance();
      case 'events':    return renderEvents();
      case 'config':    return renderConfig();
      case 'output':    return renderOutput();
      default:          return null;
    }
  };

  // ─── MAIN LAYOUT ────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0f1e] text-slate-200 font-sans selection:bg-indigo-500/30">
      {/* Background glows */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[15%] -left-[5%] w-[35%] h-[40%] bg-indigo-600/8 blur-[140px] rounded-full" />
        <div className="absolute top-[55%] -right-[5%] w-[25%] h-[35%] bg-emerald-500/5 blur-[140px] rounded-full" />
      </div>

      {/* Header */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-slate-900/70 backdrop-blur-xl border-b border-slate-800/80 z-50 flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-emerald-500 flex items-center justify-center text-white font-black text-xl shadow-lg shadow-indigo-500/20">V</div>
          <div>
            <h1 className="text-base font-black tracking-tight text-white leading-none">VITO <span className="text-indigo-400">MEGA</span></h1>
            <p className="text-[9px] text-slate-600 uppercase font-bold tracking-widest">Control Center</p>
          </div>
        </div>

        {/* Desktop nav */}
        <nav className="hidden lg:flex items-center gap-1 bg-slate-800/60 p-1 rounded-xl border border-slate-700/60">
          {SECTIONS.map((sec, idx) => {
            const Icon = sec.icon;
            const isActive = idx === currentIndex;
            return (
              <button key={sec.id} onClick={() => navigate(idx)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all duration-200 ${
                  isActive ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'text-slate-500 hover:text-white hover:bg-slate-700/50'
                }`}>
                <Icon size={13} />{sec.label}
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-3">
          <button onClick={() => fetchData(true)}
            className="p-2 rounded-lg text-slate-500 hover:text-white hover:bg-slate-700 transition-all">
            <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
          </button>
          <div className="hidden sm:flex items-center gap-2">
            <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
            <span className="text-xs text-emerald-400 font-mono font-bold">LIVE</span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="pt-24 pb-28 lg:pb-10 px-4 sm:px-6 lg:px-10 max-w-7xl mx-auto">
        {/* Section header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-slate-800 rounded-xl border border-slate-700">
              {React.createElement(currentSection.icon, { size: 22, className: 'text-indigo-400' })}
            </div>
            <h2 className="text-2xl font-black text-white tracking-tight">{currentSection.label}</h2>
          </div>
          <span className="text-xs font-bold text-slate-600 bg-slate-800/60 border border-slate-700 px-3 py-1.5 rounded-full font-mono">
            {currentIndex + 1}/{SECTIONS.length}
          </span>
        </div>

        {/* Content with animation */}
        <AnimatePresence initial={false} custom={direction} mode="wait">
          <motion.div key={currentIndex} custom={direction} variants={variants}
            initial="enter" animate="center" exit="exit"
            transition={{ y: { type: 'spring', stiffness: 350, damping: 35 }, opacity: { duration: 0.15 }, scale: { duration: 0.15 } }}>
            {renderContent()}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Mobile bottom nav */}
      <div className="lg:hidden fixed bottom-4 left-4 right-4 bg-slate-900/85 backdrop-blur-2xl border border-slate-700/80 z-50 p-2.5 rounded-2xl shadow-2xl flex justify-between items-center gap-2">
        <button onClick={() => currentIndex > 0 && navigate(currentIndex - 1)}
          disabled={currentIndex === 0}
          className="p-3 rounded-xl bg-slate-800 border border-slate-700 disabled:opacity-25 text-white active:scale-90 transition-all">
          <ChevronLeft size={20} />
        </button>
        <div className="flex gap-1.5 overflow-x-auto hide-scrollbar">
          {SECTIONS.map((sec, idx) => {
            const Icon = sec.icon;
            return (
              <button key={sec.id} onClick={() => navigate(idx)}
                className={`p-3 rounded-xl flex-shrink-0 transition-all active:scale-90 ${
                  idx === currentIndex ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'bg-slate-800 text-slate-500 border border-slate-700'
                }`}>
                <Icon size={18} />
              </button>
            );
          })}
        </div>
        <button onClick={() => currentIndex < SECTIONS.length - 1 && navigate(currentIndex + 1)}
          disabled={currentIndex === SECTIONS.length - 1}
          className="p-3 rounded-xl bg-slate-800 border border-slate-700 disabled:opacity-25 text-white active:scale-90 transition-all">
          <ChevronRight size={20} />
        </button>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        .hide-scrollbar::-webkit-scrollbar{display:none}
        .hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}
        .custom-scrollbar::-webkit-scrollbar{width:5px}
        .custom-scrollbar::-webkit-scrollbar-track{background:transparent}
        .custom-scrollbar::-webkit-scrollbar-thumb{background:#334155;border-radius:8px}
        .custom-scrollbar::-webkit-scrollbar-thumb:hover{background:#475569}
      `}} />
    </div>
  );
}
