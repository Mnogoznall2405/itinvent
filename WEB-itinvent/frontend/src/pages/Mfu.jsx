import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Drawer,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  Link,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import RefreshIcon from '@mui/icons-material/Refresh';
import BuildIcon from '@mui/icons-material/Build';
import RouterIcon from '@mui/icons-material/Router';
import PrintIcon from '@mui/icons-material/Print';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import MainLayout from '../components/layout/MainLayout';
import { mfuAPI, equipmentAPI } from '../api/client';
import jsonAPI from '../api/json_client';
import { useAuth } from '../contexts/AuthContext';

const REFRESH_INTERVAL_MS = 60_000;
const DASHBOARD_PERIOD_DAYS = 365;
const DASHBOARD_RECENT_LIMIT = 8;
const DASHBOARD_LIMIT = 5000;
const PAGE_MONTHS = 12;
// Cartridge color is extracted automatically from the consumable name

const PRINTER_COMPONENT_OPTIONS = [
  { value: 'fuser', label: 'Фьюзер' },
  { value: 'photoconductor', label: 'Фотобарабан' },
  { value: 'waste_toner', label: 'Отработанный тонер' },
  { value: 'transfer_belt', label: 'Трансферный ремень' },
];

const COMPONENT_MATCH_TOKENS = {
  fuser: ['фьюзер', 'fuser'],
  photoconductor: ['фотобарабан', 'барабан', 'photoconductor', 'drum', 'imaging'],
  waste_toner: ['отработ', 'бункер', 'waste', 'container', 'тонер'],
  transfer_belt: ['трансфер', 'ремень', 'transfer', 'belt'],
};

const normalizeText = (value) => String(value || '').trim().toLowerCase();
const toNumberOrNull = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};
const toCount = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

const formatDateTime = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ru-RU');
};

const formatDateOnly = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('ru-RU');
};

const formatMonthLabel = (value) => {
  const text = String(value || '').trim();
  const match = text.match(/^(\d{4})-(\d{2})$/);
  if (!match) return text || '-';
  return `${match[2]}.${match[1]}`;
};

const getPingMeta = (status) => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'online') return { label: 'В сети', color: 'success' };
  if (normalized === 'offline') return { label: 'Оффлайн', color: 'error' };
  return { label: 'Неизвестно', color: 'default' };
};

const getSupplySeverity = (percent) => {
  if (!Number.isFinite(percent)) return 'primary';
  if (percent < 20) return 'error';
  if (percent < 40) return 'warning';
  return 'success';
};

const flattenGroupedDevices = (grouped) => {
  const rows = [];
  Object.entries(grouped || {}).forEach(([branchName, locations]) => {
    Object.entries(locations || {}).forEach(([locationName, items]) => {
      (items || []).forEach((item) => {
        rows.push({
          ...item,
          branch_name: item?.branch_name || branchName,
          location_name: item?.location_name || locationName,
        });
      });
    });
  });
  return rows;
};

const toConsumableOption = (entry) => ({
  id: toNumberOrNull(entry?.id ?? entry?.ID),
  inv_no: String(entry?.inv_no ?? entry?.INV_NO ?? '').trim(),
  type_name: String(entry?.type_name ?? entry?.TYPE_NAME ?? '').trim(),
  model_name: String(entry?.model_name ?? entry?.MODEL_NAME ?? '').trim(),
  qty: Number(entry?.qty ?? entry?.QTY ?? 0) || 0,
  branch_name: String(entry?.branch_name ?? entry?.BRANCH_NAME ?? '').trim(),
  location_name: String(entry?.location_name ?? entry?.LOCATION_NAME ?? '').trim(),
});

const decodeHexLabel = (value) => {
  const raw = String(value || '').trim();
  const match = raw.match(/^0x([0-9a-f]+)$/i);
  if (!match) return raw;

  const hex = String(match[1] || '');
  if (!hex || (hex.length % 2 !== 0)) return raw;

  try {
    const bytes = new Uint8Array(hex.match(/.{1,2}/g).map((part) => parseInt(part, 16)));
    const encodings = ['utf-8', 'windows-1251'];
    for (const encoding of encodings) {
      try {
        const decoded = new TextDecoder(encoding).decode(bytes).replace(/\u0000/g, '').trim();
        if (decoded) return decoded;
      } catch {
        // Continue with next decoder.
      }
    }
  } catch {
    return raw;
  }

  return raw;
};

const formatReplacementItemName = (value) => {
  let text = decodeHexLabel(value);
  text = String(text || '').trim();
  if (!text) return '-';

  // Remove vendor serial suffixes like ;SND2007300170C0000 from UI and saved works.
  text = text.replace(/\s*;\s*SND[0-9A-Z_-]+/gi, '');
  text = text.replace(/\s*,?\s*SND[0-9A-Z_-]+/gi, '');
  text = text.replace(/\s*;\s*SN[0-9A-Z_-]{8,}/gi, '');
  text = text.replace(/\s*,?\s*SN[0-9A-Z_-]{8,}/gi, '');

  const replacements = [
    { pattern: /\bfuser\b/gi, value: 'Фьюзер' },
    { pattern: /\bphotoconductor\b/gi, value: 'Фотобарабан' },
    { pattern: /\bwaste[_\s-]*toner\b/gi, value: 'Отработанный тонер' },
    { pattern: /\btransfer[_\s-]*belt\b/gi, value: 'Трансферный ремень' },
    { pattern: /\bdrum cartridge\b/gi, value: 'Фотобарабан' },
    { pattern: /\btoner cartridge\b/gi, value: 'Тонер-картридж' },
    { pattern: /\bcartridge\b/gi, value: 'Картридж' },
    { pattern: /\bwaste toner container\b/gi, value: 'Бункер отработки' },
    { pattern: /\bfuser unit\b/gi, value: 'Фьюзер' },
    { pattern: /\btransfer belt\b/gi, value: 'Трансферный ремень' },
    { pattern: /\bimaging unit\b/gi, value: 'Блок формирования изображения' },
    { pattern: /\bmaintenance kit\b/gi, value: 'Сервисный комплект' },
    { pattern: /\bPN\b/gi, value: 'арт.' },
  ];
  replacements.forEach((entry) => {
    text = text.replace(entry.pattern, entry.value);
  });

  text = text.replace(/\s{2,}/g, ' ').replace(/\s+,/g, ',').trim();
  return text || '-';
};

const formatConsumableLabel = (entry) => {
  const option = toConsumableOption(entry);
  const model = formatReplacementItemName(option.model_name || '-');
  return `${model} | ${option.type_name || '-'} | ${option.branch_name || '-'} / ${option.location_name || '-'} | Остаток: ${option.qty}`;
};

const isCartridgeLikeText = (value) => {
  const haystack = normalizeText(value);
  return ['картридж', 'катридж', 'тонер', 'cartridge', 'toner'].some((token) => haystack.includes(token));
};

const isCartridgeLikeConsumable = (entry) => {
  const option = toConsumableOption(entry);
  return isCartridgeLikeText(`${option.type_name} ${option.model_name}`);
};

const matchesComponentTypeText = (componentType, value) => {
  const haystack = normalizeText(value);
  const tokens = COMPONENT_MATCH_TOKENS[componentType] || [];
  return tokens.some((token) => haystack.includes(token));
};

const CARTRIDGE_COLOR_MAP = [
  { tokens: ['black', 'черн', 'блэк', ' bk', '-bk', 'blk', ' ч'], color: 'Черный', searchToken: '__color_black__' },
  { tokens: ['cyan', 'голуб', 'циан', 'синий', ' c ', '-c ', ' г'], color: 'Голубой', searchToken: '__color_cyan__' },
  { tokens: ['magenta', 'пурпур', 'маджент', 'красн', ' m ', '-m ', ' п', 'малинов'], color: 'Пурпурный', searchToken: '__color_magenta__' },
  { tokens: ['yellow', 'желт', 'йеллоу', ' y ', '-y ', ' ж'], color: 'Желтый', searchToken: '__color_yellow__' },
];

const groupSupplies = (supplies) => {
  if (!Array.isArray(supplies)) return {};
  const groups = {
    'Картриджи / Тонеры': [],
    'Фотобарабаны': [],
    'Отстойники (Отработка)': [],
    'Печки и Ленты': [],
    'Прочее': []
  };

  supplies.forEach((supply) => {
    const raw = String(supply.name || '').toLowerCase();
    if (raw.includes('toner') || raw.includes('cartridge') || raw.includes('тонер') || raw.includes('картридж') || raw.includes('ink') || raw.includes('чернила')) {
      groups['Картриджи / Тонеры'].push(supply);
    } else if (raw.includes('drum') || raw.includes('барабан') || raw.includes('imaging unit') || raw.includes('фотобарабан')) {
      groups['Фотобарабаны'].push(supply);
    } else if (raw.includes('waste') || raw.includes('отработ') || raw.includes('collector') || raw.includes('бункер')) {
      groups['Отстойники (Отработка)'].push(supply);
    } else if (raw.includes('fuser') || raw.includes('belt') || raw.includes('transfer') || raw.includes('ремень') || raw.includes('лента') || raw.includes('печк')) {
      groups['Печки и Ленты'].push(supply);
    } else {
      groups['Прочее'].push(supply);
    }
  });

  return groups;
};

const tokenizeForMatch = (value) => {
  const normalized = normalizeText(value);
  const rawLower = String(value || '').toLowerCase();
  if (!normalized) return [];

  const tokens = [];
  const rawWords = rawLower.split(/\s+/).filter(Boolean);

  rawWords.forEach((w) => {
    const stripped = w.replace(/[^a-z0-9а-яё]/gi, '');
    if (stripped.length >= 3) {
      tokens.push(stripped);
    }
  });

  for (let i = 0; i < rawWords.length - 1; i++) {
    const pair = rawWords[i] + rawWords[i + 1];
    const stripped = pair.replace(/[^a-z0-9а-яё]/gi, '');
    if (stripped.length >= 4) {
      tokens.push(stripped);
    }
  }

  for (let i = 0; i < rawWords.length - 2; i++) {
    const trip = rawWords[i] + rawWords[i + 1] + rawWords[i + 2];
    const stripped = trip.replace(/[^a-z0-9а-яё]/gi, '');
    if (stripped.length >= 4) {
      tokens.push(stripped);
    }
  }

  normalized
    .split(/[^a-z0-9а-яё-]+/i)
    .forEach((token) => {
      const t = token.trim();
      if (t.length >= 3) {
        tokens.push(t);
        const upper = t.toUpperCase();
        if (upper.length >= 5 && /\d/.test(upper)) {
          const base = getBaseArticle(upper);
          if (base) tokens.push(base.toLowerCase());
        }
      }
    });

  CARTRIDGE_COLOR_MAP.forEach((cm) => {
    if (cm.tokens.some((t) => rawLower.includes(t))) {
      tokens.push(cm.searchToken);
    }
  });

  return [...new Set(tokens)];
};

const getBaseArticle = (article) => {
  // Removes standard capacity suffixes (A, X, XC, XD, Y) from the end of part numbers
  const match = article.match(/^([A-Z0-9]+?)(A|X|XC|XD|Y)$/i);
  if (match && match[1].length >= 4) {
    return match[1].toUpperCase();
  }
  return null;
};

const extractArticleTokens = (value) => {
  const normalized = String(value || '').toUpperCase();
  const rawTokens = normalized
    .split(/[^A-ZА-ЯЁ0-9-]+/i)
    .map((token) => token.trim())
    .filter((token) => token.length >= 5 && /\d/.test(token));

  const expandedTokens = [...rawTokens];
  rawTokens.forEach((t) => {
    // Drop hyphens for base parts (e.g. C-EXV54 -> CEXV54)
    const stripped = t.replace(/-/g, '');
    if (stripped !== t && stripped.length >= 5) expandedTokens.push(stripped);

    // Attempt suffix stripping for core part matches (HP W2032A -> W2032)
    const baseT = getBaseArticle(t);
    if (baseT) expandedTokens.push(baseT);
    const baseStripped = getBaseArticle(stripped);
    if (baseStripped) expandedTokens.push(baseStripped);
  });

  return [...new Set(expandedTokens)];
};

const countIntersection = (left, right) => {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length === 0 || right.length === 0) return 0;
  const rightSet = new Set(right);
  return left.reduce((sum, token) => sum + (rightSet.has(token) ? 1 : 0), 0);
};

const normalizeSupplyOption = (supply) => {
  const index = Number(supply?.index);
  const safeIndex = Number.isFinite(index) ? index : 0;
  const name = formatReplacementItemName(supply?.name || `Расходник ${safeIndex || '-'}`);
  const rawPercent = supply?.percent;
  const percent = typeof rawPercent === 'number' ? rawPercent : null;
  return {
    key: `${safeIndex}|${name}`,
    index: safeIndex,
    name,
    percent,
  };
};

const getComponentLabel = (componentType) => {
  const hit = PRINTER_COMPONENT_OPTIONS.find((entry) => entry.value === componentType);
  return hit?.label || componentType || '-';
};

function StatCard({ title, value, helper }) {
  return (
    <Card variant="outlined" sx={{ borderRadius: 1.5, boxShadow: 1 }}>
      <CardContent sx={{ py: 1.5 }}>
        <Typography variant="caption" color="text.secondary">{title}</Typography>
        <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.15 }}>{value}</Typography>
        <Typography variant="caption" color="text.secondary">{helper}</Typography>
      </CardContent>
    </Card>
  );
}

function Mfu() {
  const { hasPermission } = useAuth();
  const canWrite = hasPermission('database.write');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState({ grouped: {}, totals: {}, db_id: '', generated_at: '', debug: {} });
  const [search, setSearch] = useState('');
  const [branchFilter, setBranchFilter] = useState('all');
  const [snmpFilter, setSnmpFilter] = useState('all');
  const [pingFilter, setPingFilter] = useState('all');

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const selectedKeyRef = useRef('');
  const inFlightRef = useRef(false);

  const [workType, setWorkType] = useState('cartridge');
  const [componentType, setComponentType] = useState(PRINTER_COMPONENT_OPTIONS[0].value);
  const [consumablesLoading, setConsumablesLoading] = useState(false);
  const [consumableOptions, setConsumableOptions] = useState([]);
  const [selectedConsumable, setSelectedConsumable] = useState(null);
  const [workSubmitLoading, setWorkSubmitLoading] = useState(false);
  const [workError, setWorkError] = useState('');
  const [workSuccess, setWorkSuccess] = useState('');
  const [monthlyDataByKey, setMonthlyDataByKey] = useState({});
  const [monthlyLoadingKey, setMonthlyLoadingKey] = useState('');
  const [monthlyErrorByKey, setMonthlyErrorByKey] = useState({});
  const [expandedBranches, setExpandedBranches] = useState({});
  const [expandedLocations, setExpandedLocations] = useState({});
  const [monthlyExpanded, setMonthlyExpanded] = useState(true);
  const [cardView, setCardView] = useState(() => {
    const stored = String(localStorage.getItem('mfu_card_view') || '').trim();
    return stored === 'detailed' ? 'detailed' : 'compact';
  });

  const branches = useMemo(
    () => Object.keys(payload.grouped || {}).sort((a, b) => a.localeCompare(b, 'ru')),
    [payload.grouped]
  );

  useEffect(() => {
    localStorage.setItem('mfu_card_view', cardView === 'detailed' ? 'detailed' : 'compact');
  }, [cardView]);

  const reload = useCallback(async ({ withLoader = false } = {}) => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      if (withLoader) setLoading(true);
      const response = await mfuAPI.getDevices({
        period_days: DASHBOARD_PERIOD_DAYS,
        recent_limit: DASHBOARD_RECENT_LIMIT,
        limit: DASHBOARD_LIMIT,
      });
      const nextPayload = {
        grouped: response?.grouped || {},
        totals: response?.totals || {},
        db_id: response?.db_id || '',
        generated_at: response?.generated_at || '',
        debug: response?.debug || {},
      };
      setPayload(nextPayload);
      setError('');

      if (selectedKeyRef.current) {
        const current = flattenGroupedDevices(nextPayload.grouped).find((item) => item?.key === selectedKeyRef.current);
        if (current) {
          setSelectedDevice(current);
        }
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (err?.message || 'Ошибка загрузки страницы МФУ'));
    } finally {
      if (withLoader) setLoading(false);
      inFlightRef.current = false;
    }
  }, []);

  const loadMonthlyPages = useCallback(async (deviceKey, { force = false } = {}) => {
    const key = String(deviceKey || '').trim();
    if (!key) return;
    if (!force && monthlyDataByKey[key]) return;
    try {
      setMonthlyLoadingKey(key);
      setMonthlyErrorByKey((prev) => ({ ...(prev || {}), [key]: '' }));
      const response = await mfuAPI.getMonthlyPages({
        device_key: key,
        months: PAGE_MONTHS,
      });
      setMonthlyDataByKey((prev) => ({ ...(prev || {}), [key]: response || {} }));
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setMonthlyErrorByKey((prev) => ({
        ...(prev || {}),
        [key]: typeof detail === 'string' ? detail : (err?.message || 'Ошибка загрузки статистики страниц'),
      }));
    } finally {
      setMonthlyLoadingKey((current) => (current === key ? '' : current));
    }
  }, [monthlyDataByKey]);

  const loadConsumables = useCallback(async () => {
    setConsumablesLoading(true);
    try {
      const response = await equipmentAPI.lookupConsumables({
        only_positive_qty: true,
        limit: 500,
      });
      const normalized = (Array.isArray(response) ? response : [])
        .map((entry) => toConsumableOption(entry))
        .filter((entry) => entry.id !== null && entry.qty > 0)
        .sort((a, b) => a.model_name.localeCompare(b.model_name, 'ru'));
      setConsumableOptions(normalized);
      setSelectedConsumable((prev) => {
        if (!prev?.id) return null;
        return normalized.find((entry) => entry.id === prev.id) || null;
      });
    } catch (err) {
      console.error('MFU consumables load failed:', err);
      setConsumableOptions([]);
    } finally {
      setConsumablesLoading(false);
    }
  }, []);

  useEffect(() => {
    reload({ withLoader: true });
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') {
        reload();
      }
    }, REFRESH_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        reload();
      }
    };
    const onDatabaseChanged = () => {
      setDrawerOpen(false);
      setSelectedDevice(null);
      selectedKeyRef.current = '';
      setMonthlyDataByKey({});
      setMonthlyErrorByKey({});
      setMonthlyLoadingKey('');
      reload({ withLoader: true });
    };
    const onStorage = (event) => {
      if (event.key === 'selected_database') onDatabaseChanged();
    };

    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('database-changed', onDatabaseChanged);
    window.addEventListener('storage', onStorage);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('database-changed', onDatabaseChanged);
      window.removeEventListener('storage', onStorage);
    };
  }, [reload]);

  useEffect(() => {
    if (drawerOpen && canWrite) {
      loadConsumables();
    }
  }, [drawerOpen, canWrite, loadConsumables]);

  const filteredGrouped = useMemo(() => {
    const needle = normalizeText(search);
    const grouped = {};
    Object.entries(payload.grouped || {}).forEach(([branchName, locations]) => {
      if (branchFilter !== 'all' && branchName !== branchFilter) return;
      const nextLocations = {};
      Object.entries(locations || {}).forEach(([locationName, items]) => {
        const filtered = (items || []).filter((item) => {
          const pingStatus = normalizeText(item?.runtime?.ping?.status || 'unknown');
          if (pingFilter !== 'all' && pingStatus !== pingFilter) return false;

          // SNMP filter
          if (snmpFilter !== 'all') {
            const snmpStatus = normalizeText(item?.runtime?.snmp?.status || '');
            const supplies = item?.runtime?.snmp?.supplies || [];
            const percents = supplies.map((s) => s?.percent).filter((p) => typeof p === 'number' && Number.isFinite(p));
            const minPct = percents.length > 0 ? Math.min(...percents) : (Number.isFinite(Number(item?.runtime?.snmp?.best_percent)) ? Number(item.runtime.snmp.best_percent) : null);
            if (snmpFilter === 'no_data' && snmpStatus !== 'no_data') return false;
            if (snmpFilter === 'error' && snmpStatus !== 'error') return false;
            if (snmpFilter === 'low_toner' && !(typeof minPct === 'number' && minPct < 20)) return false;
          }

          if (!needle) return true;
          const blob = [
            item?.inv_no,
            item?.serial_no,
            item?.hw_serial_no,
            item?.type_name,
            item?.model_name,
            item?.manufacturer,
            item?.ip_address,
            item?.employee_name,
            item?.employee_dept,
            branchName,
            locationName,
          ].map((x) => String(x || '').toLowerCase()).join(' ');
          return blob.includes(needle);
        });
        if (filtered.length > 0) {
          // Sort: low toner first, then offline, then rest
          const sorted = filtered.slice().sort((a, b) => {
            const getMin = (item) => {
              const sp = (item?.runtime?.snmp?.supplies || []).map((s) => s?.percent).filter((p) => typeof p === 'number' && Number.isFinite(p));
              return sp.length > 0 ? Math.min(...sp) : (Number.isFinite(Number(item?.runtime?.snmp?.best_percent)) ? Number(item.runtime.snmp.best_percent) : 999);
            };
            const aMin = getMin(a);
            const bMin = getMin(b);
            const aCrit = aMin < 20 ? 0 : 1;
            const bCrit = bMin < 20 ? 0 : 1;
            if (aCrit !== bCrit) return aCrit - bCrit;
            return aMin - bMin;
          });
          nextLocations[locationName] = sorted;
        }
      });
      if (Object.keys(nextLocations).length > 0) grouped[branchName] = nextLocations;
    });
    return grouped;
  }, [payload.grouped, branchFilter, pingFilter, snmpFilter, search]);

  const filteredDevices = useMemo(() => flattenGroupedDevices(filteredGrouped), [filteredGrouped]);

  const workSupplyCandidates = useMemo(() => {
    const source = Array.isArray(selectedDevice?.runtime?.snmp?.supplies)
      ? selectedDevice.runtime.snmp.supplies
      : [];
    const normalized = source
      .map((entry, index) => {
        const name = formatReplacementItemName(entry?.name || `Расходник ${index + 1}`);
        const percent = Number(entry?.percent);
        return {
          name,
          percent: Number.isFinite(percent) ? percent : null,
          tokens: tokenizeForMatch(name),
          articles: extractArticleTokens(name),
        };
      })
      .filter((entry) => entry.name && entry.name !== '-');

    const scoped = workType === 'cartridge'
      ? normalized.filter((entry) => isCartridgeLikeText(entry.name))
      : normalized.filter((entry) => matchesComponentTypeText(componentType, entry.name));
    const result = scoped.length > 0 ? scoped : normalized;
    return result.slice().sort((a, b) => {
      const aHas = Number.isFinite(a.percent);
      const bHas = Number.isFinite(b.percent);
      if (aHas && bHas) return a.percent - b.percent;
      if (aHas) return -1;
      if (bHas) return 1;
      return a.name.localeCompare(b.name, 'ru');
    });
  }, [selectedDevice, workType, componentType]);

  const workConsumableOptions = useMemo(() => {
    const source = Array.isArray(consumableOptions) ? consumableOptions : [];
    const filteredByType = workType === 'cartridge'
      ? source.filter((entry) => isCartridgeLikeConsumable(entry))
      : source.filter((entry) => !isCartridgeLikeConsumable(entry));
    const scoped = filteredByType.length > 0 ? filteredByType : source;
    const deviceBranch = normalizeText(selectedDevice?.branch_name);
    const deviceLocation = normalizeText(selectedDevice?.location_name);

    return scoped
      .map((entry) => {
        const option = toConsumableOption(entry);
        const optionText = formatReplacementItemName(`${option.model_name || ''} ${option.type_name || ''}`);
        const optionTokens = tokenizeForMatch(optionText);
        const optionArticles = extractArticleTokens(optionText);

        let score = 0;
        if (workType === 'cartridge' && isCartridgeLikeText(optionText)) score += 25;
        if (workType === 'component' && matchesComponentTypeText(componentType, optionText)) score += 35;

        workSupplyCandidates.forEach((supply, index) => {
          const articleOverlap = countIntersection(optionArticles, supply.articles);
          const tokenOverlap = countIntersection(optionTokens, supply.tokens);

          if (articleOverlap > 0) {
            score += (index === 0 ? 120 : 80) + (articleOverlap * 10);
          }
          if (tokenOverlap > 0) {
            score += Math.min(tokenOverlap * (index === 0 ? 16 : 10), index === 0 ? 40 : 24);
          }
        });

        return { ...option, _matchScore: score };
      })
      .sort((a, b) => {
        const aIsLocalBranch = deviceBranch && normalizeText(a.branch_name) === deviceBranch;
        const bIsLocalBranch = deviceBranch && normalizeText(b.branch_name) === deviceBranch;
        const aIsLocalLoc = deviceLocation && normalizeText(a.location_name) === deviceLocation;
        const bIsLocalLoc = deviceLocation && normalizeText(b.location_name) === deviceLocation;

        const scoreDiff = b._matchScore - a._matchScore;

        // Если разница в качестве текстового совпадения небольшая (< 50 баллов, это 1-2 токена),
        // отдаем жесткий приоритет тому картриджу, который лежит на том же складе/в том же филиале.
        if (Math.abs(scoreDiff) < 50) {
          if (aIsLocalLoc !== bIsLocalLoc) return aIsLocalLoc ? -1 : 1;
          if (aIsLocalBranch !== bIsLocalBranch) return aIsLocalBranch ? -1 : 1;
        }

        if (b._matchScore !== a._matchScore) return b._matchScore - a._matchScore;
        return a.model_name.localeCompare(b.model_name, 'ru');
      });
  }, [consumableOptions, workType, componentType, selectedDevice, workSupplyCandidates]);

  const recommendedConsumable = useMemo(() => {
    const first = workConsumableOptions[0];
    if (!first) return null;
    return Number(first._matchScore) > 0 ? first : null;
  }, [workConsumableOptions]);

  const recommendedWorkHint = useMemo(() => {
    const topSupply = workSupplyCandidates[0];
    const topSupplyText = topSupply
      ? `К замене по SNMP: ${topSupply.name}${Number.isFinite(topSupply.percent) ? ` (${topSupply.percent}%)` : ''}.`
      : '';
    const topConsumable = recommendedConsumable
      ? `Рекомендуем списать: ${formatReplacementItemName(recommendedConsumable.model_name || recommendedConsumable.type_name || '-')}.`
      : '';
    return [topSupplyText, topConsumable].filter(Boolean).join(' ');
  }, [workSupplyCandidates, recommendedConsumable]);

  const selectedDeviceKey = String(selectedDevice?.key || '').trim();
  const selectedMonthly = selectedDeviceKey ? monthlyDataByKey[selectedDeviceKey] : null;
  const selectedMonthlyRows = Array.isArray(selectedMonthly?.months) ? selectedMonthly.months : [];
  const selectedMonthlyError = selectedDeviceKey ? (monthlyErrorByKey[selectedDeviceKey] || '') : '';
  const selectedMonthlyLoading = selectedDeviceKey ? monthlyLoadingKey === selectedDeviceKey : false;
  const runtimePageTotal = Number(selectedDevice?.runtime?.snmp?.page_total);
  const selectedCurrentTotalPages = Number.isFinite(Number(selectedMonthly?.current_total_pages))
    ? Number(selectedMonthly.current_total_pages)
    : (Number.isFinite(runtimePageTotal) ? runtimePageTotal : null);
  const selectedCurrentPagesCheckedAt = selectedMonthly?.current_checked_at
    || selectedDevice?.runtime?.snmp?.page_checked_at
    || null;
  const selectedTrackingStartDate = selectedMonthly?.tracking_start_date || null;

  const isBranchExpanded = useCallback(
    (branchName) => expandedBranches[String(branchName || '').trim()] === true,
    [expandedBranches]
  );
  const isLocationExpanded = useCallback(
    (locationKey) => expandedLocations[String(locationKey || '').trim()] !== false,
    [expandedLocations]
  );

  const toggleBranch = useCallback((branchName) => {
    const key = String(branchName || '').trim();
    if (!key) return;
    setExpandedBranches((prev) => ({ ...(prev || {}), [key]: !isBranchExpanded(key) }));
  }, [isBranchExpanded]);

  const toggleLocation = useCallback((locationKey) => {
    const key = String(locationKey || '').trim();
    if (!key) return;
    setExpandedLocations((prev) => ({ ...(prev || {}), [key]: !isLocationExpanded(key) }));
  }, [isLocationExpanded]);

  const handleOpenDevice = useCallback((device) => {
    selectedKeyRef.current = String(device?.key || '');
    setSelectedDevice(device);
    setDrawerOpen(true);
    setWorkError('');
    setWorkSuccess('');
    const nextKey = String(device?.key || '').trim();
    if (nextKey) {
      loadMonthlyPages(nextKey);
    }
  }, [loadMonthlyPages]);

  // loadMonthlyPages is already called in handleOpenDevice — no extra effect needed.

  const handleSubmitWork = useCallback(async () => {
    setWorkError('');
    setWorkSuccess('');

    if (!canWrite) {
      setWorkError('Недостаточно прав для записи работ.');
      return;
    }
    if (!selectedDevice) {
      setWorkError('Не выбрано устройство.');
      return;
    }
    if (!selectedConsumable?.id) {
      setWorkError('Выберите расходник для списания.');
      return;
    }

    const serialNumber = String(selectedDevice.serial_no || selectedDevice.hw_serial_no || '').trim();
    const invNo = String(selectedDevice.inv_no || '').trim();
    const branch = String(selectedDevice.branch_name || '').trim();
    const location = String(selectedDevice.location_name || '').trim();
    const employee = String(selectedDevice.employee_name || 'Не указан').trim();
    const modelName = String(selectedDevice.model_name || '').trim();
    const manufacturer = String(selectedDevice.manufacturer || '').trim();

    if (!serialNumber) {
      setWorkError('У устройства не заполнен серийный номер.');
      return;
    }
    if (!branch || !location) {
      setWorkError('У устройства не заполнены филиал или локация.');
      return;
    }

    setWorkSubmitLoading(true);
    try {
      await equipmentAPI.consumeConsumable({
        item_id: selectedConsumable.id,
        qty: 1,
        reason: workType,
      });

      const dbName = String(payload.db_id || '').trim() || undefined;
      const commonAdditional = {
        consumable_item_id: selectedConsumable.id,
        consumable_inv_no: selectedConsumable.inv_no || '',
        consumable_model: formatReplacementItemName(selectedConsumable.model_name || ''),
        consumable_branch: selectedConsumable.branch_name || '',
        consumable_location: selectedConsumable.location_name || '',
      };
      const normalizedConsumableModel = formatReplacementItemName(
        selectedConsumable.model_name || selectedConsumable.type_name || ''
      );

      // Derive cartridge color from the consumable name using the global map
      const consumableNameLower = (normalizedConsumableModel || selectedConsumable.type_name || '').toLowerCase();
      const detectedColor = CARTRIDGE_COLOR_MAP.find((entry) => entry.tokens.some((t) => consumableNameLower.includes(t)))?.color
        || 'Универсальный';

      if (workType === 'cartridge') {
        await jsonAPI.addCartridgeReplacement({
          printer_model: modelName || 'Не указано',
          cartridge_color: detectedColor,
          component_type: 'cartridge',
          component_color: detectedColor,
          cartridge_model: normalizedConsumableModel || undefined,
          detection_source: 'sql-consumables',
          branch,
          location,
          serial_number: serialNumber,
          employee,
          inv_no: invNo || undefined,
          db_name: dbName,
          equipment_id: toNumberOrNull(selectedDevice.id),
          current_description: '',
          hw_serial_no: String(selectedDevice.hw_serial_no || ''),
          model_name: modelName,
          manufacturer,
          additional_data: commonAdditional,
        });
      } else {
        const resolvedComponentModel = String(normalizedConsumableModel || '').trim();
        if (!resolvedComponentModel) {
          throw new Error('Не удалось определить модель комплектующей из выбранного расходника.');
        }
        await jsonAPI.addComponentReplacement({
          serial_number: serialNumber,
          employee,
          component_type: componentType,
          component_name: getComponentLabel(componentType),
          component_model: resolvedComponentModel,
          equipment_kind: 'printer',
          branch,
          location,
          inv_no: invNo || undefined,
          db_name: dbName,
          equipment_id: toNumberOrNull(selectedDevice.id),
          current_description: '',
          hw_serial_no: String(selectedDevice.hw_serial_no || ''),
          model_name: modelName,
          manufacturer,
          detection_source: 'sql-consumables',
          additional_data: commonAdditional,
        });
      }

      setWorkSuccess('Работа записана, расходник списан.');
      setSelectedConsumable(null);
      await Promise.all([reload(), loadConsumables()]);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string') {
        setWorkError(detail);
      } else if (Array.isArray(detail)) {
        setWorkError(detail.map((entry) => String(entry?.msg || '')).filter(Boolean).join('; '));
      } else {
        setWorkError(err?.message || 'Не удалось записать работу.');
      }
    } finally {
      setWorkSubmitLoading(false);
    }
  }, [
    canWrite,
    selectedDevice,
    selectedConsumable,
    workType,
    componentType,
    payload.db_id,
    reload,
    loadConsumables,
  ]);

  const snmpFresh = toCount(payload?.totals?.snmp_fresh);
  const snmpCachedActive = toCount(payload?.totals?.snmp_cached_active);
  const snmpError = toCount(payload?.totals?.snmp_error);
  const snmpUnknown = toCount(payload?.totals?.snmp_unknown);
  const snmpTtlSec = toCount(payload?.totals?.snmp_active_ttl_sec);
  const snmpTtlMinutes = snmpTtlSec > 0 ? Math.max(1, Math.round(snmpTtlSec / 60)) : 60;
  const snmpMetricHelper = `свежие: ${snmpFresh}, кэш: ${snmpCachedActive}, TTL: ${snmpTtlMinutes} мин`;
  const snmpDetailHelper = `ошибки: ${snmpError}, неизвестно: ${snmpUnknown}`;

  return (
    <MainLayout>
      <Box sx={{ width: '100%', pb: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <PrintIcon color="primary" />
            <Typography variant="h5" sx={{ fontWeight: 700 }}>МФУ, принтеры и плоттеры</Typography>
            <Chip size="small" variant="outlined" label={`БД: ${payload.db_id || '-'}`} />
          </Box>
          <Tooltip title="Обновить">
            <span>
              <IconButton onClick={() => reload()} disabled={loading} color="primary">
                <RefreshIcon />
              </IconButton>
            </span>
          </Tooltip>
        </Box>

        {payload.generated_at ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, mt: -1 }}>
            Обновлено: {formatDateTime(payload.generated_at)}
          </Typography>
        ) : null}

        {loading && <LinearProgress sx={{ mb: 2 }} />}
        {error ? <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert> : null}

        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Всего устройств" value={Number(payload?.totals?.devices || 0)} helper="по выбранной БД" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="В сети" value={Number(payload?.totals?.online || 0)} helper="ping отвечает" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Оффлайн" value={Number(payload?.totals?.offline || 0)} helper="ping не отвечает" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard
              title="SNMP активен"
              value={toCount(payload?.totals?.snmp_ok)}
              helper={snmpMetricHelper}
            />
          </Grid>
        </Grid>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.25 }}>
          {snmpDetailHelper}
        </Typography>

        {!loading && !error && toCount(payload?.totals?.devices) === 0 ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            API вернул 0 устройств МФУ. Это не связано со SNMP. Проверьте выбранную БД и фильтрацию МФУ на бэкенде.
          </Alert>
        ) : null}

        <Card variant="outlined" sx={{ p: 1.5, mb: 2 }}>
          <Grid container spacing={1.5}>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                size="small"
                label="Поиск"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Модель, инв. номер, серийный, IP, сотрудник"
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel id="mfu-branch-label">Филиал</InputLabel>
                <Select
                  labelId="mfu-branch-label"
                  value={branchFilter}
                  label="Филиал"
                  onChange={(event) => setBranchFilter(event.target.value)}
                >
                  <MenuItem value="all">Все</MenuItem>
                  {branches.map((branch) => (
                    <MenuItem key={branch} value={branch}>{branch}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel id="mfu-ping-label">Сеть</InputLabel>
                <Select
                  labelId="mfu-ping-label"
                  value={pingFilter}
                  label="Сеть"
                  onChange={(event) => setPingFilter(event.target.value)}
                >
                  <MenuItem value="all">Все</MenuItem>
                  <MenuItem value="online">В сети</MenuItem>
                  <MenuItem value="offline">Оффлайн</MenuItem>
                  <MenuItem value="unknown">Неизвестно</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel id="mfu-snmp-label">SNMP</InputLabel>
                <Select
                  labelId="mfu-snmp-label"
                  value={snmpFilter}
                  label="SNMP"
                  onChange={(event) => setSnmpFilter(event.target.value)}
                >
                  <MenuItem value="all">Все</MenuItem>
                  <MenuItem value="low_toner">🔴 Тонер &lt; 20%</MenuItem>
                  <MenuItem value="no_data">Нет данных</MenuItem>
                  <MenuItem value="error">Ошибка SNMP</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel id="mfu-card-view-label">Вид</InputLabel>
                <Select
                  labelId="mfu-card-view-label"
                  value={cardView}
                  label="Вид"
                  onChange={(event) => setCardView(event.target.value === 'detailed' ? 'detailed' : 'compact')}
                >
                  <MenuItem value="compact">Компактно</MenuItem>
                  <MenuItem value="detailed">Подробно</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Card>

        {!loading && filteredDevices.length === 0 ? (
          <Alert severity="info">По выбранным фильтрам устройства не найдены.</Alert>
        ) : null}

        {Object.entries(filteredGrouped).map(([branchName, locations]) => {
          const sortedLocations = Object.entries(locations || {}).sort((a, b) => String(a[0]).localeCompare(String(b[0]), 'ru'));
          const branchTotal = sortedLocations.reduce((acc, [, items]) => acc + (Array.isArray(items) ? items.length : 0), 0);
          return (
            <Accordion
              key={branchName}
              expanded={isBranchExpanded(branchName)}
              onChange={() => toggleBranch(branchName)}
              sx={{ mb: 1 }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography sx={{ fontWeight: 700 }}>{branchName}</Typography>
                  <Chip size="small" label={`${branchTotal} устройств`} />
                  <Chip size="small" variant="outlined" label={`${sortedLocations.length} локаций`} />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1.1}>
                  {sortedLocations.map(([locationName, locationItems]) => {
                    const locationKey = `${branchName}::${locationName}`;
                    const locationRows = Array.isArray(locationItems) ? locationItems : [];
                    const onlineCount = locationRows.filter((item) => normalizeText(item?.runtime?.ping?.status) === 'online').length;
                    const offlineCount = locationRows.filter((item) => normalizeText(item?.runtime?.ping?.status) === 'offline').length;
                    return (
                      <Card key={locationKey} variant="outlined" sx={{ p: 1, borderRadius: 1.5, boxShadow: 1 }}>
                        <Box
                          role="button"
                          onClick={() => toggleLocation(locationKey)}
                          sx={{
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 1,
                            mb: isLocationExpanded(locationKey) ? 0.9 : 0.1,
                          }}
                        >
                          <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                              {locationName}
                            </Typography>
                            <Chip size="small" label={`${locationRows.length} шт`} />
                            <Chip size="small" color="success" variant="outlined" label={`Online: ${onlineCount}`} />
                            <Chip size="small" color="error" variant="outlined" label={`Offline: ${offlineCount}`} />
                          </Stack>
                          <ExpandMoreIcon
                            sx={{
                              transition: 'transform 0.2s ease',
                              transform: isLocationExpanded(locationKey) ? 'rotate(180deg)' : 'rotate(0deg)',
                            }}
                          />
                        </Box>
                        {isLocationExpanded(locationKey) ? (
                          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 1.2 }}>
                            {locationRows.map((device) => {
                              const ping = getPingMeta(device?.runtime?.ping?.status);
                              const supplies = (device?.runtime?.snmp?.supplies || []).map((entry) => normalizeSupplyOption(entry));
                              const knownPercents = supplies
                                .map((entry) => entry.percent)
                                .filter((entry) => Number.isFinite(entry));
                              const minSupplyPercent = knownPercents.length > 0
                                ? Math.min(...knownPercents)
                                : (Number.isFinite(device?.runtime?.snmp?.best_percent) ? Number(device.runtime.snmp.best_percent) : null);
                              const suppliesCount = supplies.length;
                              const pagesTotal = Number(device?.runtime?.snmp?.page_total);
                              const isDetailed = cardView === 'detailed';
                              return (
                                <Card
                                  key={device?.key || `${device?.inv_no || ''}-${device?.serial_no || ''}`}
                                  variant="outlined"
                                  onClick={() => handleOpenDevice(device)}
                                  sx={{
                                    p: 1,
                                    cursor: 'pointer',
                                    borderRadius: 1.5,
                                    boxShadow: 1,
                                    transition: 'border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease',
                                    '&:hover': {
                                      borderColor: 'primary.main',
                                      boxShadow: 2,
                                      transform: 'translateY(-1px)',
                                    },
                                  }}
                                >
                                  <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={0.8} sx={{ mb: 0.5 }}>
                                    <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                                      {device?.model_name || '-'}
                                    </Typography>
                                    <Stack direction="row" spacing={0.5} alignItems="center">
                                      {Number.isFinite(minSupplyPercent) && minSupplyPercent < 20 ? (
                                        <Chip size="small" color="error" label="Мало!" sx={{ fontSize: '0.6rem', height: 18 }} />
                                      ) : null}
                                      <Chip size="small" color={ping.color} label={ping.label} />
                                    </Stack>
                                  </Stack>
                                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.6 }}>
                                    {device?.type_name || '-'}
                                  </Typography>
                                  <Box sx={{ mb: 0.7 }}>
                                    <LinearProgress
                                      variant="determinate"
                                      value={Number.isFinite(minSupplyPercent) ? minSupplyPercent : 0}
                                      color={getSupplySeverity(minSupplyPercent)}
                                      sx={{
                                        height: 6,
                                        borderRadius: 99,
                                        backgroundColor: 'action.hover',
                                        opacity: Number.isFinite(minSupplyPercent) ? 1 : 0.35,
                                      }}
                                    />
                                    <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.25 }}>
                                      <Typography variant="caption" color="text.secondary">
                                        Мин. тонер: {Number.isFinite(minSupplyPercent) ? `${minSupplyPercent}%` : 'N/A'}
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary">
                                        Расходники: {suppliesCount || 0}
                                      </Typography>
                                    </Stack>
                                  </Box>
                                  <Typography variant="caption" sx={{ display: 'block' }}>Инв.: <b>{device?.inv_no || '-'}</b></Typography>
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="caption">IP: <b>{device?.ip_address || '-'}</b></Typography>
                                    {device?.ip_address && (
                                      <Tooltip title="Открыть веб-интерфейс">
                                        <IconButton size="small" component="a" href={`http://${device.ip_address}`} target="_blank" rel="noopener noreferrer" sx={{ p: 0.2 }}>
                                          <OpenInNewIcon sx={{ fontSize: '0.9rem' }} color="primary" />
                                        </IconButton>
                                      </Tooltip>
                                    )}
                                  </Box>
                                  <Typography variant="caption" sx={{ display: 'block' }}>
                                    Страниц: <b>{Number.isFinite(pagesTotal) ? pagesTotal : '-'}</b>
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                    Работ: {Number(device?.maintenance?.total_operations || 0)}
                                  </Typography>
                                  {isDetailed ? (
                                    <>
                                      <Typography variant="caption" sx={{ display: 'block' }}>
                                        Серийный: <b>{device?.serial_no || device?.hw_serial_no || '-'}</b>
                                      </Typography>
                                      <Typography variant="caption" sx={{ display: 'block' }}>
                                        Отдел: <b>{device?.employee_dept || '-'}</b>
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                        Последняя работа: {formatDateTime(device?.maintenance?.last_operation_at)}
                                      </Typography>
                                    </>
                                  ) : null}
                                </Card>
                              );
                            })}
                          </Box>
                        ) : null}
                      </Card>
                    );
                  })}
                </Stack>
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Box>

      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <Box sx={{ width: { xs: 360, sm: 480 }, p: 2 }}>
          {selectedDevice ? (
            <>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>{selectedDevice?.model_name || '-'}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{selectedDevice?.type_name || '-'}</Typography>

              <Card variant="outlined" sx={{ p: 1.2, mb: 1.5 }}>
                <Stack spacing={0.5}>
                  <Typography variant="body2"><b>Инв. номер:</b> {selectedDevice?.inv_no || '-'}</Typography>
                  <Typography variant="body2"><b>Серийный:</b> {selectedDevice?.serial_no || '-'}</Typography>
                  <Typography variant="body2"><b>HW серийный:</b> {selectedDevice?.hw_serial_no || '-'}</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Typography variant="body2"><b>IP:</b> {selectedDevice?.ip_address || '-'}</Typography>
                    {selectedDevice?.ip_address && (
                      <Tooltip title="Открыть веб-интерфейс">
                        <IconButton size="small" component="a" href={`http://${selectedDevice.ip_address}`} target="_blank" rel="noopener noreferrer" sx={{ p: 0.2 }}>
                          <OpenInNewIcon sx={{ fontSize: '1.1rem' }} color="primary" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                  <Typography variant="body2"><b>MAC:</b> {selectedDevice?.mac_address || '-'}</Typography>
                  <Typography variant="body2"><b>Филиал:</b> {selectedDevice?.branch_name || '-'}</Typography>
                  <Typography variant="body2"><b>Локация:</b> {selectedDevice?.location_name || '-'}</Typography>
                  <Typography variant="body2"><b>Сотрудник:</b> {selectedDevice?.employee_name || '-'}</Typography>
                  <Typography variant="body2"><b>Отдел:</b> {selectedDevice?.employee_dept || '-'}</Typography>
                </Stack>
              </Card>

              <Card variant="outlined" sx={{ p: 1.2, mb: 1.5 }}>
                <Stack spacing={0.7}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <RouterIcon fontSize="small" />
                    <Typography variant="subtitle2">Ping</Typography>
                    <Chip size="small" {...getPingMeta(selectedDevice?.runtime?.ping?.status)} />
                  </Box>
                  <Typography variant="caption" color="text.secondary">Последняя проверка: {formatDateTime(selectedDevice?.runtime?.ping?.checked_at)}</Typography>
                  <Typography variant="caption" color="text.secondary">Последний online: {formatDateTime(selectedDevice?.runtime?.ping?.last_online_at)}</Typography>
                  <Typography variant="caption" color="text.secondary">Задержка: {selectedDevice?.runtime?.ping?.latency_ms ?? '-'} ms</Typography>
                </Stack>
              </Card>

              <Card variant="outlined" sx={{ p: 1.2, mb: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.8 }}>
                  <RouterIcon fontSize="small" />
                  <Typography variant="subtitle2">SNMP расходники</Typography>
                  <Chip size="small" variant="outlined" label={String(selectedDevice?.runtime?.snmp?.status || 'unknown')} />
                </Box>
                <Stack spacing={0.3} sx={{ mb: 0.8 }}>
                  <Typography variant="caption" color="text.secondary">
                    Последняя проверка: {formatDateTime(selectedDevice?.runtime?.snmp?.checked_at)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Последний успешный опрос: {formatDateTime(selectedDevice?.runtime?.snmp?.last_success_at)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Community: {selectedDevice?.runtime?.snmp?.used_community || '-'}; Версия: {selectedDevice?.runtime?.snmp?.version || '-'}
                  </Typography>
                  {selectedDevice?.runtime?.snmp?.error ? (
                    <Typography variant="caption" color="warning.main">
                      Ошибка SNMP: {String(selectedDevice.runtime.snmp.error)}
                    </Typography>
                  ) : null}
                  {String(selectedDevice?.runtime?.snmp?.status || '').toLowerCase() === 'error'
                    && selectedDevice?.runtime?.snmp?.last_success_at ? (
                    <Typography variant="caption" color="info.main">
                      Временная ошибка SNMP. Показаны последние валидные данные.
                    </Typography>
                  ) : null}
                </Stack>
                {((selectedDevice?.runtime?.snmp?.supplies || []).length === 0) ? (
                  <Typography variant="caption" color={String(selectedDevice?.runtime?.snmp?.status || '').toLowerCase() === 'error' ? 'warning.main' : 'text.secondary'}>
                    {String(selectedDevice?.runtime?.snmp?.status || '').toLowerCase() === 'error'
                      ? 'Ошибка SNMP-соединения. Проверьте community и доступность порта 161.'
                      : 'Данных о расходниках нет — принтер не вернул таблицу supplies. Проверьте настройки SNMP в custom_snmp.json.'}
                  </Typography>
                ) : (
                  <Box sx={{ mt: 1 }}>
                    {Object.entries(groupSupplies(selectedDevice?.runtime?.snmp?.supplies)).map(([groupName, groupSupplies]) => {
                      if (groupSupplies.length === 0) return null;
                      return (
                        <Box key={`group-${groupName}`} sx={{ mb: 1.5 }}>
                          <Typography variant="caption" sx={{ fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            {groupName}
                          </Typography>
                          <List dense disablePadding>
                            {groupSupplies.map((supply) => (
                              <ListItem key={`${selectedDevice?.key}-s-${supply?.index || supply?.name}`} disableGutters sx={{ py: 0.25 }}>
                                <ListItemText
                                  primary={formatReplacementItemName(supply?.name || `Расходник ${supply?.index}`)}
                                  secondary={
                                    (supply?.level < 0 || supply?.max < 0)
                                      ? `Уровень: ${(supply?.level === -3 || supply?.level === -2) ? 'OK' : 'Неизвестно'}; ${typeof supply?.percent === 'number' ? `${supply.percent}%` : 'N/A'}`
                                      : `Уровень: ${supply?.level ?? '-'} / ${supply?.max ?? '-'}; ${typeof supply?.percent === 'number' ? `${supply.percent}%` : 'N/A'}`
                                  }
                                  primaryTypographyProps={{ variant: 'body2' }}
                                  secondaryTypographyProps={{ variant: 'caption', color: (typeof supply?.percent === 'number' && supply.percent < 20) ? 'error.main' : 'text.secondary' }}
                                />
                              </ListItem>
                            ))}
                          </List>
                        </Box>
                      );
                    })}
                  </Box>
                )}
              </Card>

              {selectedDevice?.runtime?.snmp?.device_info ? (
                <Card variant="outlined" sx={{ p: 1.2, mb: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.8 }}>
                    <PrintIcon fontSize="small" />
                    <Typography variant="subtitle2">Информация SNMP</Typography>
                  </Box>
                  <Stack spacing={0.3}>
                    {selectedDevice.runtime.snmp.device_info.serial_number ? (
                      <Typography variant="body2"><b>Серийный №:</b> {selectedDevice.runtime.snmp.device_info.serial_number}</Typography>
                    ) : null}
                    {selectedDevice.runtime.snmp.device_info.device_model ? (
                      <Typography variant="body2"><b>Модель (SNMP):</b> {selectedDevice.runtime.snmp.device_info.device_model}</Typography>
                    ) : null}
                    {selectedDevice.runtime.snmp.device_info.sys_name ? (
                      <Typography variant="body2"><b>Имя устройства:</b> {selectedDevice.runtime.snmp.device_info.sys_name}</Typography>
                    ) : null}
                    {selectedDevice.runtime.snmp.device_info.sys_descr ? (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        <b>Описание:</b> {selectedDevice.runtime.snmp.device_info.sys_descr}
                      </Typography>
                    ) : null}
                    {selectedDevice.runtime.snmp.device_info.sys_location ? (
                      <Typography variant="body2"><b>Расположение:</b> {selectedDevice.runtime.snmp.device_info.sys_location}</Typography>
                    ) : null}
                    {typeof selectedDevice.runtime.snmp.device_info.uptime_seconds === 'number' ? (
                      <Typography variant="body2">
                        <b>Uptime:</b>{' '}
                        {(() => {
                          const totalSec = selectedDevice.runtime.snmp.device_info.uptime_seconds;
                          const d = Math.floor(totalSec / 86400);
                          const h = Math.floor((totalSec % 86400) / 3600);
                          const m = Math.floor((totalSec % 3600) / 60);
                          return `${d}д ${h}ч ${m}м`;
                        })()}
                      </Typography>
                    ) : null}
                  </Stack>
                </Card>
              ) : null}

              {selectedDevice?.runtime?.snmp?.custom_metrics && Object.keys(selectedDevice.runtime.snmp.custom_metrics).length > 0 ? (
                <Card variant="outlined" sx={{ p: 1.2, mb: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.8 }}>
                    <PrintIcon fontSize="small" />
                    <Typography variant="subtitle2">Дополнительные датчики</Typography>
                  </Box>
                  <Stack spacing={0.3}>
                    {Object.entries(selectedDevice.runtime.snmp.custom_metrics).map(([metricName, metricValue]) => (
                      <Typography key={`custom-metric-${metricName}`} variant="body2">
                        <b>{metricName}:</b> {metricValue}
                      </Typography>
                    ))}
                  </Stack>
                </Card>
              ) : null}

              {(selectedDevice?.runtime?.snmp?.trays || []).length > 0 ? (
                <Card variant="outlined" sx={{ p: 1.2, mb: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.8 }}>
                    <PrintIcon fontSize="small" />
                    <Typography variant="subtitle2">Лотки бумаги</Typography>
                  </Box>
                  <List dense disablePadding>
                    {(selectedDevice?.runtime?.snmp?.trays || []).map((tray) => (
                      <ListItem key={`tray-${tray?.index}`} disableGutters sx={{ py: 0.25, flexDirection: 'column', alignItems: 'stretch' }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {tray?.name || `Лоток ${tray?.index}`}
                          </Typography>
                          {typeof tray?.percent === 'number' ? (
                            <Chip size="small" label={`${tray.percent}%`} color={tray.percent < 20 ? 'error' : tray.percent < 50 ? 'warning' : 'success'} />
                          ) : null}
                        </Stack>
                        {typeof tray?.percent === 'number' ? (
                          <LinearProgress
                            variant="determinate"
                            value={tray.percent}
                            color={tray.percent < 20 ? 'error' : tray.percent < 50 ? 'warning' : 'success'}
                            sx={{ height: 4, borderRadius: 99, mt: 0.3 }}
                          />
                        ) : null}
                        <Typography variant="caption" color="text.secondary">
                          {tray?.media_name ? `Бумага: ${tray.media_name}; ` : ''}
                          Уровень: {tray?.current_level ?? '-'} / {tray?.max_capacity ?? '-'}
                        </Typography>
                      </ListItem>
                    ))}
                  </List>
                </Card>
              ) : null}

              <Card variant="outlined" sx={{ p: 0.2, mb: 1.5 }}>
                <Accordion
                  expanded={monthlyExpanded}
                  onChange={(_, expanded) => setMonthlyExpanded(Boolean(expanded))}
                  disableGutters
                  elevation={0}
                  sx={{ '&:before': { display: 'none' } }}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 46 }}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Печать по месяцам</Typography>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`Текущий: ${Number.isFinite(selectedCurrentTotalPages) ? selectedCurrentTotalPages : '-'}`}
                      />
                    </Stack>
                  </AccordionSummary>
                  <AccordionDetails sx={{ pt: 0.4 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 0.8 }}>
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Дата счетчика: {formatDateTime(selectedCurrentPagesCheckedAt)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Начало учета: {formatDateOnly(selectedTrackingStartDate)}
                        </Typography>
                      </Box>
                      <Button
                        size="small"
                        onClick={(event) => {
                          event.stopPropagation();
                          if (selectedDeviceKey) loadMonthlyPages(selectedDeviceKey, { force: true });
                        }}
                        disabled={!selectedDeviceKey || selectedMonthlyLoading}
                      >
                        Обновить
                      </Button>
                    </Box>
                    {selectedMonthlyLoading ? (
                      <LinearProgress sx={{ mb: 0.8 }} />
                    ) : null}
                    {selectedMonthlyError ? (
                      <Alert severity="warning" sx={{ mb: 0.8 }}>{selectedMonthlyError}</Alert>
                    ) : null}
                    {selectedMonthlyRows.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        Пока нет накопленных суточных срезов для расчета помесячной печати.
                      </Typography>
                    ) : (
                      <List dense disablePadding>
                        {selectedMonthlyRows.map((entry) => (
                          <ListItem key={`${selectedDeviceKey}-month-${entry?.month}`} disableGutters sx={{ py: 0.35 }}>
                            <ListItemText
                              primary={`${formatMonthLabel(entry?.month)}: ${Number(entry?.printed_pages || 0)} стр.`}
                              secondary={entry?.reset_detected
                                ? 'Обнаружен сброс счетчика'
                                : `Счетчик: ${entry?.start_counter ?? '-'} → ${entry?.end_counter ?? '-'}`}
                              primaryTypographyProps={{ variant: 'body2' }}
                              secondaryTypographyProps={{ variant: 'caption' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    )}
                  </AccordionDetails>
                </Accordion>
              </Card>

              <Divider sx={{ my: 1.2 }} />
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.6 }}>
                <BuildIcon fontSize="small" />
                <Typography variant="subtitle2">История работ</Typography>
                <Chip size="small" label={Number(selectedDevice?.maintenance?.total_operations || 0)} />
              </Box>
              {((selectedDevice?.maintenance?.recent || []).length === 0) ? (
                <Typography variant="caption" color="text.secondary">
                  По устройству нет зарегистрированных работ.
                </Typography>
              ) : (
                <List dense disablePadding>
                  {(selectedDevice?.maintenance?.recent || []).map((entry, index) => (
                    <ListItem key={`${selectedDevice?.key}-h-${index}`} disableGutters sx={{ py: 0.5 }}>
                      <ListItemText
                        primary={`${formatReplacementItemName(entry?.component_type || '-')}: ${formatReplacementItemName(entry?.replacement_item || '-')}`}
                        secondary={`${formatDateTime(entry?.timestamp)}; ${entry?.employee || 'Без сотрудника'}`}
                        primaryTypographyProps={{ variant: 'body2' }}
                        secondaryTypographyProps={{ variant: 'caption' }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}

              <Divider sx={{ my: 1.5 }} />
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Работы МФУ</Typography>
              {!canWrite ? (
                <Alert severity="info">У вас нет прав на запись работ.</Alert>
              ) : (
                <Stack spacing={1.2}>
                  <FormControl fullWidth size="small">
                    <InputLabel id="mfu-work-type-label">Тип работы</InputLabel>
                    <Select
                      labelId="mfu-work-type-label"
                      label="Тип работы"
                      value={workType}
                      onChange={(event) => {
                        setWorkType(event.target.value);
                        setSelectedConsumable(null);
                        setWorkError('');
                        setWorkSuccess('');
                      }}
                    >
                      <MenuItem value="cartridge">Замена картриджа</MenuItem>
                      <MenuItem value="component">Замена комплектующей</MenuItem>
                    </Select>
                  </FormControl>

                  {workType === 'component' ? (
                    <FormControl fullWidth size="small">
                      <InputLabel id="mfu-component-type-label">Комплектующая</InputLabel>
                      <Select
                        labelId="mfu-component-type-label"
                        label="Комплектующая"
                        value={componentType}
                        onChange={(event) => setComponentType(event.target.value)}
                      >
                        {PRINTER_COMPONENT_OPTIONS.map((option) => (
                          <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  ) : null}

                  {recommendedWorkHint ? (
                    <Alert severity="info">{recommendedWorkHint}</Alert>
                  ) : null}

                  <Autocomplete
                    options={workConsumableOptions}
                    loading={consumablesLoading}
                    value={selectedConsumable}
                    onChange={(_, value) => setSelectedConsumable(value || null)}
                    getOptionLabel={(option) => formatConsumableLabel(option)}
                    isOptionEqualToValue={(option, value) => option.id === value.id}
                    noOptionsText="Расходники не найдены"
                    renderOption={(props, option) => (
                      <Box component="li" {...props} sx={{ display: 'block' }}>
                        <Typography variant="body2">{formatConsumableLabel(option)}</Typography>
                        {recommendedConsumable?.id === option.id ? (
                          <Typography variant="caption" color="primary.main">
                            Рекомендуем для выбранного устройства
                          </Typography>
                        ) : null}
                      </Box>
                    )}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        size="small"
                        label="Списываемый расходник"
                        placeholder="Выберите позицию со склада"
                      />
                    )}
                  />

                  {workError ? <Alert severity="error">{workError}</Alert> : null}
                  {workSuccess ? <Alert severity="success">{workSuccess}</Alert> : null}

                  <Button
                    variant="contained"
                    onClick={handleSubmitWork}
                    disabled={workSubmitLoading || consumablesLoading}
                  >
                    {workSubmitLoading ? 'Сохранение...' : 'Списать и записать работу'}
                  </Button>
                </Stack>
              )}
            </>
          ) : null}
        </Box>
      </Drawer>
    </MainLayout>
  );
}

export default Mfu;
