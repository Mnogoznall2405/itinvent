import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  PlayArrow as PlayArrowIcon,
  Refresh as RefreshIcon,
  WarningAmber as WarningAmberIcon,
} from '@mui/icons-material';
import MainLayout from '../components/layout/MainLayout';
import { equipmentAPI, scanAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

function StatCard({ title, value, helper, color = 'inherit' }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
      <Typography variant="body2" color="text.secondary">{title}</Typography>
      <Typography variant="h4" sx={{ fontWeight: 700, color, lineHeight: 1.2 }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{helper}</Typography>
    </Paper>
  );
}

function MiniBars({ title, rows, color = '#1565c0' }) {
  const list = Array.isArray(rows) ? rows.slice(0, 8) : [];
  const max = list.reduce((acc, item) => Math.max(acc, Number(item.count || item.value || 0)), 0) || 1;

  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.2 }}>{title}</Typography>
      {list.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Нет данных</Typography>
      ) : (
        <Stack spacing={0.9}>
          {list.map((row, idx) => {
            const label = String(row.label || row.branch || row.severity || '-');
            const value = Number(row.value || row.count || 0);
            const width = Math.max(4, Math.round((value / max) * 100));
            return (
              <Box key={`${label}-${idx}`}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.2 }}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>{label}</Typography>
                  <Typography variant="caption" color="text.secondary">{value}</Typography>
                </Box>
                <Box sx={{ height: 7, bgcolor: 'action.hover', borderRadius: 3, overflow: 'hidden' }}>
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

function DailyBars({ rows }) {
  const list = Array.isArray(rows) ? rows.slice(-14) : [];
  const max = list.reduce((acc, item) => Math.max(acc, Number(item.count || 0)), 0) || 1;

  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.2 }}>Динамика за 14 дней</Typography>
      {list.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Нет данных</Typography>
      ) : (
        <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.6, height: 132 }}>
          {list.map((row) => {
            const value = Number(row.count || 0);
            const h = Math.max(3, Math.round((value / max) * 100));
            return (
              <Box key={String(row.date)} sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <Box
                  title={`${row.date}: ${value}`}
                  sx={{
                    width: '100%',
                    height: `${h}%`,
                    minHeight: 3,
                    borderRadius: 1,
                    bgcolor: value > 0 ? 'warning.main' : 'action.hover',
                  }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.3, fontSize: '0.62rem' }}>
                  {String(row.date || '').slice(5)}
                </Typography>
              </Box>
            );
          })}
        </Box>
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
  const minutes = Math.floor(value / 60);
  if (minutes < 60) return `${minutes}м`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}ч`;
  return `${Math.floor(hours / 24)}д`;
}

function formatLastSeen(seconds, isOnline) {
  const age = formatAge(seconds);
  if (age === '-') return 'последний контакт: -';
  if (isOnline) return `в сети, обновлено ${age} назад`;
  return `не в сети ${age}`;
}

function normalizeHost(value) {
  return String(value || '').trim().toLowerCase();
}

function firstIpv4(value) {
  const text = String(value || '');
  const match = text.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/);
  return match ? match[0] : '';
}

function inferFileExt(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  const normalized = text.replace(/\\/g, '/');
  const name = normalized.split('/').pop() || '';
  const idx = name.lastIndexOf('.');
  if (idx < 0 || idx === name.length - 1) return '';
  return name.slice(idx + 1).toLowerCase();
}

function getIncidentFileExt(incident) {
  return String(
    incident?.file_ext
    || inferFileExt(incident?.file_name)
    || inferFileExt(incident?.file_path)
    || ''
  ).trim().toLowerCase();
}

function getIncidentSourceKind(incident) {
  const source = String(incident?.source_kind || '').trim().toLowerCase();
  if (source) return source;
  const ext = getIncidentFileExt(incident);
  if (!ext) return '';
  if (ext === 'pdf') return 'pdf';
  if (['txt', 'rtf', 'csv', 'json', 'xml', 'ini', 'conf', 'md', 'log'].includes(ext)) return 'text';
  return 'metadata';
}

function parseDateToEpoch(dateValue, endOfDay = false) {
  const value = String(dateValue || '').trim();
  if (!value) return null;
  const stamp = endOfDay ? `${value}T23:59:59` : `${value}T00:00:00`;
  const ms = new Date(stamp).getTime();
  if (!Number.isFinite(ms)) return null;
  return Math.floor(ms / 1000);
}

function buildIncidentSearchText(item) {
  const base = [
    item?.hostname,
    item?.user_login,
    item?.user_full_name,
    item?.file_path,
    item?.file_name,
    item?.short_reason,
    item?.reason,
    item?.pattern,
    item?.patterns,
    item?.source_kind,
    item?.file_ext,
  ].map((v) => String(v || '').toLowerCase());
  const matches = Array.isArray(item?.matched_patterns) ? item.matched_patterns : [];
  const fragments = matches.flatMap((entry) => ([
    String(entry?.pattern_name || '').toLowerCase(),
    String(entry?.pattern || '').toLowerCase(),
    String(entry?.value || '').toLowerCase(),
    String(entry?.snippet || '').toLowerCase(),
  ]));
  return [...base, ...fragments].join(' ');
}

function applyIncidentFilters(items, filters) {
  const rows = Array.isArray(items) ? items : [];
  const qNeedle = String(filters?.q || '').trim().toLowerCase();
  const statusFilter = String(filters?.status || 'all').trim().toLowerCase();
  const severityFilter = String(filters?.severity || 'all').trim().toLowerCase();
  const sourceFilter = String(filters?.source_kind || 'all').trim().toLowerCase();
  const fileExtFilter = String(filters?.file_ext || '').trim().replace(/^\./, '').toLowerCase();
  const hasFragment = Boolean(filters?.has_fragment);
  const dateFrom = parseDateToEpoch(filters?.date_from, false);
  const dateTo = parseDateToEpoch(filters?.date_to, true);

  return rows.filter((item) => {
    const createdAt = Number(item?.created_at || 0);
    if (dateFrom !== null && createdAt < dateFrom) return false;
    if (dateTo !== null && createdAt > dateTo) return false;

    if (statusFilter !== 'all') {
      const status = String(item?.status || '').trim().toLowerCase();
      if (status !== statusFilter) return false;
    }

    if (severityFilter !== 'all') {
      const severity = String(item?.severity || '').trim().toLowerCase();
      if (severity !== severityFilter) return false;
    }

    if (sourceFilter !== 'all') {
      const source = getIncidentSourceKind(item);
      if (source !== sourceFilter) return false;
    }

    if (fileExtFilter) {
      const ext = getIncidentFileExt(item);
      if (ext !== fileExtFilter) return false;
    }

    if (hasFragment) {
      const matches = Array.isArray(item?.matched_patterns) ? item.matched_patterns : [];
      const hasAny = matches.some((entry) => (
        String(entry?.snippet || '').trim()
        || String(entry?.value || '').trim()
      ));
      if (!hasAny) return false;
    }

    if (qNeedle) {
      const haystack = buildIncidentSearchText(item);
      if (!haystack.includes(qNeedle)) return false;
    }

    return true;
  });
}

function parseIncidentItems(response) {
  if (Array.isArray(response?.items)) return response.items;
  if (Array.isArray(response)) return response;
  return [];
}

function canonicalHost(value) {
  const normalized = normalizeHost(value);
  if (!normalized) return '';
  return normalized
    .replace(/\$$/, '')
    .split(/[.\s/\\]+/)[0];
}

function incidentMatchesHost(item, host) {
  const hostNeedle = canonicalHost(host);
  if (!hostNeedle) return false;
  const candidates = [
    item?.hostname,
    item?.host,
    item?.agent_id,
    item?.agentId,
    item?.computer_name,
    item?.computer,
    item?.device_name,
    item?.machine_name,
  ];
  return candidates.some((candidate) => {
    const probe = canonicalHost(candidate);
    if (!probe) return false;
    return probe === hostNeedle || probe.includes(hostNeedle) || hostNeedle.includes(probe);
  });
}

function filterIncidentsByHost(items, host) {
  const rows = Array.isArray(items) ? items : [];
  return rows.filter((item) => incidentMatchesHost(item, host));
}

function uniqueIncidents(items) {
  const rows = Array.isArray(items) ? items : [];
  const seen = new Set();
  const out = [];
  rows.forEach((item) => {
    const id = String(item?.id || '').trim();
    const key = id || [
      canonicalHost(item?.hostname || item?.host || item?.agent_id || item?.computer_name),
      String(item?.created_at || ''),
      String(item?.file_path || item?.file_name || ''),
      String(item?.pattern || ''),
    ].join('|');
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(item);
  });
  return out;
}

function resolvePcIp(pc) {
  const direct = String(pc?.ip_primary || '').trim();
  if (direct) return direct;
  if (Array.isArray(pc?.ip_list) && pc.ip_list.length > 0) {
    const candidate = firstIpv4(pc.ip_list[0]);
    if (candidate) return candidate;
  }
  return firstIpv4(pc?.ip_address || '');
}

function renderFragments(incident) {
  const matches = Array.isArray(incident?.matched_patterns) ? incident.matched_patterns : [];
  if (matches.length === 0) {
    return <Typography variant="caption" color="text.secondary">Фрагменты не найдены</Typography>;
  }
  return (
    <Stack spacing={0.7}>
      {matches.slice(0, 6).map((item, idx) => (
        <Paper key={`${incident.id || 'inc'}-${idx}`} variant="outlined" sx={{ p: 0.8 }}>
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            {item.pattern_name || item.pattern || 'pattern'}
          </Typography>
          {!!String(item.value || '').trim() && (
            <Typography variant="caption" sx={{ display: 'block' }}>
              Значение: {String(item.value)}
            </Typography>
          )}
          {!!String(item.snippet || '').trim() && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              Фрагмент: {String(item.snippet)}
            </Typography>
          )}
        </Paper>
      ))}
    </Stack>
  );
}

function aggregateHostsFromIncidents(items) {
  const rows = Array.isArray(items) ? items : [];
  const map = new Map();
  rows.forEach((item) => {
    const host = String(item?.hostname || '').trim();
    if (!host) return;
    const key = host.toLowerCase();
    const createdAt = Number(item?.created_at || 0);
    const status = String(item?.status || '').toLowerCase();
    const severity = String(item?.severity || '').toLowerCase();
    const source = String(item?.source_kind || '').trim().toLowerCase();
    const ext = inferFileExt(item?.file_name) || inferFileExt(item?.file_path);

    let entry = map.get(key);
    if (!entry) {
      entry = {
        hostname: host,
        incidents_total: 0,
        incidents_new: 0,
        last_incident_at: 0,
        top_severity: 'none',
        branch: String(item?.branch || '').trim(),
        user: String(item?.user_full_name || item?.user_login || '').trim(),
        ip_address: '',
        _ext_counts: {},
        _source_counts: {},
      };
      map.set(key, entry);
    }

    entry.incidents_total += 1;
    if (status === 'new') entry.incidents_new += 1;
    if (createdAt > Number(entry.last_incident_at || 0)) {
      entry.last_incident_at = createdAt;
      if (!entry.branch) entry.branch = String(item?.branch || '').trim();
      if (!entry.user) entry.user = String(item?.user_full_name || item?.user_login || '').trim();
    }

    const rank = severity === 'high' ? 3 : severity === 'medium' ? 2 : severity === 'low' ? 1 : 0;
    const prevRank = entry.top_severity === 'high' ? 3 : entry.top_severity === 'medium' ? 2 : entry.top_severity === 'low' ? 1 : 0;
    if (rank > prevRank) {
      entry.top_severity = rank === 3 ? 'high' : rank === 2 ? 'medium' : rank === 1 ? 'low' : 'none';
    }

    if (ext) entry._ext_counts[ext] = Number(entry._ext_counts[ext] || 0) + 1;
    if (source) entry._source_counts[source] = Number(entry._source_counts[source] || 0) + 1;
  });

  return Array.from(map.values()).map((entry) => {
    const topExts = Object.entries(entry._ext_counts)
      .sort((a, b) => Number(b[1]) - Number(a[1]) || String(a[0]).localeCompare(String(b[0]), 'ru'))
      .slice(0, 5)
      .map(([name]) => String(name));
    const topSourceKinds = Object.entries(entry._source_counts)
      .sort((a, b) => Number(b[1]) - Number(a[1]) || String(a[0]).localeCompare(String(b[0]), 'ru'))
      .slice(0, 5)
      .map(([name]) => String(name));

    return {
      hostname: entry.hostname,
      incidents_total: entry.incidents_total,
      incidents_new: entry.incidents_new,
      last_incident_at: Number(entry.last_incident_at || 0),
      top_severity: entry.top_severity,
      branch: entry.branch,
      user: entry.user,
      ip_address: entry.ip_address,
      top_exts: topExts,
      top_source_kinds: topSourceKinds,
    };
  });
}

function ScanCenter() {
  const { hasPermission } = useAuth();
  const canScanAck = hasPermission('scan.ack');
  const canScanTasks = hasPermission('scan.tasks');

  const [dashboard, setDashboard] = useState({ totals: {}, daily: [], by_severity: [], by_branch: [], new_hosts: [] });
  const [hosts, setHosts] = useState([]);
  const [agents, setAgents] = useState([]);
  const [computers, setComputers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [busyIncident, setBusyIncident] = useState('');
  const [busyTaskAgent, setBusyTaskAgent] = useState('');
  const [busyAckAllHost, setBusyAckAllHost] = useState(false);

  const [hostDrawerOpen, setHostDrawerOpen] = useState(false);
  const [selectedHost, setSelectedHost] = useState('');
  const [hostIncidentPool, setHostIncidentPool] = useState([]);
  const [hostLoading, setHostLoading] = useState(false);
  const [incidentQ, setIncidentQ] = useState('');
  const [incidentStatus, setIncidentStatus] = useState('all');
  const [incidentSeverity, setIncidentSeverity] = useState('all');
  const [incidentSourceKind, setIncidentSourceKind] = useState('all');
  const [incidentFileExt, setIncidentFileExt] = useState('');
  const [incidentDateFrom, setIncidentDateFrom] = useState('');
  const [incidentDateTo, setIncidentDateTo] = useState('');
  const [incidentHasFragment, setIncidentHasFragment] = useState(false);
  const hostIncidentRequestIdRef = useRef(0);

  const resetHostFilters = () => {
    setIncidentQ('');
    setIncidentStatus('all');
    setIncidentSeverity('all');
    setIncidentSourceKind('all');
    setIncidentFileExt('');
    setIncidentDateFrom('');
    setIncidentDateTo('');
    setIncidentHasFragment(false);
  };

  const load = async () => {
    try {
      setLoading(true);
      const [dashboardRes, hostsRes, agentsRes, computersRes] = await Promise.allSettled([
        scanAPI.getDashboard(),
        scanAPI.getHosts({ limit: 300 }),
        scanAPI.getAgents(),
        equipmentAPI.getAgentComputers(),
      ]);

      const dashboardData = dashboardRes.status === 'fulfilled' && dashboardRes.value && typeof dashboardRes.value === 'object'
        ? dashboardRes.value
        : { totals: {}, daily: [], by_severity: [], by_branch: [], new_hosts: [] };
      let hostData = hostsRes.status === 'fulfilled' ? hostsRes.value : [];
      const agentData = agentsRes.status === 'fulfilled' ? agentsRes.value : [];
      const pcData = computersRes.status === 'fulfilled' ? computersRes.value : [];

      const hostStatusCode = Number(hostsRes?.reason?.response?.status || 0);
      if ((!Array.isArray(hostData) || hostData.length === 0) && hostStatusCode === 404) {
        try {
          const incidentsData = await scanAPI.getIncidents({ limit: 500, offset: 0 });
          hostData = aggregateHostsFromIncidents(incidentsData?.items);
        } catch (fallbackError) {
          console.error('Scan hosts fallback failed', fallbackError);
          hostData = [];
        }
      }

      setDashboard(dashboardData);
      setHosts(Array.isArray(hostData) ? hostData : []);
      setAgents(Array.isArray(agentData) ? agentData : []);
      setComputers(Array.isArray(pcData) ? pcData : []);
    } catch (error) {
      console.error('Scan center load failed', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const computerMetaByHost = useMemo(() => {
    const map = {};
    computers.forEach((pc) => {
      const host = normalizeHost(pc?.hostname);
      if (!host) return;
      const prev = map[host] || {};
      map[host] = {
        branch_name: String(pc?.branch_name || prev.branch_name || '').trim(),
        user_full_name: String(pc?.user_full_name || prev.user_full_name || '').trim(),
        user_login: String(pc?.user_login || prev.user_login || '').trim(),
        ip_address: String(resolvePcIp(pc) || prev.ip_address || '').trim(),
      };
    });
    return map;
  }, [computers]);

  const getHostMeta = (item) => {
    const host = normalizeHost(item?.hostname || item?.agent_id || selectedHost);
    return computerMetaByHost[host] || {};
  };

  const resolveBranch = (item) => {
    const meta = getHostMeta(item);
    return String(item?.branch || meta.branch_name || '').trim() || 'Без филиала';
  };

  const resolveUser = (item) => {
    const meta = getHostMeta(item);
    const full = String(item?.user_full_name || meta.user_full_name || '').trim();
    const login = String(item?.user_login || meta.user_login || '').trim();
    return full || login || '-';
  };

  const resolveIp = (item) => {
    const meta = getHostMeta(item);
    return String(item?.ip_address || meta.ip_address || '').trim() || '-';
  };

  const hostRows = useMemo(() => {
    const list = Array.isArray(hosts) ? hosts : [];
    return list.map((item) => {
      const host = String(item.hostname || '').trim();
      const meta = computerMetaByHost[normalizeHost(host)] || {};
      const branchValue = String(item.branch || meta.branch_name || '').trim() || 'Без филиала';
      const userValue = String(item.user || meta.user_full_name || meta.user_login || '').trim() || '-';
      const ipValue = String(item.ip_address || meta.ip_address || '').trim() || '-';
      return {
        hostname: host || 'unknown-host',
        total: Number(item.incidents_total || 0),
        newCount: Number(item.incidents_new || 0),
        lastTs: Number(item.last_incident_at || 0),
        branch: branchValue,
        user: userValue,
        ip: ipValue,
        topSeverity: String(item.top_severity || 'none'),
        topExts: Array.isArray(item.top_exts) ? item.top_exts : [],
        topSourceKinds: Array.isArray(item.top_source_kinds) ? item.top_source_kinds : [],
      };
    }).sort((a, b) => b.newCount - a.newCount || b.lastTs - a.lastTs);
  }, [hosts, computerMetaByHost]);

  const filteredHostRows = useMemo(() => {
    const needle = String(q || '').trim().toLowerCase();
    if (!needle) return hostRows;
    return hostRows.filter((row) => {
      const text = [row.hostname, row.branch, row.user, row.ip].map((v) => String(v || '').toLowerCase()).join(' ');
      return text.includes(needle);
    });
  }, [hostRows, q]);

  const loadHostIncidents = async (host) => {
    if (!host) return;
    const requestId = hostIncidentRequestIdRef.current + 1;
    hostIncidentRequestIdRef.current = requestId;
    setHostLoading(true);
    try {
      let hostItems = [];

      const hostQueryVariants = [
        { hostname: host },
        { host },
        { agent_id: host },
        { agentId: host },
        { computer_name: host },
      ];
      for (const variant of hostQueryVariants) {
        const response = await scanAPI.getIncidents({
          ...variant,
          limit: 500,
          offset: 0,
        });
        if (requestId !== hostIncidentRequestIdRef.current) return;
        const items = parseIncidentItems(response);
        const matched = filterIncidentsByHost(items, host);
        if (matched.length > 0) {
          hostItems = matched;
          break;
        }
      }

      // Full fallback: old API can ignore host params entirely.
      // In this case we page through common incident feed and filter locally.
      if (hostItems.length === 0) {
        const batchSize = 500;
        const maxPages = 20;
        let offset = 0;
        const collected = [];
        for (let page = 0; page < maxPages; page += 1) {
          const fallbackResponse = await scanAPI.getIncidents({
            limit: batchSize,
            offset,
          });
          if (requestId !== hostIncidentRequestIdRef.current) return;
          const fallbackItems = parseIncidentItems(fallbackResponse);
          if (fallbackItems.length === 0) break;
          collected.push(...filterIncidentsByHost(fallbackItems, host));
          if (fallbackItems.length < batchSize) break;
          offset += batchSize;
        }
        hostItems = collected;
      }

      if (requestId !== hostIncidentRequestIdRef.current) return;
      const uniqueHostItems = uniqueIncidents(hostItems);
      setHostIncidentPool(uniqueHostItems.slice().sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0)));
    } catch (error) {
      console.error('Host incidents load failed', error);
      if (requestId === hostIncidentRequestIdRef.current) {
        setHostIncidentPool([]);
      }
    } finally {
      if (requestId === hostIncidentRequestIdRef.current) {
        setHostLoading(false);
      }
    }
  };

  const openHostDetails = (hostname) => {
    const host = String(hostname || '').trim();
    if (!host) return;
    resetHostFilters();
    setSelectedHost(host);
    setHostDrawerOpen(true);
  };

  useEffect(() => {
    if (!hostDrawerOpen || !selectedHost) return;
    loadHostIncidents(selectedHost);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    hostDrawerOpen,
    selectedHost,
  ]);

  const hostIncidents = useMemo(() => {
    const filtered = applyIncidentFilters(hostIncidentPool, {
      q: incidentQ,
      status: incidentStatus,
      severity: incidentSeverity,
      source_kind: incidentSourceKind,
      file_ext: incidentFileExt,
      date_from: incidentDateFrom,
      date_to: incidentDateTo,
      has_fragment: incidentHasFragment,
    });
    return filtered.slice().sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));
  }, [
    hostIncidentPool,
    incidentQ,
    incidentStatus,
    incidentSeverity,
    incidentSourceKind,
    incidentFileExt,
    incidentDateFrom,
    incidentDateTo,
    incidentHasFragment,
  ]);

  const ackIncident = async (incident) => {
    if (!canScanAck) return;
    const incidentId = String(incident?.id || '').trim();
    if (!incidentId) return;
    const keepScroll = window.scrollY;
    try {
      const wasNew = String(incident?.status || '').toLowerCase() === 'new';
      const hostKey = normalizeHost(incident?.hostname || selectedHost);
      setBusyIncident(incidentId);
      await scanAPI.ackIncident(incidentId, 'web-user');
      setHostIncidentPool((prev) => prev.map((item) => {
        if (String(item.id) !== incidentId) return item;
        return { ...item, status: 'ack' };
      }));
      if (wasNew) {
        setHosts((prev) => prev.map((row) => {
          if (normalizeHost(row.hostname) !== hostKey) return row;
          return { ...row, incidents_new: Math.max(0, Number(row.incidents_new || 0) - 1) };
        }));
      }
      setDashboard((prev) => {
        const next = { ...(prev || {}) };
        const totals = { ...(next.totals || {}) };
        if (wasNew) {
          totals.incidents_new = Math.max(0, Number(totals.incidents_new || 0) - 1);
        }
        next.totals = totals;
        return next;
      });
    } catch (error) {
      console.error('Ack incident failed', error);
    } finally {
      setBusyIncident('');
      requestAnimationFrame(() => {
        window.scrollTo({ top: keepScroll, behavior: 'auto' });
      });
    }
  };

  const ackAllHostIncidents = async () => {
    if (!canScanAck) return;
    const pendingIds = hostIncidentPool
      .filter((item) => String(item.status || '').toLowerCase() === 'new')
      .map((item) => String(item.id || '').trim())
      .filter(Boolean);
    if (pendingIds.length === 0) return;

    setBusyAckAllHost(true);
    try {
      const results = await Promise.allSettled(
        pendingIds.map((id) => scanAPI.ackIncident(id, 'web-user')),
      );
      const ackedIds = pendingIds.filter((_, idx) => results[idx]?.status === 'fulfilled');
      const ackedSet = new Set(ackedIds.map((id) => String(id)));
      if (ackedSet.size > 0) {
        const hostKey = normalizeHost(selectedHost);
        const oldNewCount = hostIncidentPool.filter((item) => (
          String(item.status || '').toLowerCase() === 'new' && ackedSet.has(String(item.id))
        )).length;
        setHostIncidentPool((prev) => prev.map((item) => {
          if (!ackedSet.has(String(item.id))) return item;
          return { ...item, status: 'ack' };
        }));
        if (oldNewCount > 0) {
          setHosts((prev) => prev.map((row) => {
            if (normalizeHost(row.hostname) !== hostKey) return row;
            return { ...row, incidents_new: Math.max(0, Number(row.incidents_new || 0) - oldNewCount) };
          }));
        }
        setDashboard((prev) => {
          const next = { ...(prev || {}) };
          const totals = { ...(next.totals || {}) };
          totals.incidents_new = Math.max(0, Number(totals.incidents_new || 0) - oldNewCount);
          next.totals = totals;
          return next;
        });
      }
    } catch (error) {
      console.error('Ack all host incidents failed', error);
    } finally {
      setBusyAckAllHost(false);
    }
  };

  const enqueueTask = async (agentId, command) => {
    if (!canScanTasks) return;
    try {
      setBusyTaskAgent(agentId);
      await scanAPI.createTask({
        agent_id: agentId,
        command,
        dedupe_key: `${command}:${agentId}`,
      });
      await load();
    } catch (error) {
      console.error('Create task failed', error);
    } finally {
      setBusyTaskAgent('');
    }
  };

  const totals = dashboard.totals || {};
  const hostNewCount = hostIncidentPool.filter((item) => String(item.status || '').toLowerCase() === 'new').length;
  const hostExtOptions = useMemo(() => {
    const set = new Set();
    hostIncidentPool.forEach((item) => {
      const ext = getIncidentFileExt(item);
      if (ext) set.add(ext);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'ru'));
  }, [hostIncidentPool]);
  const hostSourceOptions = useMemo(() => {
    const set = new Set();
    hostIncidentPool.forEach((item) => {
      const source = getIncidentSourceKind(item);
      if (source) set.add(source);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'ru'));
  }, [hostIncidentPool]);
  const sourceSelectOptions = useMemo(() => {
    const base = ['text', 'pdf', 'pdf_slice'];
    const known = new Set(base);
    const extra = hostSourceOptions.filter((option) => !known.has(option));
    return [...base, ...extra];
  }, [hostSourceOptions]);

  return (
    <MainLayout>
      <Box sx={{ width: '100%', pb: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Центр сканирования</Typography>
          <IconButton onClick={load} disabled={loading} color="primary">
            <RefreshIcon />
          </IconButton>
        </Box>

        {!loading && Number(totals.incidents_new || 0) > 0 && (
          <Alert severity="warning" icon={<WarningAmberIcon fontSize="inherit" />} sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Новые инциденты: {Number(totals.incidents_new || 0)}
            </Typography>
            <Typography variant="body2">
              {(Array.isArray(dashboard.new_hosts) ? dashboard.new_hosts : []).slice(0, 8).join(', ')}
              {(Array.isArray(dashboard.new_hosts) ? dashboard.new_hosts.length : 0) > 8
                ? ` и еще ${(Array.isArray(dashboard.new_hosts) ? dashboard.new_hosts.length : 0) - 8}`
                : ''}
            </Typography>
          </Alert>
        )}

        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Агенты" value={Number(totals.agents_total || 0)} helper="зарегистрировано" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="В сети" value={Number(totals.agents_online || 0)} helper="активны за 5 минут" color="success.main" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Новые инциденты" value={Number(totals.incidents_new || 0)} helper="статус NEW" color="warning.main" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Очередь задач" value={Number(totals.queue_active || 0)} helper={`просрочено: ${Number(totals.queue_expired || 0)}`} color="info.main" />
          </Grid>
        </Grid>

        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} md={4}>
            <MiniBars title="Инциденты по severity" rows={dashboard.by_severity || []} color="#b71c1c" />
          </Grid>
          <Grid item xs={12} md={4}>
            <MiniBars title="Инциденты по филиалам" rows={dashboard.by_branch || []} color="#1565c0" />
          </Grid>
          <Grid item xs={12} md={4}>
            <DailyBars rows={dashboard.daily || []} />
          </Grid>
        </Grid>

        <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
          <TextField
            size="small"
            fullWidth
            label="Поиск по ПК, филиалу, пользователю, IP"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="TMN-IT-0009, филиал, ФИО, IP"
          />
        </Paper>

        <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>Компьютеры с находками</Typography>
        <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
          {loading ? (
            <Box sx={{ py: 2, display: 'flex', justifyContent: 'center' }}><CircularProgress size={28} /></Box>
          ) : filteredHostRows.length === 0 ? (
            <Typography color="text.secondary">Инцидентов пока нет.</Typography>
          ) : (
            <Stack spacing={1}>
              {filteredHostRows.slice(0, 100).map((row) => (
                <Paper key={row.hostname} variant="outlined" sx={{ p: 1.2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1 }}>
                    <Box>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{row.hostname}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {row.branch || 'Без филиала'} · {row.user || '-'} · IP: {row.ip || '-'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Всего: {row.total} · Новые: {row.newCount} · Последний: {formatTs(row.lastTs)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        Типы: {(row.topExts || []).join(', ') || '-'} · Источники: {(row.topSourceKinds || []).join(', ') || '-'}
                      </Typography>
                    </Box>
                    <Button type="button" size="small" variant="outlined" onClick={() => openHostDetails(row.hostname)}>
                      Просмотреть инциденты
                    </Button>
                  </Box>
                </Paper>
              ))}
            </Stack>
          )}
        </Paper>

        <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>Агенты и очередь</Typography>
        <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
          {loading ? (
            <Box sx={{ py: 2, display: 'flex', justifyContent: 'center' }}><CircularProgress size={28} /></Box>
          ) : agents.length === 0 ? (
            <Typography color="text.secondary">Нет данных по агентам.</Typography>
          ) : (
            <Stack spacing={1.5}>
              {agents.map((agent) => {
                const hostName = String(agent.hostname || agent.agent_id || '').trim();
                return (
                  <Paper key={agent.agent_id} variant="outlined" sx={{ p: 1.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                          {hostName || '-'}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {resolveBranch(agent)} · IP: {resolveIp(agent)} · {formatLastSeen(agent.age_seconds, agent.is_online)}
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Chip size="small" color={agent.is_online ? 'success' : 'default'} label={agent.is_online ? 'В сети' : 'Не в сети'} />
                        <Chip size="small" label={`Очередь: ${Number(agent.queue_size || 0)}`} />
                        <Button
                          type="button"
                          size="small"
                          variant="outlined"
                          startIcon={<PlayArrowIcon />}
                          disabled={!canScanTasks || busyTaskAgent === agent.agent_id}
                          onClick={() => enqueueTask(agent.agent_id, 'scan_now')}
                        >
                          Сканировать
                        </Button>
                        <Button
                          type="button"
                          size="small"
                          variant="outlined"
                          disabled={!canScanTasks || busyTaskAgent === agent.agent_id}
                          onClick={() => enqueueTask(agent.agent_id, 'ping')}
                        >
                          Проверить связь
                        </Button>
                        <Button
                          type="button"
                          size="small"
                          variant="contained"
                          onClick={() => openHostDetails(hostName)}
                          disabled={!hostName}
                        >
                          Просмотреть инциденты
                        </Button>
                      </Box>
                    </Box>
                  </Paper>
                );
              })}
            </Stack>
          )}
        </Paper>

        <Drawer anchor="right" open={hostDrawerOpen} onClose={() => setHostDrawerOpen(false)}>
          <Box sx={{ width: { xs: 360, sm: 620 }, p: 2.2 }}>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              {selectedHost || 'Компьютер'}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Все найденные инциденты по выбранному ПК
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.4 }}>
              Показано: {hostIncidents.length} из {hostIncidentPool.length}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.2, mb: 0.6, flexWrap: 'wrap' }}>
              <Chip size="small" color={hostNewCount > 0 ? 'warning' : 'default'} label={`Новых: ${hostNewCount}`} />
              <Button
                type="button"
                size="small"
                variant="contained"
                onClick={ackAllHostIncidents}
                disabled={!canScanAck || hostLoading || busyAckAllHost || hostNewCount === 0}
              >
                Просмотрено все
              </Button>
              <Button
                type="button"
                size="small"
                variant={incidentHasFragment ? 'contained' : 'outlined'}
                onClick={() => setIncidentHasFragment((prev) => !prev)}
              >
                Только с фрагментами
              </Button>
              <Button
                type="button"
                size="small"
                variant="outlined"
                onClick={resetHostFilters}
                disabled={hostLoading}
              >
                Сброс фильтров
              </Button>
            </Box>
            <Grid container spacing={1.2} sx={{ mb: 1 }}>
              <Grid item xs={12}>
                <TextField
                  size="small"
                  fullWidth
                  label="Поиск по пути/фрагменту/паттерну"
                  value={incidentQ}
                  onChange={(e) => setIncidentQ(e.target.value)}
                  placeholder="pdf, паспорт, ДСП, путь файла"
                />
              </Grid>
              <Grid item xs={6}>
                <FormControl size="small" fullWidth>
                  <InputLabel>Статус</InputLabel>
                  <Select value={incidentStatus} label="Статус" onChange={(e) => setIncidentStatus(e.target.value)}>
                    <MenuItem value="all">Все</MenuItem>
                    <MenuItem value="new">NEW</MenuItem>
                    <MenuItem value="ack">ACK</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={6}>
                <FormControl size="small" fullWidth>
                  <InputLabel>Severity</InputLabel>
                  <Select value={incidentSeverity} label="Severity" onChange={(e) => setIncidentSeverity(e.target.value)}>
                    <MenuItem value="all">Все</MenuItem>
                    <MenuItem value="high">High</MenuItem>
                    <MenuItem value="medium">Medium</MenuItem>
                    <MenuItem value="low">Low</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={6}>
                <FormControl size="small" fullWidth>
                  <InputLabel>Источник</InputLabel>
                  <Select value={incidentSourceKind} label="Источник" onChange={(e) => setIncidentSourceKind(e.target.value)}>
                    <MenuItem value="all">Все</MenuItem>
                    {sourceSelectOptions.map((option) => (
                      <MenuItem key={option} value={option}>{option}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={6}>
                <TextField
                  size="small"
                  fullWidth
                  label="Расширение файла"
                  value={incidentFileExt}
                  onChange={(e) => setIncidentFileExt(e.target.value)}
                  placeholder={hostExtOptions[0] || 'pdf/txt/docx'}
                />
              </Grid>
              <Grid item xs={6}>
                <TextField
                  size="small"
                  fullWidth
                  type="date"
                  label="Дата с"
                  value={incidentDateFrom}
                  onChange={(e) => setIncidentDateFrom(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
              <Grid item xs={6}>
                <TextField
                  size="small"
                  fullWidth
                  type="date"
                  label="Дата по"
                  value={incidentDateTo}
                  onChange={(e) => setIncidentDateTo(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
            </Grid>
            <Divider sx={{ my: 1.3 }} />

            {hostLoading ? (
              <Box sx={{ py: 3, display: 'flex', justifyContent: 'center' }}><CircularProgress size={30} /></Box>
            ) : hostIncidents.length === 0 ? (
              <Box>
                <Typography color="text.secondary">
                  {hostIncidentPool.length > 0
                    ? 'По текущим фильтрам ничего не найдено.'
                    : 'Инциденты для этого ПК не найдены.'}
                </Typography>
                {hostIncidentPool.length > 0 && (
                  <Button
                    type="button"
                    size="small"
                    variant="text"
                    onClick={resetHostFilters}
                    sx={{ mt: 0.5 }}
                  >
                    Сбросить фильтры
                  </Button>
                )}
              </Box>
            ) : (
              <Stack spacing={1.3}>
                {hostIncidents.map((incident) => (
                  <Paper key={incident.id} variant="outlined" sx={{ p: 1.2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.6, gap: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        {incident.severity || '-'} · {formatTs(incident.created_at)}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Chip size="small" color={incident.status === 'new' ? 'warning' : 'default'} label={incident.status || '-'} />
                        {incident.status === 'new' && (
                          <Button
                            type="button"
                            size="small"
                            variant="outlined"
                            disabled={!canScanAck || busyIncident === incident.id}
                            onClick={(e) => { e.preventDefault(); ackIncident(incident); }}
                          >
                            ACK
                          </Button>
                        )}
                      </Box>
                    </Box>
                    <Typography variant="body2" sx={{ mb: 0.8 }}>{incident.file_path || '-'}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.4 }}>
                      Тип: {getIncidentFileExt(incident) || '-'} · Источник: {getIncidentSourceKind(incident) || '-'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.4 }}>
                      {resolveBranch(incident)} · {resolveUser(incident)} · IP: {resolveIp(incident)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.8 }}>
                      {incident.short_reason || 'Совпадения по паттернам'}
                    </Typography>
                    {renderFragments(incident)}
                  </Paper>
                ))}
              </Stack>
            )}
          </Box>
        </Drawer>
      </Box>
    </MainLayout>
  );
}

export default ScanCenter;

