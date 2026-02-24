import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { parseDashboardHtml, ParsedData } from '../utils/parser';
import {
  Activity,
  Users,
  Target,
  Layers,
  DollarSign,
  AlertTriangle,
  Settings,
  FileBox,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Power,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Cpu,
  HardDrive,
  Clock,
  Hash,
  ShieldCheck,
  Info,
  Check,
  X,
  ShoppingBag,
  Globe,
  Youtube,
  Rss,
  Twitter,
  BookOpen
} from 'lucide-react';

const SECTIONS = [
  { id: 'status', label: 'Статус', icon: Activity },
  { id: 'agents', label: 'Агенты', icon: Users },
  { id: 'goals', label: 'Цели', icon: Target },
  { id: 'platforms', label: 'Платформы', icon: Layers },
  { id: 'finance', label: 'Финансы', icon: DollarSign },
  { id: 'events', label: 'События', icon: AlertTriangle },
  { id: 'config', label: 'Конфиг', icon: Settings },
  { id: 'output', label: 'Вывод', icon: FileBox },
];

const PLATFORM_ICONS: Record<string, React.ElementType> = {
  gumroad: ShoppingBag,
  etsy: ShoppingBag,
  youtube: Youtube,
  wordpress: Globe,
  medium: BookOpen,
  twitter: Twitter,
  kofi: Rss,
};

export default function Dashboard() {
  const [data, setData] = useState<ParsedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [direction, setDirection] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Конфиг
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [disabledKeys, setDisabledKeys] = useState<Record<string, boolean>>({});
  const [rssSources, setRssSources] = useState<Array<{ url: string; active: boolean }>>([]);
  const [newRss, setNewRss] = useState('');

  const fetchData = async () => {
    setIsRefreshing(true);
    try {
      const res = await fetch('/api/proxy');
      const html = await res.text();
      const parsed = parseDashboardHtml(html);
      setData(parsed);

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
      setTimeout(() => setIsRefreshing(false), 600);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [rssSources.length]);

  const navigate = (newIndex: number) => {
    setDirection(newIndex > currentIndex ? 1 : -1);
    setCurrentIndex(newIndex);
  };

  const handleNext = () => {
    if (currentIndex < SECTIONS.length - 1) navigate(currentIndex + 1);
  };

  const handlePrev = () => {
    if (currentIndex > 0) navigate(currentIndex - 1);
  };

  const toggleSecret = (key: string) => {
    setShowSecrets(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleKeyStatus = (key: string) => {
    setDisabledKeys(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const addRssSource = (e: React.FormEvent) => {
    e.preventDefault();
    if (newRss.trim()) {
      setRssSources([...rssSources, { url: newRss.trim(), active: true }]);
      setNewRss('');
    }
  };

  const toggleRssStatus = (index: number) => {
    const updated = [...rssSources];
    updated[index].active = !updated[index].active;
    setRssSources(updated);
  };

  const removeRssSource = (index: number) => {
    setRssSources(rssSources.filter((_, i) => i !== index));
  };

  const currentSection = SECTIONS[currentIndex];

  const statusMetrics = useMemo(() => {
    if (!data) return { cpu: '-', ram: '-', uptime: '-', pid: '-' };
    return {
      cpu: data.status?.cpu_mem || data.status?.cpu || '-',
      ram: data.status?.memory || data.status?.ram || '-',
      uptime: data.status?.uptime || '-',
      pid: data.status?.pid || '-',
    };
  }, [data]);

  const currentTask = useMemo(() => {
    if (!data) return 'Нет активной задачи';
    const goal = data.goals?.[0];
    return goal?.title || 'Нет активной задачи';
  }, [data]);

  const financeSummary = useMemo(() => {
    const spent = data?.finance?.reduce((acc, f) => acc + Number(f.spend || 0), 0) || 0;
    const earned = 0;
    const total = earned - spent;
    return { spent, earned, total };
  }, [data]);

  const budgetLimit = 3;
  const budgetPct = Math.min(100, (financeSummary.spent / budgetLimit) * 100);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0f172a] flex flex-col items-center justify-center text-emerald-400">
        <Activity className="animate-spin w-16 h-16 mb-4" />
        <p className="text-slate-400 font-medium animate-pulse">Загрузка VITO...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0f172a] flex items-center justify-center text-rose-400 p-6">
        <div className="text-center max-w-md bg-rose-950/20 p-8 rounded-3xl border border-rose-900/50 shadow-2xl">
          <AlertTriangle className="w-16 h-16 mx-auto mb-6" />
          <h2 className="text-2xl font-bold mb-2">Ошибка подключения</h2>
          <p className="text-rose-300/70 mb-6">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-6 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl transition-colors font-semibold"
          >
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  const variants = {
    enter: (direction: number) => ({
      y: direction > 0 ? 20 : -20,
      opacity: 0,
      scale: 0.98
    }),
    center: {
      zIndex: 1,
      y: 0,
      opacity: 1,
      scale: 1
    },
    exit: (direction: number) => ({
      zIndex: 0,
      y: direction < 0 ? 20 : -20,
      opacity: 0,
      scale: 0.98
    })
  };

  const renderContent = () => {
    if (!data) return null;

    switch (currentSection.id) {
      case 'status':
        return (
          <div className="space-y-8">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-slate-800/50 backdrop-blur-sm p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">CPU</div>
                <div className="flex items-center gap-3 text-white">
                  <Cpu size={18} className="text-emerald-400" />
                  <span className="font-mono text-lg">{statusMetrics.cpu}</span>
                </div>
              </div>
              <div className="bg-slate-800/50 backdrop-blur-sm p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">RAM</div>
                <div className="flex items-center gap-3 text-white">
                  <HardDrive size={18} className="text-indigo-400" />
                  <span className="font-mono text-lg">{statusMetrics.ram}</span>
                </div>
              </div>
              <div className="bg-slate-800/50 backdrop-blur-sm p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">Uptime</div>
                <div className="flex items-center gap-3 text-white">
                  <Clock size={18} className="text-amber-400" />
                  <span className="font-mono text-lg">{statusMetrics.uptime}</span>
                </div>
              </div>
              <div className="bg-slate-800/50 backdrop-blur-sm p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">PID</div>
                <div className="flex items-center gap-3 text-white">
                  <Hash size={18} className="text-rose-400" />
                  <span className="font-mono text-lg">{statusMetrics.pid}</span>
                </div>
              </div>
            </div>
            <div className="bg-slate-900/70 border border-slate-700 p-6 rounded-3xl shadow-2xl">
              <div className="flex items-center gap-3 mb-3">
                <ShieldCheck className="text-emerald-400" />
                <h3 className="text-lg font-bold">Текущая задача</h3>
              </div>
              <div className="text-slate-200 font-mono text-sm">{currentTask}</div>
            </div>
          </div>
        );
      case 'agents':
        return (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {data.agents.map((agent, i) => {
              const status = agent.module.includes('error') ? 'error' : agent.module.includes('stop') ? 'idle' : 'active';
              const color = status === 'active' ? 'bg-emerald-500' : status === 'idle' ? 'bg-slate-500' : 'bg-rose-500';
              return (
                <div key={i} className="bg-slate-800/50 backdrop-blur-sm p-5 rounded-2xl border border-slate-700 shadow-xl">
                  <div className="flex items-center gap-3">
                    <span className={`w-2.5 h-2.5 rounded-full ${color}`} />
                    <div className="font-mono text-sm text-emerald-300">{agent.module}</div>
                  </div>
                  <div className="text-xs text-slate-400 mt-2">Последнее изменение: {agent.lastModified}</div>
                </div>
              );
            })}
          </div>
        );
      case 'goals':
        return (
          <div className="bg-slate-800/50 backdrop-blur-sm p-10 rounded-3xl border border-slate-700 shadow-2xl text-center">
            {data.goals.length === 0 ? (
              <div className="flex flex-col items-center gap-4">
                <Target className="w-16 h-16 text-slate-600" />
                <p className="text-slate-400 text-lg">Активных целей пока нет</p>
              </div>
            ) : (
              <pre className="text-left text-sm text-emerald-300/90 overflow-x-auto bg-slate-900/50 p-6 rounded-2xl border border-slate-700">
                {JSON.stringify(data.goals, null, 2)}
              </pre>
            )}
          </div>
        );
      case 'platforms':
        return (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {data.platforms.map((p, i) => {
              const name = p.file.replace('.py', '').toLowerCase();
              const Icon = PLATFORM_ICONS[name] || Layers;
              const connected = !name.includes('not') && !name.includes('disabled');
              return (
                <div key={i} className="bg-slate-800/50 backdrop-blur-sm p-5 rounded-2xl border border-slate-700 flex flex-col items-center justify-center text-center">
                  <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center mb-3">
                    <Icon size={18} className={connected ? 'text-emerald-400' : 'text-slate-400'} />
                  </div>
                  <span className="font-mono text-xs text-slate-200">{p.file}</span>
                  <div className={`text-[10px] mt-2 ${connected ? 'text-emerald-400' : 'text-rose-400'}`}>{connected ? 'Подключено' : 'Не подключено'}</div>
                </div>
              );
            })}
          </div>
        );
      case 'finance':
        return (
          <div className="space-y-8">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <div className="bg-slate-800/50 p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">Потрачено</div>
                <div className="text-rose-400 font-mono text-2xl">${financeSummary.spent.toFixed(4)}</div>
              </div>
              <div className="bg-slate-800/50 p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">Заработано</div>
                <div className="text-emerald-400 font-mono text-2xl">${financeSummary.earned.toFixed(4)}</div>
              </div>
              <div className="bg-slate-800/50 p-6 rounded-3xl border border-slate-700 shadow-xl">
                <div className="text-slate-400 text-xs uppercase tracking-widest font-bold mb-3">Итог</div>
                <div className="text-indigo-400 font-mono text-2xl">${financeSummary.total.toFixed(4)}</div>
              </div>
            </div>
            <div className="bg-slate-900/60 p-6 rounded-3xl border border-slate-700 shadow-2xl">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-3">
                <span>Лимит: ${budgetLimit.toFixed(2)}</span>
                <span>{budgetPct.toFixed(1)}%</span>
              </div>
              <div className="w-full h-3 rounded-full bg-slate-800 overflow-hidden">
                <div className="h-full bg-emerald-500" style={{ width: `${budgetPct}%` }} />
              </div>
            </div>
          </div>
        );
      case 'events':
        return (
          <div className="space-y-3">
            {data.events.map((ev, i) => {
              const isError = ev.includes('ERROR') || ev.includes('CRITICAL');
              const isWarning = ev.includes('WARNING');
              const isSuccess = ev.includes('SUCCESS') || ev.includes('ok') || ev.includes('OK');
              const Icon = isError ? X : isWarning ? AlertTriangle : isSuccess ? Check : Info;
              const bg = isError ? 'bg-rose-950/20 border-rose-900/50 text-rose-200' :
                isWarning ? 'bg-amber-950/20 border-amber-900/50 text-amber-200' :
                isSuccess ? 'bg-emerald-950/20 border-emerald-900/50 text-emerald-200' :
                'bg-slate-800/50 border-slate-700 text-slate-300';
              return (
                <div key={i} className={`p-4 rounded-2xl border ${bg} font-mono text-xs whitespace-pre-wrap break-words`}>
                  <div className="flex items-start gap-3">
                    <Icon size={14} className="mt-0.5 shrink-0" />
                    <span>{ev}</span>
                  </div>
                </div>
              );
            })}
          </div>
        );
      case 'config':
        return (
          <div className="space-y-8">
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-3xl border border-slate-700 overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-slate-700 flex justify-between items-center bg-slate-900/30">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Settings size={20} className="text-indigo-400" />
                  Переменные окружения
                </h3>
                <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Секреты скрыты</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <tbody className="divide-y divide-slate-700/50">
                    {Object.entries(data.config).map(([key, value]) => {
                      const isSecret = value === '***' || key.includes('KEY') || key.includes('SECRET') || key.includes('TOKEN') || key.includes('PASSWORD');
                      const isDisabled = disabledKeys[key];
                      const displayValue = isSecret && !showSecrets[key] ? '••••••••••••••••' : value;

                      return (
                        <tr key={key} className={`transition-colors group ${isDisabled ? 'opacity-40 grayscale' : 'hover:bg-slate-700/30'}`}>
                          <td className="p-5 font-mono text-sm text-emerald-400 w-1/3">{key}</td>
                          <td className="p-5 font-mono text-sm text-slate-400 break-all">
                            {displayValue}
                          </td>
                          <td className="p-5 w-32 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {isSecret && (
                                <button
                                  onClick={() => toggleSecret(key)}
                                  className="text-slate-500 hover:text-white transition-colors p-2 rounded-xl hover:bg-slate-700"
                                  title="Показать/скрыть"
                                >
                                  {showSecrets[key] ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                              )}
                              <button
                                onClick={() => toggleKeyStatus(key)}
                                className={`p-2 rounded-xl transition-all ${isDisabled ? 'text-rose-500 bg-rose-500/10' : 'text-emerald-500 hover:bg-emerald-500/10'}`}
                                title={isDisabled ? "Включить" : "Выключить"}
                              >
                                <Power size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bg-slate-800/50 backdrop-blur-sm rounded-3xl border border-slate-700 overflow-hidden shadow-2xl p-8">
              <h3 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
                <Users size={20} className="text-indigo-400" />
                Источники RSS
              </h3>
              <div className="space-y-4 mb-8">
                {rssSources.map((rss, i) => (
                  <div key={i} className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${
                    rss.active ? 'bg-slate-900/50 border-slate-700' : 'bg-slate-900/20 border-slate-800 opacity-50'
                  }`}>
                    <div className="flex items-center gap-4 truncate mr-4">
                      <button
                        onClick={() => toggleRssStatus(i)}
                        className={`shrink-0 transition-colors ${rss.active ? 'text-emerald-500' : 'text-slate-600'}`}
                      >
                        {rss.active ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
                      </button>
                      <span className="text-sm text-slate-200 truncate">{rss.url}</span>
                    </div>
                    <button
                      onClick={() => removeRssSource(i)}
                      className="text-rose-400 hover:text-white p-2 rounded-xl hover:bg-rose-500/20 transition-all"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                ))}
                {rssSources.length === 0 && (
                  <div className="text-center py-10 border-2 border-dashed border-slate-700 rounded-3xl">
                    <p className="text-slate-500 text-sm italic">Список источников пуст</p>
                  </div>
                )}
              </div>
              <form onSubmit={addRssSource} className="flex flex-col sm:flex-row gap-4">
                <input
                  type="url"
                  value={newRss}
                  onChange={e => setNewRss(e.target.value)}
                  placeholder="Введите URL RSS фида..."
                  className="flex-1 bg-slate-900/50 border border-slate-700 rounded-2xl px-6 py-3 text-white focus:outline-none focus:border-indigo-500 transition-all placeholder:text-slate-600"
                  required
                />
                <button
                  type="submit"
                  className="bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-3 rounded-2xl flex items-center justify-center gap-2 transition-all font-bold shadow-lg shadow-indigo-500/20 active:scale-95"
                >
                  <Plus size={20} /> Добавить
                </button>
              </form>
            </div>
          </div>
        );
      case 'output':
        return (
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-3xl border border-slate-700 overflow-hidden shadow-2xl">
            <div className="overflow-x-auto max-h-[65vh] custom-scrollbar">
              <table className="w-full text-left border-collapse">
                <thead className="sticky top-0 bg-slate-900 z-10 shadow-md">
                  <tr className="border-b border-slate-700">
                    <th className="p-5 text-slate-400 font-bold uppercase text-xs tracking-wider">Файл</th>
                    <th className="p-5 text-slate-400 font-bold uppercase text-xs tracking-wider">Размер</th>
                    <th className="p-5 text-slate-400 font-bold uppercase text-xs tracking-wider">Изменен</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {data.output.map((out, i) => (
                    <tr key={i} className="hover:bg-slate-700/30 transition-colors">
                      <td className="p-5 font-mono text-sm text-indigo-400 break-all">{out.file}</td>
                      <td className="p-5 text-sm text-slate-500">{out.size} B</td>
                      <td className="p-5 text-sm text-slate-300 whitespace-nowrap">{out.modified}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-200 font-sans selection:bg-indigo-500/30">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] bg-indigo-500/10 blur-[120px] rounded-full" />
        <div className="absolute top-[60%] -right-[10%] w-[30%] h-[40%] bg-emerald-500/5 blur-[120px] rounded-full" />
      </div>

      <header className="fixed top-0 left-0 right-0 h-20 bg-slate-900/60 backdrop-blur-xl border-b border-slate-800 z-50 flex items-center justify-between px-8">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-emerald-500 flex items-center justify-center text-white font-black text-2xl shadow-lg shadow-indigo-500/20">
            V
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-white">VITO <span className="text-indigo-400">MEGA</span></h1>
            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Панель управления</p>
          </div>
        </div>

        <div className="hidden lg:flex items-center gap-1 bg-slate-800/50 p-1.5 rounded-2xl border border-slate-700 shadow-inner">
          {SECTIONS.map((sec, idx) => {
            const Icon = sec.icon;
            const isActive = idx === currentIndex;
            return (
              <button
                key={sec.id}
                onClick={() => navigate(idx)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider transition-all duration-300 ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                    : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                }`}
              >
                <Icon size={14} />
                {sec.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={fetchData}
            className={`p-2 rounded-xl border border-slate-700 bg-slate-800/60 text-slate-200 hover:bg-slate-700 transition-all ${isRefreshing ? 'animate-spin' : ''}`}
            title="Обновить"
          >
            <RefreshCw size={18} />
          </button>
          <div className="hidden sm:flex flex-col items-end">
            <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Система</span>
            <span className="text-xs text-emerald-400 font-mono flex items-center gap-1.5">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              ONLINE
            </span>
          </div>
        </div>
      </header>

      <main className="pt-32 pb-32 lg:pb-12 px-6 lg:px-12 max-w-7xl mx-auto relative min-h-screen flex flex-col">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-10 gap-4">
          <h2 className="text-4xl font-black text-white flex items-center gap-4 tracking-tight">
            <div className="p-3 bg-slate-800 rounded-2xl border border-slate-700 shadow-xl">
              {React.createElement(currentSection.icon, { size: 28, className: "text-indigo-400" })}
            </div>
            {currentSection.label}
          </h2>

          <div className="flex items-center gap-4">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-widest bg-slate-800/50 px-4 py-2 rounded-full border border-slate-700">
              {currentIndex + 1} / {SECTIONS.length}
            </div>
          </div>
        </div>

        <div className="relative flex-1">
          <AnimatePresence initial={false} custom={direction} mode="wait">
            <motion.div
              key={currentIndex}
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                y: { type: 'spring', stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 },
                scale: { duration: 0.2 },
              }}
              className="w-full"
            >
              {renderContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      <div className="lg:hidden fixed bottom-6 left-6 right-6 bg-slate-900/80 backdrop-blur-2xl border border-slate-700 z-50 p-3 rounded-3xl shadow-2xl flex justify-between items-center">
        <button
          onClick={handlePrev}
          disabled={currentIndex === 0}
          className="p-4 rounded-2xl bg-slate-800 border border-slate-700 disabled:opacity-30 disabled:cursor-not-allowed text-white active:scale-90 transition-all"
        >
          <ChevronLeft size={24} />
        </button>

        <div className="flex gap-3 overflow-x-auto hide-scrollbar px-4">
          {SECTIONS.map((sec, idx) => {
            const Icon = sec.icon;
            return (
              <button
                key={sec.id}
                onClick={() => navigate(idx)}
                className={`p-4 rounded-2xl flex-shrink-0 transition-all active:scale-90 ${
                  idx === currentIndex
                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                    : 'bg-slate-800 text-slate-500 border border-slate-700'
                }`}
              >
                <Icon size={20} />
              </button>
            );
          })}
        </div>

        <button
          onClick={handleNext}
          disabled={currentIndex === SECTIONS.length - 1}
          className="p-4 rounded-2xl bg-slate-800 border border-slate-700 disabled:opacity-30 disabled:cursor-not-allowed text-white active:scale-90 transition-all"
        >
          <ChevronRight size={24} />
        </button>
      </div>

      <style
        dangerouslySetInnerHTML={{
          __html: `
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #475569; }
      `,
        }}
      />
    </div>
  );
}
