import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  CircularProgress,
  Drawer,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Lan as LanIcon,
  MailOutline as MailOutlineIcon,
  Memory as MemoryIcon,
  Storage as StorageIcon,
  WarningAmber as WarningAmberIcon,
} from '@mui/icons-material';
import MainLayout from '../components/layout/MainLayout';
import { equipmentAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const SEEN_CHANGES_STORAGE_KEY = 'computers_seen_changes_by_pc_v1';
const AUTO_REFRESH_BASE_SEC = 60;
const AUTO_REFRESH_STEP_SEC = 30;
const AUTO_REFRESH_MAX_SEC = 120;

function StatCard({ title, value, helper, color = 'inherit' }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
      <Typography variant="body2" color="text.secondary">{title}</Typography>
      <Typography variant="h4" sx={{ fontWeight: 700, color, lineHeight: 1.2 }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{helper}</Typography>
    </Paper>
  );
}

function MiniBars({ title, rows, color }) {
  const list = Array.isArray(rows) ? rows.slice(0, 8) : [];
  const max = list.reduce((acc, row) => Math.max(acc, Number(row.value) || 0), 0) || 1;

  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.2 }}>{title}</Typography>
      {list.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Нет данных</Typography>
      ) : (
        <Stack spacing={1}>
          {list.map((row) => {
            const value = Number(row.value) || 0;
            const width = Math.max(3, Math.round((value / max) * 100));
            return (
              <Box key={String(row.label)}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.2 }}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>{row.label}</Typography>
                  <Typography variant="caption" color="text.secondary">{value}</Typography>
                </Box>
                <Box sx={{ height: 7, borderRadius: 4, bgcolor: 'action.hover', overflow: 'hidden' }}>
                  <Box sx={{ width: `${width}%`, height: '100%', bgcolor: color }} />
                </Box>
              </Box>
            );
          })}
        </Stack>
      )}
    </Paper>
  );
}

function formatTs(ts) {
  if (!ts) return '-';
  return new Date(Number(ts) * 1000).toLocaleString('ru-RU');
}

function formatAge(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return '-';
  if (value < 60) return `${value}с`;
  const mins = Math.floor(value / 60);
  if (mins < 60) return `${mins}м`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}ч`;
  return `${Math.floor(hours / 24)}д`;
}

function toPercent(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  if (parsed < 0) return 0;
  if (parsed > 100) return 100;
  return parsed;
}

function formatPercent(value) {
  const parsed = toPercent(value);
  if (parsed === null) return '-';
  return `${parsed.toFixed(1)}%`;
}

function resolveRuntimeMetrics(pc) {
  const health = pc?.health && typeof pc.health === 'object' ? pc.health : {};
  const cpu = toPercent(pc?.cpu_load_percent ?? health?.cpu_load_percent);
  const ram = toPercent(pc?.ram_used_percent ?? health?.ram_used_percent);

  const uptimeRaw = Number(pc?.uptime_seconds ?? health?.uptime_seconds);
  const uptimeSeconds = Number.isFinite(uptimeRaw) && uptimeRaw >= 0 ? Math.floor(uptimeRaw) : null;

  const rebootRaw = Number(pc?.last_reboot_at ?? health?.last_reboot_at ?? health?.boot_time);
  const lastRebootAt = Number.isFinite(rebootRaw) && rebootRaw > 0 ? Math.floor(rebootRaw) : null;

  return { cpu, ram, uptimeSeconds, lastRebootAt };
}

function smartHealthColor(status) {
  const normalized = String(status || '').trim().toLowerCase();
  if (!normalized) return 'default';
  if (normalized.includes('healthy') || normalized.includes('ok') || normalized.includes('good')) return 'success';
  if (normalized.includes('warning') || normalized.includes('degrad') || normalized.includes('pred')) return 'warning';
  if (normalized.includes('critical') || normalized.includes('unhealthy') || normalized.includes('fail')) return 'error';
  return 'default';
}

function getStorageHealthStats(pc) {
  const rows = Array.isArray(pc?.storage) ? pc.storage : [];
  let problemCount = 0;
  rows.forEach((disk) => {
    const color = smartHealthColor(disk?.health_status);
    if (color === 'warning' || color === 'error') {
      problemCount += 1;
    }
  });
  return { total: rows.length, problemCount };
}

function statusColor(status) {
  if (status === 'online') return 'success';
  if (status === 'stale') return 'warning';
  if (status === 'offline') return 'error';
  return 'default';
}

function statusLabel(status) {
  if (status === 'online') return 'В сети';
  if (status === 'stale') return 'Нет свежих';
  if (status === 'offline') return 'Оффлайн';
  return 'Неизвестно';
}

function firstIpv4(value) {
  const text = String(value || '');
  const match = text.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/);
  return match ? match[0] : '';
}

function resolvePcIp(pc) {
  const direct = String(pc?.ip_primary || '').trim();
  if (direct) return direct;
  if (Array.isArray(pc?.ip_list) && pc.ip_list.length > 0) {
    const candidate = firstIpv4(pc.ip_list[0]);
    if (candidate) return candidate;
  }
  return firstIpv4(pc?.network_link?.endpoint_ip_raw);
}

function toIntOrNull(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.floor(parsed);
}

function formatDiskSizeFromBytes(value) {
  const sizeBytes = toIntOrNull(value);
  if (!sizeBytes) return '';
  const gib = sizeBytes / (1024 ** 3);
  if (gib >= 1024) return `${(gib / 1024).toFixed(1)} TB`;
  return `${Math.round(gib)} GB`;
}

function resolveDiskSizeLabel(disk) {
  return formatDiskSizeFromBytes(disk?.size_bytes) || formatDiskSizeFromBytes(disk?.extended_info?.Size);
}

function resolveDiskTitle(disk) {
  const title = String(disk?.display_name || disk?.model || disk?.serial_number || 'Unknown').trim();
  if (title) return title;
  return 'Unknown';
}

function formatBytesAsGb(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return 'не определено';
  const gb = bytes / (1024 ** 3);
  if (gb >= 1024) return `${(gb / 1024).toFixed(1)} TB`;
  return `${gb.toFixed(1)} GB`;
}

function formatBytesCompact(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = bytes;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  if (idx === 0) return `${Math.round(size)} ${units[idx]}`;
  return `${size.toFixed(1)} ${units[idx]}`;
}

function outlookStatusColor(status) {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'ok') return 'success';
  if (normalized === 'warning') return 'warning';
  if (normalized === 'critical') return 'error';
  return 'default';
}

function outlookStatusLabel(status) {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'ok') return 'OK';
  if (normalized === 'warning') return 'Warning';
  if (normalized === 'critical') return 'Critical';
  return 'Unknown';
}

function resolveOutlookMeta(pc) {
  const raw = pc?.outlook && typeof pc.outlook === 'object' ? pc.outlook : {};
  const active = raw?.active_store && typeof raw.active_store === 'object' ? raw.active_store : null;
  const activeStoresRaw = Array.isArray(raw?.active_stores) ? raw.active_stores : [];
  const activeStores = activeStoresRaw
    .filter((row) => row && typeof row === 'object' && String(row.path || '').trim())
    .map((row) => row);
  if (active && !activeStores.some((row) => String(row.path || '').trim().toLowerCase() === String(active.path || '').trim().toLowerCase())) {
    activeStores.unshift(active);
  }
  const candidate = raw?.active_candidate && typeof raw.active_candidate === 'object' ? raw.active_candidate : null;
  const archives = Array.isArray(raw?.archives) ? raw.archives : [];
  const activePrimary = activeStores[0] || active || null;
  const activeSizeMax = activeStores.length > 0
    ? Math.max(...activeStores.map((row) => Number(row?.size_bytes || 0)))
    : Number(activePrimary?.size_bytes || 0);
  return {
    status: String(pc?.outlook_status || raw?.status || 'unknown').toLowerCase(),
    confidence: String(pc?.outlook_confidence || raw?.confidence || 'low').toLowerCase(),
    source: String(raw?.source || 'none').toLowerCase(),
    activeSizeBytes: Number(pc?.outlook_active_size_bytes || activeSizeMax || 0),
    activePath: String(pc?.outlook_active_path || activePrimary?.path || '').trim(),
    totalSizeBytes: Number(pc?.outlook_total_size_bytes || raw?.total_outlook_size_bytes || 0),
    archivesCount: Number(pc?.outlook_archives_count || archives.length || 0),
    activeStoresCount: Number(pc?.outlook_active_stores_count || activeStores.length || 0),
    activeStore: activePrimary,
    activeStores,
    activeCandidate: candidate,
    archives,
  };
}

function pcChangeKey(pc) {
  const mac = String(pc?.mac_address || '').replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
  if (mac) return `mac:${mac}`;
  const host = String(pc?.hostname || '').trim().toLowerCase();
  return `host:${host}`;
}

function readSeenChangesMap() {
  try {
    const raw = localStorage.getItem(SEEN_CHANGES_STORAGE_KEY);
    if (!raw) return {};
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') return {};
    return data;
  } catch {
    return {};
  }
}

function summarizeChangeEvent(event) {
  const diff = event?.diff && typeof event.diff === 'object' ? event.diff : {};
  const lines = [];

  if (diff.system && typeof diff.system === 'object') {
    const before = diff.system.before || {};
    const after = diff.system.after || {};
    if ((before.cpu_model || '') !== (after.cpu_model || '')) {
      lines.push(`CPU: "${before.cpu_model || '-'}" -> "${after.cpu_model || '-'}"`);
    }
    if (Number(before.ram_gb || 0) !== Number(after.ram_gb || 0)) {
      lines.push(`RAM: ${before.ram_gb || '-'} -> ${after.ram_gb || '-'}`);
    }
    if ((before.system_serial || '') !== (after.system_serial || '')) {
      lines.push(`S/N BIOS: "${before.system_serial || '-'}" -> "${after.system_serial || '-'}"`);
    }
  }

  const summarizeSet = (name, beforeRaw, afterRaw) => {
    const before = Array.isArray(beforeRaw) ? beforeRaw : [];
    const after = Array.isArray(afterRaw) ? afterRaw : [];
    const added = after.filter((item) => !before.includes(item));
    const removed = before.filter((item) => !after.includes(item));
    if (added.length === 0 && removed.length === 0) {
      if (before.length !== after.length) {
        lines.push(`${name}: ${before.length} -> ${after.length}`);
      }
      return;
    }
    if (added.length > 0) lines.push(`${name}: добавлено ${added.length}`);
    if (removed.length > 0) lines.push(`${name}: убрано ${removed.length}`);
  };

  if (diff.monitors && typeof diff.monitors === 'object') {
    summarizeSet('Мониторы', diff.monitors.before, diff.monitors.after);
  }
  if (diff.storage && typeof diff.storage === 'object') {
    summarizeSet('Накопители', diff.storage.before, diff.storage.after);
  }

  if (lines.length === 0) {
    const types = Array.isArray(event?.change_types) ? event.change_types.join(', ') : '-';
    return [`Изменения: ${types}`];
  }
  return lines;
}

function Computers() {
  const { hasPermission } = useAuth();
  const canViewAllComputers = hasPermission('computers.read_all');

  const [computers, setComputers] = useState([]);
  const [changes, setChanges] = useState({ totals: {}, daily: [] });
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(false);

  const [q, setQ] = useState('');
  const [status, setStatus] = useState('all');
  const [outlookStatus, setOutlookStatus] = useState('all');
  const [branch, setBranch] = useState('all');
  const [changedOnly, setChangedOnly] = useState(false);
  const [showAllComputers, setShowAllComputers] = useState(false);
  const [showDashboard, setShowDashboard] = useState(() => localStorage.getItem('computers_show_dashboard') !== '0');
  const [showLocation, setShowLocation] = useState(() => localStorage.getItem('computers_show_location') !== '0');
  const [expandedLocations, setExpandedLocations] = useState({});
  const [seenChangesByPc, setSeenChangesByPc] = useState(() => readSeenChangesMap());

  const inFlightRef = useRef(false);
  const pollTimerRef = useRef(null);
  const retryDelaySecRef = useRef(AUTO_REFRESH_BASE_SEC);

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const load = useCallback(async ({ withLoader = false } = {}) => {
    if (inFlightRef.current) return false;
    inFlightRef.current = true;
    try {
      if (withLoader) setLoading(true);
      const scope = canViewAllComputers && showAllComputers ? 'all' : 'selected';
      const [pcData, changeData] = await Promise.all([
        equipmentAPI.getAgentComputers({ scope }),
        equipmentAPI.getAgentComputerChanges(50),
      ]);
      setComputers(Array.isArray(pcData) ? pcData : []);
      setChanges(changeData && typeof changeData === 'object' ? changeData : { totals: {}, daily: [] });
      retryDelaySecRef.current = AUTO_REFRESH_BASE_SEC;
      return true;
    } catch (err) {
      console.error('Computers load failed', err);
      retryDelaySecRef.current = Math.min(retryDelaySecRef.current + AUTO_REFRESH_STEP_SEC, AUTO_REFRESH_MAX_SEC);
      return false;
    } finally {
      if (withLoader) setLoading(false);
      inFlightRef.current = false;
    }
  }, [canViewAllComputers, showAllComputers]);

  const scheduleNextPoll = useCallback((delaySec) => {
    clearPollTimer();
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
    const nextDelaySec = Number.isFinite(Number(delaySec)) ? Number(delaySec) : retryDelaySecRef.current;
    pollTimerRef.current = setTimeout(async () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        clearPollTimer();
        return;
      }
      await load({ withLoader: false });
      scheduleNextPoll(retryDelaySecRef.current);
    }, Math.max(1, nextDelaySec) * 1000);
  }, [clearPollTimer, load]);

  const handleManualRefresh = useCallback(async () => {
    await load({ withLoader: true });
    scheduleNextPoll(retryDelaySecRef.current);
  }, [load, scheduleNextPoll]);

  useEffect(() => {
    let isActive = true;
    const init = async () => {
      await load({ withLoader: true });
      if (!isActive) return;
      scheduleNextPoll(AUTO_REFRESH_BASE_SEC);
    };
    init();
    return () => {
      isActive = false;
      clearPollTimer();
    };
  }, [clearPollTimer, load, scheduleNextPoll]);

  useEffect(() => {
    const handleVisibilityChange = async () => {
      if (document.visibilityState !== 'visible') {
        clearPollTimer();
        return;
      }
      await load({ withLoader: false });
      scheduleNextPoll(retryDelaySecRef.current);
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [clearPollTimer, load, scheduleNextPoll]);

  useEffect(() => {
    const reloadAfterDbSwitch = async () => {
      // If auto-refresh request is in-flight, wait briefly and then reload for the new DB.
      let guard = 0;
      while (inFlightRef.current && guard < 30) {
        // eslint-disable-next-line no-await-in-loop
        await new Promise((resolve) => setTimeout(resolve, 150));
        guard += 1;
      }
      setSelected(null);
      setOpen(false);
      await load({ withLoader: true });
      scheduleNextPoll(AUTO_REFRESH_BASE_SEC);
    };

    const handleDatabaseChanged = async () => {
      await reloadAfterDbSwitch();
    };

    const handleStorage = async (event) => {
      if (event.key !== 'selected_database') return;
      await reloadAfterDbSwitch();
    };

    window.addEventListener('database-changed', handleDatabaseChanged);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener('database-changed', handleDatabaseChanged);
      window.removeEventListener('storage', handleStorage);
    };
  }, [load, scheduleNextPoll]);

  useEffect(() => {
    localStorage.setItem('computers_show_dashboard', showDashboard ? '1' : '0');
  }, [showDashboard]);

  useEffect(() => {
    localStorage.setItem('computers_show_location', showLocation ? '1' : '0');
  }, [showLocation]);

  useEffect(() => {
    if (canViewAllComputers) return;
    setShowAllComputers(false);
  }, [canViewAllComputers]);

  useEffect(() => {
    localStorage.setItem(SEEN_CHANGES_STORAGE_KEY, JSON.stringify(seenChangesByPc));
  }, [seenChangesByPc]);

  const hasUnseenChanges = (pc) => {
    const lastTs = Number(pc?.last_change_at || 0);
    if (!lastTs) return false;
    const seenTs = Number(seenChangesByPc?.[pcChangeKey(pc)] || 0);
    return lastTs > seenTs;
  };

  const markPcChangesSeen = (pc) => {
    const ts = Number(pc?.last_change_at || 0);
    if (!ts) return;
    const key = pcChangeKey(pc);
    setSeenChangesByPc((prev) => {
      const current = Number(prev?.[key] || 0);
      if (current >= ts) return prev;
      return { ...(prev || {}), [key]: ts };
    });
  };

  const markAllChangesSeen = () => {
    const next = { ...(seenChangesByPc || {}) };
    computers.forEach((pc) => {
      const ts = Number(pc?.last_change_at || 0);
      if (!pc?.has_hardware_changes || !ts) return;
      next[pcChangeKey(pc)] = Math.max(Number(next[pcChangeKey(pc)] || 0), ts);
    });
    setSeenChangesByPc(next);
  };

  const branches = useMemo(() => {
    const uniq = new Set(computers.map((pc) => String(pc.branch_name || 'Без филиала').trim() || 'Без филиала'));
    return Array.from(uniq).sort((a, b) => a.localeCompare(b, 'ru'));
  }, [computers]);

  const filtered = useMemo(() => {
    const needle = String(q || '').trim().toLowerCase();
    return computers.filter((pc) => {
      const pcBranch = String(pc.branch_name || 'Без филиала').trim() || 'Без филиала';
      if (status !== 'all' && String(pc.status || '').toLowerCase() !== status) return false;
      if (outlookStatus !== 'all' && String(pc.outlook_status || 'unknown').toLowerCase() !== outlookStatus) return false;
      if (branch !== 'all' && pcBranch !== branch) return false;
      if (changedOnly && !pc.has_hardware_changes) return false;
      if (!needle) return true;

      const net = pc.network_link || {};
      const text = [
        pc.hostname,
        pc.user_full_name,
        pc.user_login,
        pc.current_user,
        resolvePcIp(pc),
        pc.mac_address,
        pc.branch_name,
        pc.location_name,
        pc.database_name,
        pc.database_id,
        pc.outlook_active_path,
        pc.outlook_status,
        net.device_code,
        net.port_name,
        net.socket_code,
      ].map((v) => String(v || '').toLowerCase()).join(' ');

      return text.includes(needle);
    });
  }, [branch, changedOnly, computers, outlookStatus, q, status]);

  const grouped = useMemo(() => {
    const branchBuckets = {};
    filtered.forEach((pc) => {
      const branchName = String(pc.branch_name || 'Без филиала').trim() || 'Без филиала';
      const locationName = showLocation
        ? (String(pc.location_name || pc.network_link?.site_name || 'Без местоположения').trim() || 'Без местоположения')
        : 'Все компьютеры';

      if (!branchBuckets[branchName]) {
        branchBuckets[branchName] = { branchName, locations: {} };
      }
      if (!branchBuckets[branchName].locations[locationName]) {
        branchBuckets[branchName].locations[locationName] = { locationName, items: [] };
      }
      branchBuckets[branchName].locations[locationName].items.push(pc);
    });

    return Object.values(branchBuckets)
      .sort((a, b) => a.branchName.localeCompare(b.branchName, 'ru'))
      .map((branchGroup) => ({
        ...branchGroup,
        locations: Object.values(branchGroup.locations).sort((a, b) => a.locationName.localeCompare(b.locationName, 'ru')),
      }));
  }, [filtered, showLocation]);

  const statusRows = useMemo(() => {
    const map = { online: 0, stale: 0, offline: 0, unknown: 0 };
    filtered.forEach((pc) => {
      const key = String(pc.status || 'unknown').toLowerCase();
      map[key] = (map[key] || 0) + 1;
    });
    return [
      { label: 'В сети', value: map.online || 0 },
      { label: 'Нет свежих', value: map.stale || 0 },
      { label: 'Оффлайн', value: map.offline || 0 },
      { label: 'Неизвестно', value: map.unknown || 0 },
    ];
  }, [filtered]);

  const branchRows = useMemo(() => {
    const counters = {};
    filtered.forEach((pc) => {
      const name = String(pc.branch_name || 'Без филиала').trim() || 'Без филиала';
      counters[name] = (counters[name] || 0) + 1;
    });
    return Object.entries(counters)
      .sort((a, b) => a[0].localeCompare(b[0], 'ru'))
      .map(([label, value]) => ({ label, value }));
  }, [filtered]);

  const changeRows = useMemo(() => {
    const daily = Array.isArray(changes.daily) ? changes.daily : [];
    return daily.map((row) => ({ label: String(row.date || '').slice(5), value: Number(row.count || 0) }));
  }, [changes.daily]);

  const totals = changes.totals || {};
  const unseenChangedPcs = useMemo(() => {
    return computers.filter((pc) => {
      if (!pc?.has_hardware_changes) return false;
      return hasUnseenChanges(pc);
    });
  }, [computers, seenChangesByPc]);
  const selectedRuntime = useMemo(() => resolveRuntimeMetrics(selected), [selected]);
  const selectedStorageStats = useMemo(() => getStorageHealthStats(selected), [selected]);
  const selectedOutlook = useMemo(() => resolveOutlookMeta(selected), [selected]);
  const toggleLocationGroup = useCallback((branchName, locationName) => {
    const key = `${branchName}__${locationName}`;
    setExpandedLocations((prev) => ({ ...(prev || {}), [key]: !Boolean(prev?.[key]) }));
  }, []);

  return (
    <MainLayout title="Компьютеры (Агенты)">
      <Box sx={{ width: '100%', pb: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Дашборд компьютеров</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {canViewAllComputers && (
              <FormControlLabel
                sx={{ m: 0 }}
                control={<Switch checked={showAllComputers} onChange={(e) => setShowAllComputers(e.target.checked)} />}
                label={showAllComputers ? 'Все БД' : 'Текущая БД'}
              />
            )}
            <FormControlLabel
              sx={{ m: 0 }}
              control={<Switch checked={showLocation} onChange={(e) => setShowLocation(e.target.checked)} />}
              label={showLocation ? 'Скрыть местоположение' : 'Показать местоположение'}
            />
            <FormControlLabel
              sx={{ m: 0 }}
              control={<Switch checked={showDashboard} onChange={(e) => setShowDashboard(e.target.checked)} />}
              label={showDashboard ? 'Скрыть дашборд' : 'Показать дашборд'}
            />
            <Tooltip title="Обновить данные">
              <span>
                <IconButton onClick={handleManualRefresh} disabled={loading} color="primary">
                  <RefreshIcon />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
        </Box>

        {!loading && unseenChangedPcs.length > 0 && (
          <Alert severity="warning" icon={<WarningAmberIcon fontSize="inherit" />} sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.8 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Новые изменения оборудования на ПК: {unseenChangedPcs.length}
              </Typography>
              <Typography variant="body2">
                {unseenChangedPcs.slice(0, 8).map((pc) => pc.hostname || 'Неизвестный ПК').join(', ')}
                {unseenChangedPcs.length > 8 ? ` и еще ${unseenChangedPcs.length - 8}` : ''}
              </Typography>
              <Box>
                <Button size="small" variant="outlined" color="warning" onClick={markAllChangesSeen}>
                  Отметить все как просмотренные
                </Button>
              </Box>
              <Typography variant="caption" color="text.secondary">
                24ч: {Number(totals.changed_24h || 0)} · 7д: {Number(totals.changed_7d || 0)} · 30д: {Number(totals.changed_30d || 0)}
              </Typography>
            </Box>
          </Alert>
        )}

        {showDashboard && (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard title="Всего ПК" value={filtered.length} helper="по текущим фильтрам" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard title="В сети" value={statusRows[0]?.value || 0} helper="heartbeat до 12 минут" color="success.main" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard title="Оффлайн" value={statusRows[2]?.value || 0} helper="более 60 минут" color="error.main" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard title="С изменениями" value={Number(totals.changed_30d || 0)} helper="уникальные ПК за 30 дней" color="warning.main" />
              </Grid>
            </Grid>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}><MiniBars title="Статусы" rows={statusRows} color="#2e7d32" /></Grid>
              <Grid item xs={12} md={4}><MiniBars title="Филиалы" rows={branchRows} color="#1565c0" /></Grid>
              <Grid item xs={12} md={4}><MiniBars title="Изменения по дням" rows={changeRows} color="#ed6c02" /></Grid>
            </Grid>
          </>
        )}

        <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <TextField
                size="small"
                fullWidth
                label="Поиск"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="ПК, ФИО, логин, IP, MAC"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Статус</InputLabel>
                <Select value={status} label="Статус" onChange={(e) => setStatus(e.target.value)}>
                  <MenuItem value="all">Все</MenuItem>
                  <MenuItem value="online">В сети</MenuItem>
                  <MenuItem value="stale">Нет свежих</MenuItem>
                  <MenuItem value="offline">Оффлайн</MenuItem>
                  <MenuItem value="unknown">Неизвестно</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Outlook</InputLabel>
                <Select value={outlookStatus} label="Outlook" onChange={(e) => setOutlookStatus(e.target.value)}>
                  <MenuItem value="all">All</MenuItem>
                  <MenuItem value="ok">OK</MenuItem>
                  <MenuItem value="warning">Warning</MenuItem>
                  <MenuItem value="critical">Critical</MenuItem>
                  <MenuItem value="unknown">Unknown</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Филиал</InputLabel>
                <Select value={branch} label="Филиал" onChange={(e) => setBranch(e.target.value)}>
                  <MenuItem value="all">Все</MenuItem>
                  {branches.map((branchName) => (
                    <MenuItem key={branchName} value={branchName}>{branchName}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={1}>
              <FormControlLabel
                control={<Switch checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />}
                label="Изменения"
              />
            </Grid>
          </Grid>
        </Paper>

        {loading ? (
          <Box sx={{ py: 8, display: 'flex', justifyContent: 'center' }}><CircularProgress /></Box>
        ) : grouped.length === 0 ? (
          <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}><Typography color="text.secondary">Нет данных по выбранным фильтрам.</Typography></Paper>
        ) : (
          <Stack spacing={1.5}>
            {grouped.map((branchGroup) => (
              <Paper key={branchGroup.branchName} variant="outlined" sx={{ p: 1.2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{branchGroup.branchName}</Typography>
                  <Chip
                    size="small"
                    label={`${branchGroup.locations.reduce((acc, location) => acc + location.items.length, 0)} ПК`}
                  />
                </Box>

                <Stack spacing={1}>
                  {branchGroup.locations.map((locationGroup) => {
                    const locationKey = `${branchGroup.branchName}__${locationGroup.locationName}`;
                    const isExpanded = Boolean(expandedLocations[locationKey]);
                    return (
                      <Paper key={locationKey} variant="outlined" sx={{ p: 1 }}>
                        <Box
                          onClick={() => toggleLocationGroup(branchGroup.branchName, locationGroup.locationName)}
                          sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            cursor: 'pointer',
                            userSelect: 'none',
                          }}
                        >
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {locationGroup.locationName}
                          </Typography>
                          <Chip size="small" label={isExpanded ? `Скрыть (${locationGroup.items.length})` : `Показать (${locationGroup.items.length})`} />
                        </Box>

                        <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                          <Grid container spacing={1.2} sx={{ mt: 0.5 }}>
                            {locationGroup.items.map((pc, idx) => {
                              const net = pc.network_link || {};
                              const runtime = resolveRuntimeMetrics(pc);
                              const storageStats = getStorageHealthStats(pc);
                              const outlookMeta = resolveOutlookMeta(pc);
                              return (
                                <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={`${pc.mac_address || pc.hostname || idx}`}>
                                  <Paper
                                    variant="outlined"
                                    onClick={() => { markPcChangesSeen(pc); setSelected(pc); setOpen(true); }}
                                    sx={{ p: 1.1, height: '100%', cursor: 'pointer', '&:hover': { borderColor: 'primary.main', boxShadow: 2 } }}
                                  >
                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.7 }}>
                                      <Typography variant="subtitle2" sx={{ fontWeight: 700, pr: 1 }}>{pc.hostname || 'Неизвестный ПК'}</Typography>
                                      <Chip size="small" color={statusColor(pc.status)} label={statusLabel(pc.status)} />
                                    </Box>

                                    <Typography variant="caption" sx={{ fontWeight: 600, display: 'block' }}>{pc.user_full_name || 'ФИО не определено'}</Typography>
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.7 }}>{pc.user_login || pc.current_user || '-'}</Typography>

                                    <Typography variant="caption" sx={{ display: 'block' }}>IP: <b>{resolvePcIp(pc) || '-'}</b></Typography>
                                    <Typography variant="caption" sx={{ display: 'block' }}>MAC: <b>{pc.mac_address || '-'}</b></Typography>
                                    <Typography variant="caption" sx={{ display: 'block' }}>БД: <b>{pc.database_name || pc.database_id || '-'}</b></Typography>
                                    <Typography variant="caption" sx={{ display: 'block', mb: 0.7 }}>Возраст: <b>{formatAge(pc.age_seconds)}</b></Typography>

                                    <Box sx={{ mb: 0.8 }}>
                                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, mb: 0.3 }}>
                                        <MemoryIcon fontSize="small" color="action" />
                                        <Typography variant="caption" color="text.secondary">
                                          CPU: {formatPercent(runtime.cpu)} · RAM: {formatPercent(runtime.ram)}
                                        </Typography>
                                      </Box>
                                      {runtime.cpu !== null && (
                                        <LinearProgress
                                          variant="determinate"
                                          value={runtime.cpu}
                                          sx={{ height: 5, borderRadius: 3, mb: 0.4 }}
                                        />
                                      )}
                                      {runtime.ram !== null && (
                                        <LinearProgress
                                          variant="determinate"
                                          value={runtime.ram}
                                          color="secondary"
                                          sx={{ height: 5, borderRadius: 3 }}
                                        />
                                      )}
                                    </Box>

                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, mb: 0.7 }}>
                                      <LanIcon fontSize="small" color="action" />
                                      <Typography variant="caption" color="text.secondary">
                                        {net.device_code ? `${net.device_code} / ${net.port_name || 'порт ?'} / ${net.socket_code || 'розетка ?'}` : 'Сетевое подключение не определено'}
                                      </Typography>
                                    </Box>
                                    {storageStats.total > 0 && (
                                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, mb: 0.7 }}>
                                        <StorageIcon fontSize="small" color="action" />
                                        <Typography variant="caption" color="text.secondary">
                                          SMART: дисков {storageStats.total}, проблемных {storageStats.problemCount}
                                        </Typography>
                                      </Box>
                                    )}
                                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 0.8, mb: 0.7 }}>
                                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, minWidth: 0 }}>
                                        <MailOutlineIcon fontSize="small" color="action" />
                                        <Typography variant="caption" color="text.secondary" noWrap>
                                          {outlookMeta.activeStoresCount > 1
                                            ? `Outlook: активных ${outlookMeta.activeStoresCount}`
                                            : `Outlook: ${formatBytesAsGb(outlookMeta.activeSizeBytes)}`}
                                        </Typography>
                                      </Box>
                                      <Chip size="small" color={outlookStatusColor(outlookMeta.status)} label={outlookStatusLabel(outlookMeta.status)} />
                                    </Box>

                                    {pc.has_hardware_changes && (
                                      <Chip
                                        size="small"
                                        color={hasUnseenChanges(pc) ? 'warning' : 'default'}
                                        label={`Изменения: ${pc.changes_count_30d || 0}`}
                                      />
                                    )}
                                  </Paper>
                                </Grid>
                              );
                            })}
                          </Grid>
                        </Collapse>
                      </Paper>
                    );
                  })}
                </Stack>
              </Paper>
            ))}
          </Stack>
        )}

        <Drawer anchor="right" open={open} onClose={() => setOpen(false)}>
          <Box sx={{ width: { xs: 360, sm: 520 }, p: 3 }}>
            {!selected ? null : (
              <>
                <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>{selected.hostname || 'Неизвестный ПК'}</Typography>
                <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
                  <Chip size="small" color={statusColor(selected.status)} label={statusLabel(selected.status)} />
                  {selected.has_hardware_changes && hasUnseenChanges(selected) && <Chip size="small" color="warning" label="Есть изменения" />}
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Last seen: {formatTs(selected.last_seen_at || selected.timestamp)} · Возраст: {formatAge(selected.age_seconds)}
                </Typography>

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Пользователь и сеть</Typography>
                <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
                  <Typography variant="body2">ФИО: {selected.user_full_name || '-'}</Typography>
                  <Typography variant="body2">Логин: {selected.user_login || selected.current_user || '-'}</Typography>
                  <Typography variant="body2">IP: {resolvePcIp(selected) || '-'}</Typography>
                  <Typography variant="body2">MAC: {selected.mac_address || '-'}</Typography>
                  <Typography variant="body2">Филиал: {selected.branch_name || '-'}</Typography>
                  <Typography variant="body2">Местоположение: {selected.location_name || selected.network_link?.site_name || '-'}</Typography>
                  <Typography variant="body2">База: {selected.database_name || selected.database_id || '-'}</Typography>
                  <Typography variant="body2">Подключение: {selected.network_link?.device_code ? `${selected.network_link.device_code} / ${selected.network_link.port_name || 'порт ?'} / ${selected.network_link.socket_code || 'розетка ?'}` : 'не определено'}</Typography>
                </Paper>

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Система</Typography>
                <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
                  <Typography variant="body2">CPU: {selected.cpu_model || '-'}</Typography>
                  <Typography variant="body2">RAM: {selected.ram_gb ? `${selected.ram_gb} GB` : '-'}</Typography>
                  <Typography variant="body2">Серийный номер BIOS: {selected.system_serial || '-'}</Typography>
                  <Typography variant="body2">Последняя перезагрузка: {selectedRuntime.lastRebootAt ? formatTs(selectedRuntime.lastRebootAt) : '-'}</Typography>
                  <Typography variant="body2">Uptime: {selectedRuntime.uptimeSeconds !== null ? formatAge(selectedRuntime.uptimeSeconds) : '-'}</Typography>
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.3 }}>
                      Загрузка CPU: {formatPercent(selectedRuntime.cpu)}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={selectedRuntime.cpu ?? 0}
                      sx={{ height: 6, borderRadius: 3, mb: 0.8 }}
                    />
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.3 }}>
                      Загрузка RAM: {formatPercent(selectedRuntime.ram)}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={selectedRuntime.ram ?? 0}
                      color="secondary"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                </Paper>

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Outlook</Typography>
                <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Chip size="small" color={outlookStatusColor(selectedOutlook.status)} label={outlookStatusLabel(selectedOutlook.status)} />
                    <Typography variant="caption" color="text.secondary">
                      confidence: {selectedOutlook.confidence || 'low'} · source: {selectedOutlook.source || 'none'}
                    </Typography>
                  </Box>
                  {selectedOutlook.activeStores.length > 0 ? (
                    <Box sx={{ mb: 1.2 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.3 }}>
                        Active stores ({selectedOutlook.activeStoresCount || selectedOutlook.activeStores.length})
                      </Typography>
                      <Stack spacing={0.6}>
                        {selectedOutlook.activeStores.map((store, idx) => (
                          <Paper key={`${store.path || 'active'}-${idx}`} variant="outlined" sx={{ p: 0.8 }}>
                            <Tooltip title={store.path || '-'}>
                              <Typography variant="caption" sx={{ display: 'block' }} noWrap>
                                {store.path || '-'}
                              </Typography>
                            </Tooltip>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                              {String(store.type || '-').toUpperCase()} · {formatBytesCompact(store.size_bytes)} · {store.last_modified_at ? formatTs(store.last_modified_at) : '-'}
                            </Typography>
                          </Paper>
                        ))}
                      </Stack>
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Active store: Не определено
                    </Typography>
                  )}
                  {selectedOutlook.activeStores.length === 0 && selectedOutlook.activeCandidate?.path && (
                    <Box sx={{ mb: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        Кандидат (низкая уверенность):
                      </Typography>
                      <Tooltip title={selectedOutlook.activeCandidate.path}>
                        <Typography variant="caption" sx={{ display: 'block' }} noWrap>
                          {selectedOutlook.activeCandidate.path}
                        </Typography>
                      </Tooltip>
                    </Box>
                  )}
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.8 }}>
                    Всего: {formatBytesCompact(selectedOutlook.totalSizeBytes)} · Активных: {selectedOutlook.activeStoresCount || selectedOutlook.activeStores.length} · Архивов: {selectedOutlook.archivesCount}
                  </Typography>
                  {selectedOutlook.archives.length > 0 ? (
                    <Stack spacing={0.6}>
                      {selectedOutlook.archives.map((archive, idx) => (
                        <Paper key={`${archive.path || 'archive'}-${idx}`} variant="outlined" sx={{ p: 0.8 }}>
                          <Tooltip title={archive.path || '-'}>
                            <Typography variant="caption" sx={{ display: 'block' }} noWrap>
                              {archive.path || '-'}
                            </Typography>
                          </Tooltip>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            {String(archive.type || '-').toUpperCase()} · {formatBytesCompact(archive.size_bytes)} · {archive.last_modified_at ? formatTs(archive.last_modified_at) : '-'}
                          </Typography>
                        </Paper>
                      ))}
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Архивы не обнаружены.</Typography>
                  )}
                </Paper>

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Мониторы</Typography>
                {Array.isArray(selected.monitors) && selected.monitors.length > 0 ? (
                  selected.monitors.map((mon, i) => (
                    <Paper key={i} variant="outlined" sx={{ p: 1.2, mb: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{mon.manufacturer || 'Unknown'} {mon.product_code || ''}</Typography>
                      <Typography variant="caption" color="text.secondary">S/N: {mon.serial_number || '-'} {mon.serial_source ? `(${mon.serial_source})` : ''}</Typography>
                    </Paper>
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Мониторы не обнаружены.</Typography>
                )}

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Логические диски</Typography>
                {Array.isArray(selected.logical_disks) && selected.logical_disks.length > 0 ? (
                  selected.logical_disks.map((disk, i) => (
                    <Box key={i} sx={{ mb: 1.3 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.2 }}>
                        <Typography variant="caption" sx={{ fontWeight: 600 }}>{disk.mountpoint || '-'} ({disk.fstype || '-'})</Typography>
                        <Typography variant="caption" color="text.secondary">{disk.free_gb} / {disk.total_gb} ГБ</Typography>
                      </Box>
                      <LinearProgress variant="determinate" value={Number(disk.percent || 0)} sx={{ height: 7, borderRadius: 3 }} />
                    </Box>
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Диски не обнаружены.</Typography>
                )}

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Физические диски (SMART)</Typography>
                {Array.isArray(selected.storage) && selected.storage.length > 0 ? (
                  <Stack spacing={1} sx={{ mb: 1.5 }}>
                    {selected.storage.map((disk, i) => {
                      const healthStatus = String(disk?.health_status || 'Unknown');
                      const wearRaw = Number(disk?.wear_out_percentage);
                      const tempRaw = Number(disk?.temperature);
                      const diskTitle = resolveDiskTitle(disk);
                      const sizeLabel = resolveDiskSizeLabel(disk) || '-';
                      return (
                        <Paper key={`${disk.serial_number || disk.display_name || disk.model || 'disk'}-${i}`} variant="outlined" sx={{ p: 1.2 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, mb: 0.6 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {diskTitle}
                            </Typography>
                            <Chip size="small" color={smartHealthColor(healthStatus)} label={healthStatus} />
                          </Box>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            S/N: {disk.serial_number || '-'} · Media: {disk.media_type || '-'} · Bus: {disk.bus_type || '-'} · Size: {sizeLabel}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            Износ: {Number.isFinite(wearRaw) ? `${wearRaw}%` : '-'} · Температура: {Number.isFinite(tempRaw) ? `${tempRaw}C` : '-'}
                          </Typography>
                        </Paper>
                      );
                    })}
                    <Typography variant="caption" color="text.secondary">
                      Дисков: {selectedStorageStats.total} · Проблемных: {selectedStorageStats.problemCount}
                    </Typography>
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    SMART/физические диски не обнаружены.
                  </Typography>
                )}

                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1, mt: 1.5 }}>Последние изменения оборудования</Typography>
                {Array.isArray(selected.recent_changes) && selected.recent_changes.length > 0 ? (
                  selected.recent_changes.map((event, idx) => (
                    <Paper key={event.event_id || idx} variant="outlined" sx={{ p: 1.2, mb: 1 }}>
                      <Typography variant="caption" sx={{ display: 'block', fontWeight: 700, mb: 0.4 }}>
                        {formatTs(event.detected_at)}
                      </Typography>
                      <Stack spacing={0.3}>
                        {summarizeChangeEvent(event).map((line, lineIdx) => (
                          <Typography key={`${event.event_id || idx}-${lineIdx}`} variant="caption" color="text.secondary">
                            {line}
                          </Typography>
                        ))}
                      </Stack>
                    </Paper>
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary">Подробных изменений за период нет.</Typography>
                )}
              </>
            )}
          </Box>
        </Drawer>
      </Box>
    </MainLayout>
  );
}

export default Computers;
