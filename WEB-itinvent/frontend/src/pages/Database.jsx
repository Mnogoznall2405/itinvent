import { Children, forwardRef, useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  InputAdornment,
  Tabs,
  Tab,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Autocomplete,
  Grid,
  IconButton,
  Divider,
  Fade,
  FormControl,
  FormControlLabel,
  InputLabel,
  Select,
  Snackbar,
  Chip,
  CircularProgress,
  Checkbox,
  TableSortLabel,
  MenuItem,
  Collapse,
  Switch,
  useTheme,
  useMediaQuery,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/Edit';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import QrCode2Icon from '@mui/icons-material/QrCode2';
import MyLocationIcon from '@mui/icons-material/MyLocation';
import MainLayout from '../components/layout/MainLayout';
import { equipmentAPI, API_V1_BASE, apiClient } from '../api/client';
import jsonAPI from '../api/json_client';
import { LoadingSpinner, StatusChip, ActionMenu } from '../components/common';
import { getOrFetchSWR, buildCacheKey } from '../lib/swrCache';
import { useAuth } from '../contexts/AuthContext';

// Debounce utility
function debounce(func, wait) {
  let timeout;
  function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  }

  executedFunction.cancel = () => {
    clearTimeout(timeout);
  };

  return executedFunction;
}

const EQUIPMENT_PAGE_LIMIT = 1000;
const EQUIPMENT_PREFETCH_PAGES = 1;
const SWR_STALE_TIME_MS = 30_000;
const ACTION_BATCH_SIZE = 10;
const normalizeDbId = (value) => String(value ?? '').trim();
const textCollator = new Intl.Collator('ru', { numeric: true, sensitivity: 'base' });
const DEFAULT_TABLE_SORT = { field: 'employee', direction: 'asc' };
const CONSUMABLES_DEFAULT_TABLE_SORT = { field: 'model', direction: 'asc' };
const TABLE_VIRTUALIZE_THRESHOLD = 120;
const TABLE_MAX_HEIGHT = 520;
const DATA_MODE_EQUIPMENT = 'equipment';
const DATA_MODE_CONSUMABLES = 'consumables';
const TABLE_WIDTHS = {
  consumables: { inv: 140, type: 140, model: 200, qty: 120, actions: 56 },
  equipment: { select: 56, inv: 120, serial: 110, type: 120, model: 170, employee: 220, status: 110, actions: 56 },
  equipmentMobile: { inv: 130, employee: 210, status: 110, actions: 56 },
};

const countGroupedItems = (groupedData) =>
  Object.values(groupedData || {}).reduce(
    (branchSum, locations) =>
      branchSum + Object.values(locations || {}).reduce((locSum, items) => locSum + (items?.length || 0), 0),
    0
  );

const groupSearchResults = (entries) => {
  const grouped = {};
  entries.forEach(({ branchName, locationName, item }) => {
    if (!grouped[branchName]) grouped[branchName] = {};
    if (!grouped[branchName][locationName]) grouped[branchName][locationName] = [];
    grouped[branchName][locationName].push(item);
  });
  return grouped;
};

const toInvNo = (itemOrInvNo) =>
  String(
    typeof itemOrInvNo === 'string' || typeof itemOrInvNo === 'number'
      ? itemOrInvNo
      : itemOrInvNo?.INV_NO || itemOrInvNo?.inv_no || ''
  ).trim();

const toItemId = (item) => String(readFirst(item, ['ID', 'id'], '')).trim();

const normalizeActionTargets = (selectedItems, fallbackInvNo) =>
  (selectedItems.length > 0 ? selectedItems : [fallbackInvNo])
    .map((invNo) => String(invNo || '').trim())
    .filter(Boolean);

const buildLocationKey = (branchName, locationName) => `${branchName}::${locationName}`;
const locationNameCollator = new Intl.Collator('ru', { numeric: true, sensitivity: 'base' });
const LOCATION_LIST_ITEM_HEIGHT = 40;
const LOCATION_LIST_MAX_VISIBLE = 8;
const LOCATION_LIST_OVERSCAN = 4;

const normalizeLocationOption = (location) => {
  const locNo = toIdOrNull(location?.LOC_NO ?? location?.loc_no);
  const locName = String(location?.LOC_NAME || location?.loc_name || location?.DESCR || '').trim();
  const searchBlob = `${locName} ${locNo || ''}`.toLowerCase();
  return {
    loc_no: locNo,
    loc_name: locName,
    search_blob: searchBlob,
  };
};

const sortLocationOptions = (a, b) => {
  const byName = locationNameCollator.compare(String(a?.loc_name || ''), String(b?.loc_name || ''));
  if (byName !== 0) return byName;
  return locationNameCollator.compare(String(a?.loc_no || ''), String(b?.loc_no || ''));
};

const formatLocationOptionLabel = (option) => {
  const locName = String(option?.loc_name || '').trim();
  const locNo = String(option?.loc_no || '').trim();
  if (locName && locNo && normalizeText(locName) !== normalizeText(locNo)) {
    return `${locName} (${locNo})`;
  }
  return locName || locNo || '-';
};

const filterLocationOptions = (options, state) => {
  const needle = normalizeText(state?.inputValue || '');
  if (!needle) return options;
  return options.filter((option) => String(option?.search_blob || '').includes(needle));
};

const VirtualizedAutocompleteListbox = forwardRef(function VirtualizedAutocompleteListbox(props, ref) {
  const { children, ...other } = props;
  const items = Children.toArray(children);
  const [scrollTop, setScrollTop] = useState(0);
  const itemCount = items.length;
  const viewportHeight = Math.min(LOCATION_LIST_MAX_VISIBLE, Math.max(1, itemCount)) * LOCATION_LIST_ITEM_HEIGHT;

  const startIndex = Math.max(0, Math.floor(scrollTop / LOCATION_LIST_ITEM_HEIGHT) - LOCATION_LIST_OVERSCAN);
  const endIndex = Math.min(
    itemCount,
    Math.ceil((scrollTop + viewportHeight) / LOCATION_LIST_ITEM_HEIGHT) + LOCATION_LIST_OVERSCAN
  );

  const topSpacerHeight = startIndex * LOCATION_LIST_ITEM_HEIGHT;
  const bottomSpacerHeight = Math.max(0, (itemCount - endIndex) * LOCATION_LIST_ITEM_HEIGHT);

  return (
    <Box
      ref={ref}
      component="ul"
      {...other}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      sx={{
        m: 0,
        p: 0,
        listStyle: 'none',
        maxHeight: viewportHeight,
        overflowY: 'auto',
        overflowX: 'hidden',
        scrollbarGutter: 'stable',
        '& li': {
          minHeight: LOCATION_LIST_ITEM_HEIGHT,
          boxSizing: 'border-box',
        },
      }}
    >
      {topSpacerHeight > 0 && <li aria-hidden="true" style={{ height: topSpacerHeight }} />}
      {items.slice(startIndex, endIndex)}
      {bottomSpacerHeight > 0 && <li aria-hidden="true" style={{ height: bottomSpacerHeight }} />}
    </Box>
  );
});

const LocationAutocompleteField = memo(function LocationAutocompleteField({
  label,
  value,
  options,
  onChange,
  disabled = false,
  loading = false,
  required = false,
  size = 'small',
}) {
  const selectedOption = useMemo(
    () => (Array.isArray(options) ? options.find((option) => option.loc_no === value) || null : null),
    [options, value]
  );

  return (
    <Autocomplete
      options={options}
      value={selectedOption}
      onChange={(_, next) => onChange(next?.loc_no || '')}
      disabled={disabled}
      loading={loading}
      ListboxComponent={VirtualizedAutocompleteListbox}
      filterOptions={filterLocationOptions}
      getOptionLabel={formatLocationOptionLabel}
      isOptionEqualToValue={(option, selected) => option.loc_no === selected.loc_no}
      noOptionsText="Ничего не найдено"
      renderOption={(props, option) => (
        <li {...props} key={option.loc_no || formatLocationOptionLabel(option)}>
          {formatLocationOptionLabel(option)}
        </li>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          required={required}
          size={size}
          placeholder="Начните вводить название или код"
        />
      )}
    />
  );
});

const mergeGroupedEquipment = (baseGrouped, nextGrouped) => {
  const merged = {};
  const sourceGroups = [baseGrouped || {}, nextGrouped || {}];

  sourceGroups.forEach((grouped) => {
    Object.entries(grouped).forEach(([branchName, locations]) => {
      if (!merged[branchName]) {
        merged[branchName] = {};
      }
      Object.entries(locations || {}).forEach(([locationName, items]) => {
        const currentItems = merged[branchName][locationName] || [];
        const existingInvNos = new Set(currentItems.map((item) => toInvNo(item)).filter(Boolean));
        const appended = [];
        (items || []).forEach((item) => {
          const invNo = toInvNo(item);
          if (!invNo || !existingInvNos.has(invNo)) {
            appended.push(item);
            if (invNo) {
              existingInvNos.add(invNo);
            }
          }
        });
        merged[branchName][locationName] = [...currentItems, ...appended];
      });
    });
  });

  return merged;
};

async function runInBatches(items, worker, batchSize = ACTION_BATCH_SIZE) {
  const settled = [];
  for (let i = 0; i < items.length; i += batchSize) {
    const chunk = items.slice(i, i + batchSize);
    const chunkResults = await Promise.allSettled(chunk.map(worker));
    settled.push(...chunkResults);
  }
  return settled;
}

const toNumberOrNull = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const toIdOrNull = (value) => {
  if (value === null || value === undefined || value === '') return null;
  return String(value).trim();
};

const normalizeText = (value) => String(value ?? '').trim().toLowerCase();

const validateEmployeeName = (name) => {
  if (!name || typeof name !== 'string') return false;
  const normalized = name.trim();
  if (normalized.length < 2 || normalized.length > 100) return false;

  const dangerousChars = ['<', '>', '"', "'", '&', ';', '|', '`', '\n', '\r'];
  if (dangerousChars.some((char) => normalized.includes(char))) return false;

  const upper = normalized.toUpperCase();
  const sqlKeywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', 'EXEC'];
  if (sqlKeywords.some((keyword) => upper.includes(keyword))) return false;

  return true;
};

const parseInvNosInput = (rawValue) => {
  const text = String(rawValue || '');
  const chunks = text.split(/[\s,;]+/g).map((token) => token.trim()).filter(Boolean);
  const invNos = [];
  chunks.forEach((chunk) => {
    const normalized = String(chunk).replace(/№/g, '').trim();
    if (normalized && !invNos.includes(normalized)) {
      invNos.push(normalized);
    }
  });
  return invNos;
};

const readFirst = (data, keys, fallback = '') => {
  for (const key of keys) {
    const value = data?.[key];
    if (value !== undefined && value !== null) return value;
  }
  return fallback;
};

const readQty = (item, fallback = 1) => {
  const raw = readFirst(item, ['QTY', 'qty'], fallback);
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const buildEquipmentQrText = (item) => {
  const invNo = String(readFirst(item, ['INV_NO', 'inv_no'], '') || '').trim();
  const serialNo = String(readFirst(item, ['SERIAL_NO', 'serial_no'], '') || '').trim();
  const modelName = String(readFirst(item, ['MODEL_NAME', 'model_name'], '') || '').trim();
  const partNo = String(readFirst(item, ['PART_NO', 'part_no'], '') || '').trim();

  return [
    `INV_NO: ${invNo || '-'}`,
    `SERIAL_NO: ${serialNo || '-'}`,
    `MODEL: ${modelName || '-'}`,
    `PART_NO: ${partNo || '-'}`,
  ].join('\n');
};

const buildEquipmentQrUrl = (payload) => {
  const text = String(payload || '').trim();
  if (!text) return '';
  const params = new URLSearchParams({
    size: '360x360',
    format: 'png',
    margin: '10',
    data: text,
  });
  return `https://api.qrserver.com/v1/create-qr-code/?${params.toString()}`;
};

const toOwnerOption = (owner) => ({
  owner_no: toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no),
  owner_display_name: String(owner?.OWNER_DISPLAY_NAME || owner?.owner_display_name || '').trim(),
  owner_dept: String(owner?.OWNER_DEPT || owner?.owner_dept || '').trim(),
});

const toConsumableSourceOption = (entry) => ({
  id: toNumberOrNull(readFirst(entry, ['ID', 'id'], null)),
  inv_no: String(readFirst(entry, ['INV_NO', 'inv_no'], '') || '').trim(),
  type_name: String(readFirst(entry, ['TYPE_NAME', 'type_name'], '') || '').trim(),
  model_name: String(readFirst(entry, ['MODEL_NAME', 'model_name'], '') || '').trim(),
  qty: Number(readFirst(entry, ['QTY', 'qty'], 0)) || 0,
  branch_name: String(readFirst(entry, ['BRANCH_NAME', 'branch_name'], '') || '').trim(),
  location_name: String(
    readFirst(entry, ['LOCATION_NAME', 'location_name', 'LOCATION', 'location'], '') || ''
  ).trim(),
});

const formatConsumableSourceLabel = (entry) => {
  const option = toConsumableSourceOption(entry);
  const model = option.model_name || '-';
  const type = option.type_name || '-';
  const branch = option.branch_name || '-';
  const location = option.location_name || '-';
  return `${model} | ${type} | ${branch} / ${location} | Остаток: ${option.qty}`;
};

const flattenGroupedConsumables = (grouped) => {
  const rows = [];
  Object.values(grouped || {}).forEach((locations) => {
    Object.values(locations || {}).forEach((items) => {
      (items || []).forEach((item) => rows.push(item));
    });
  });
  return rows;
};

const isCartridgeLikeConsumable = (entry) => {
  const option = toConsumableSourceOption(entry);
  const haystack = `${option.type_name} ${option.model_name}`.toLowerCase();
  const cartridgeTokens = ['картридж', 'катридж', 'тонер', 'cartridge', 'toner'];
  return cartridgeTokens.some((token) => haystack.includes(token));
};

const createAddEquipmentInitialForm = () => ({
  employee_name: '',
  employee_no: null,
  employee_dept: '',
  branch_no: '',
  loc_no: '',
  type_no: '',
  model_name: '',
  model_no: null,
  status_no: '',
  serial_number: '',
  part_no: '',
  ip_address: '',
  description: '',
});

const createAddConsumableInitialForm = () => ({
  branch_no: '',
  loc_no: '',
  type_no: '',
  model_name: '',
  model_no: null,
  qty: 1,
});

const buildDetailFormState = (data) => ({
  type_no: toNumberOrNull(readFirst(data, ['TYPE_NO', 'type_no'], null)),
  type_name: String(readFirst(data, ['TYPE_NAME', 'type_name'], '') || ''),
  model_no: toNumberOrNull(readFirst(data, ['MODEL_NO', 'model_no'], null)),
  model_name: String(readFirst(data, ['MODEL_NAME', 'model_name'], '') || ''),
  serial_no: String(readFirst(data, ['SERIAL_NO', 'serial_no'], '') || ''),
  hw_serial_no: String(readFirst(data, ['HW_SERIAL_NO', 'hw_serial_no'], '') || ''),
  part_no: String(readFirst(data, ['PART_NO', 'part_no'], '') || ''),
  description: String(readFirst(data, ['DESCRIPTION', 'description'], '') || ''),
  status_no: toNumberOrNull(readFirst(data, ['STATUS_NO', 'status_no'], null)),
  empl_no: toNumberOrNull(readFirst(data, ['EMPL_NO', 'empl_no'], null)),
  employee_name: String(readFirst(data, ['OWNER_DISPLAY_NAME', 'employee_name'], '') || ''),
  employee_dept: String(readFirst(data, ['OWNER_DEPT', 'employee_dept'], '') || ''),
  branch_no: toIdOrNull(readFirst(data, ['BRANCH_NO', 'branch_no'], null)),
  branch_name: String(readFirst(data, ['BRANCH_NAME', 'branch_name'], '') || ''),
  loc_no: toIdOrNull(readFirst(data, ['LOC_NO', 'loc_no'], null)),
  location_name: String(readFirst(data, ['LOCATION_NAME', 'location_name', 'LOCATION', 'location'], '') || ''),
  ip_address: String(readFirst(data, ['IP_ADDRESS', 'ip_address'], '') || ''),
  mac_address: String(readFirst(data, ['MAC_ADDRESS', 'mac_address', 'MAC_ADDR', 'mac_addr', 'MAC', 'mac'], '') || ''),
  network_name: String(
    readFirst(
      data,
      [
        'NETBIOS_NAME',
        'netbios_name',
        'NETWORK_NAME',
        'network_name',
        'NET_NAME',
        'net_name',
        'HOST_NAME',
        'host_name',
        'HOSTNAME',
        'hostname',
        'DNS_NAME',
        'dns_name',
        'DOMAIN_NAME',
        'domain_name',
      ],
      ''
    ) || ''
  ),
  domain_name: String(readFirst(data, ['DOMAIN_NAME', 'domain_name'], '') || ''),
});

const toGroupedItem = (data) => ({
  ID: readFirst(data, ['ID', 'id'], null),
  INV_NO: String(readFirst(data, ['INV_NO', 'inv_no'], '') || ''),
  SERIAL_NO: String(readFirst(data, ['SERIAL_NO', 'serial_no'], '') || ''),
  HW_SERIAL_NO: String(readFirst(data, ['HW_SERIAL_NO', 'hw_serial_no'], '') || ''),
  PART_NO: String(readFirst(data, ['PART_NO', 'part_no'], '') || ''),
  QTY: readQty(data, 1),
  IP_ADDRESS: String(readFirst(data, ['IP_ADDRESS', 'ip_address'], '') || ''),
  MAC_ADDRESS: String(readFirst(data, ['MAC_ADDRESS', 'mac_address', 'MAC_ADDR', 'mac_addr', 'MAC', 'mac'], '') || ''),
  NETWORK_NAME: String(
    readFirst(
      data,
      [
        'NETBIOS_NAME',
        'netbios_name',
        'NETWORK_NAME',
        'network_name',
        'NET_NAME',
        'net_name',
        'HOST_NAME',
        'host_name',
        'HOSTNAME',
        'hostname',
        'DNS_NAME',
        'dns_name',
        'DOMAIN_NAME',
        'domain_name',
      ],
      ''
    ) || ''
  ),
  DOMAIN_NAME: String(readFirst(data, ['DOMAIN_NAME', 'domain_name'], '') || ''),
  TYPE_NAME: String(readFirst(data, ['TYPE_NAME', 'type_name'], '-') || '-'),
  MODEL_NAME: String(readFirst(data, ['MODEL_NAME', 'model_name'], '-') || '-'),
  VENDOR_NAME: String(readFirst(data, ['VENDOR_NAME', 'vendor_name', 'MANUFACTURER', 'manufacturer'], '-') || '-'),
  OWNER_DISPLAY_NAME: String(readFirst(data, ['OWNER_DISPLAY_NAME', 'employee_name'], '-') || '-'),
  OWNER_DEPT: String(readFirst(data, ['OWNER_DEPT', 'employee_dept'], '') || ''),
  BRANCH_NAME: String(readFirst(data, ['BRANCH_NAME', 'branch_name'], 'Не указан') || 'Не указан'),
  LOCATION_NAME: String(readFirst(data, ['LOCATION_NAME', 'location_name', 'LOCATION', 'location'], 'Не указано') || 'Не указано'),
  DESCRIPTION: String(readFirst(data, ['DESCRIPTION', 'description'], '') || ''),
  TYPE_NO: toNumberOrNull(readFirst(data, ['TYPE_NO', 'type_no'], null)),
  MODEL_NO: toNumberOrNull(readFirst(data, ['MODEL_NO', 'model_no'], null)),
  STATUS_NO: toNumberOrNull(readFirst(data, ['STATUS_NO', 'status_no'], null)),
  DESCR: String(readFirst(data, ['DESCR', 'status_name', 'status'], '') || ''),
});

const PRINTER_MFU_KEYWORDS = [
  'принтер',
  'мфу',
  'плоттер',
  'плотер',
  'printer',
  'plotter',
  'mfp',
  'mfc',
  'large format',
  'wide format',
  'laserjet',
  'officejet',
  'deskjet',
  'workcentre',
  'versalink',
  'i-sensys',
  'designjet',
  'imageprograf',
  'surecolor',
  'plotwave',
];

const UPS_KEYWORDS = [
  'ибп',
  'ups',
  'uninterruptible',
  'power supply',
];

const PC_KEYWORDS = [
  'системный блок',
  'системный',
  'пк',
  'pc',
  'system unit',
];

const DEFAULT_CARTRIDGE_COLOR = 'Универсальный';

const PRINTER_COMPONENT_OPTIONS = [
  { value: 'fuser', label: 'Фьюзер' },
  { value: 'photoconductor', label: 'Фотобарабан' },
  { value: 'waste_toner', label: 'Отработанный тонер' },
  { value: 'transfer_belt', label: 'Трансферный ролик' },
];

const PC_COMPONENT_OPTIONS = [
  { value: 'ram', label: 'Оперативная память' },
  { value: 'ssd', label: 'SSD накопитель' },
  { value: 'hdd', label: 'HDD накопитель' },
  { value: 'gpu', label: 'Видеокарта' },
  { value: 'cpu', label: 'Процессор' },
  { value: 'motherboard', label: 'Материнская плата' },
  { value: 'psu', label: 'Блок питания' },
  { value: 'cooler', label: 'Кулер' },
  { value: 'fan', label: 'Вентилятор' },
];

const hasAnyKeyword = (text, keywords) => keywords.some((keyword) => text.includes(keyword));

const getItemCapabilityFlags = (item) => {
  const typeName = String(item?.TYPE_NAME || item?.type_name || '').toLowerCase();
  const modelName = String(item?.MODEL_NAME || item?.model_name || '').toLowerCase();
  const vendorName = String(item?.VENDOR_NAME || item?.vendor_name || item?.MANUFACTURER || item?.manufacturer || '').toLowerCase();
  const allFields = `${typeName} ${modelName} ${vendorName}`.trim();

  return {
    isPrinterOrMfu: hasAnyKeyword(allFields, PRINTER_MFU_KEYWORDS),
    isUps: hasAnyKeyword(allFields, UPS_KEYWORDS),
    isPc: hasAnyKeyword(allFields, PC_KEYWORDS),
  };
};

const getComponentOptionsByKind = (kind) =>
  kind === 'pc' ? PC_COMPONENT_OPTIONS : PRINTER_COMPONENT_OPTIONS;

const normalizePrinterComponentType = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'drum') return 'photoconductor';
  return normalized;
};

const getPrinterComponentOptionLabel = (value) => {
  const normalized = normalizePrinterComponentType(value);
  const known = PRINTER_COMPONENT_OPTIONS.find((option) => option.value === normalized);
  return known?.label || normalized || 'Компонент';
};

const getComponentLabel = (kind, type) => {
  if (kind === 'pc') {
    const option = PC_COMPONENT_OPTIONS.find((entry) => entry.value === type);
    return option?.label || type || 'компонента';
  }
  return getPrinterComponentOptionLabel(type);
};

const EMPTY_HISTORY = { count: 0, last_date: null, time_ago_str: null };

const upsertItemInGrouped = (groupedData, nextItem) => {
  const targetInvNo = toInvNo(nextItem);
  const nextGrouped = {};

  Object.entries(groupedData || {}).forEach(([branchName, locations]) => {
    Object.entries(locations || {}).forEach(([locationName, items]) => {
      const filteredItems = (items || []).filter((item) => toInvNo(item) !== targetInvNo);
      if (filteredItems.length === 0) return;
      if (!nextGrouped[branchName]) nextGrouped[branchName] = {};
      nextGrouped[branchName][locationName] = filteredItems;
    });
  });

  const targetBranch = String(nextItem?.BRANCH_NAME || nextItem?.branch_name || 'Не указан').trim() || 'Не указан';
  const targetLocation = String(
    nextItem?.LOCATION_NAME || nextItem?.location_name || nextItem?.LOCATION || nextItem?.location || 'Не указано'
  ).trim() || 'Не указано';

  if (!nextGrouped[targetBranch]) nextGrouped[targetBranch] = {};
  if (!nextGrouped[targetBranch][targetLocation]) nextGrouped[targetBranch][targetLocation] = [];
  nextGrouped[targetBranch][targetLocation] = [nextItem, ...nextGrouped[targetBranch][targetLocation]];

  return nextGrouped;
};

const EquipmentRow = memo(function EquipmentRow({
  item,
  isSelected,
  isMobile,
  theme,
  onSelect,
  onAction,
  onEditConsumableQty = null,
  allowSelection = true,
  dataMode = DATA_MODE_EQUIPMENT,
  canWrite = true,
}) {
  const invNo = String(item.INV_NO || item.inv_no || '');
  const itemId = toItemId(item);
  const isConsumablesMode = dataMode === DATA_MODE_CONSUMABLES;
  const employeeName = String(item.OWNER_DISPLAY_NAME || item.employee_name || '-');
  const employeeDept = String(item.OWNER_DEPT || item.employee_dept || '').trim();
  const modelName = String(item.MODEL_NAME || item.model_name || '-');
  const typeName = String(item.TYPE_NAME || item.type_name || '-');
  const qtyValue = readQty(item, 1);

  // Determine available actions based on equipment type
  const getAvailableActions = () => {
    const baseActions = canWrite ? ['view', 'transfer'] : ['view'];
    const flags = getItemCapabilityFlags(item);
    return [
      ...baseActions,
      ...(canWrite && flags.isPrinterOrMfu ? ['cartridge', 'component'] : []),
      ...(canWrite && flags.isUps ? ['battery'] : []),
      ...(canWrite && flags.isPc && !flags.isPrinterOrMfu ? ['component'] : []),
      ...(canWrite && flags.isPc ? ['cleaning'] : []),
    ];
  };

  const actions = getAvailableActions();

  if (isConsumablesMode) {
    return (
      <TableRow
        hover
        sx={{
          '& .MuiTableCell-root': {
            borderBottom: '1px solid ' + theme.palette.divider,
            py: isMobile ? 0.7 : 0.9,
            px: isMobile ? 1 : 1.25,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          },
        }}
      >
        <TableCell sx={{ width: TABLE_WIDTHS.consumables.inv }}>
          <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }} noWrap>
            {invNo || '-'}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.1 }} noWrap>
            ID: {itemId || '-'}
          </Typography>
        </TableCell>
        <TableCell sx={{ width: TABLE_WIDTHS.consumables.type }}>
          <Typography variant="body2" sx={{ lineHeight: 1.2 }} noWrap>
            {typeName || '-'}
          </Typography>
        </TableCell>
        <TableCell sx={{ width: TABLE_WIDTHS.consumables.model }}>
          <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }} noWrap>
            {modelName || '-'}
          </Typography>
        </TableCell>
        <TableCell sx={{ width: TABLE_WIDTHS.consumables.qty }} align="right">
          <Typography variant="body2" sx={{ fontWeight: 700 }} noWrap>
            {qtyValue.toLocaleString('ru-RU')}
          </Typography>
        </TableCell>
        <TableCell padding="checkbox" sx={{ width: TABLE_WIDTHS.consumables.actions, minWidth: TABLE_WIDTHS.consumables.actions }} align="right">
          <IconButton
            size="small"
            aria-label="Изменить количество"
            onClick={() => onEditConsumableQty?.(item)}
            disabled={!onEditConsumableQty}
          >
            <EditIcon fontSize="small" />
          </IconButton>
        </TableCell>
      </TableRow>
    );
  }

  return (
      <TableRow
        hover
        sx={{
          '& .MuiTableCell-root': {
            borderBottom: '1px solid ' + theme.palette.divider,
            py: isMobile ? 0.6 : 0.8,
            px: isMobile ? 0.8 : 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          },
        }}
      >
      {!isMobile && allowSelection && (
        <TableCell padding="checkbox" sx={{ width: TABLE_WIDTHS.equipment.select }}>
          <Checkbox
            checked={isSelected}
            onChange={() => onSelect(invNo)}
            onClick={(e) => e.stopPropagation()}
            size="small"
          />
        </TableCell>
      )}
      <TableCell sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.inv : TABLE_WIDTHS.equipment.inv }}>
        <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }} noWrap>
          {invNo || '-'}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.1 }} noWrap>
          ID: {itemId || '-'}
        </Typography>
      </TableCell>
      {!isMobile && (
        <TableCell sx={{ width: TABLE_WIDTHS.equipment.serial }}>
          <Typography variant="body2" noWrap>
            {String(item.SERIAL_NO || item.serial_no || item.HW_SERIAL_NO || item.hw_serial_no || '-')}
          </Typography>
        </TableCell>
      )}
      {!isMobile && (
        <TableCell sx={{ width: TABLE_WIDTHS.equipment.type }}>
          <Typography variant="body2" noWrap>
            {String(item.TYPE_NAME || item.type_name || '-')}
          </Typography>
        </TableCell>
      )}
      {!isMobile && (
        <TableCell sx={{ width: TABLE_WIDTHS.equipment.model }}>
          <Typography variant="body2" noWrap>
            {String(item.MODEL_NAME || item.model_name || '-')}
          </Typography>
        </TableCell>
      )}
      <TableCell sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.employee : TABLE_WIDTHS.equipment.employee }}>
        <Typography variant="body2" sx={{ lineHeight: 1.2 }} noWrap>
          {employeeName}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.1 }} noWrap>
          {`Отдел: ${employeeDept || '-'}`}
        </Typography>
      </TableCell>
      <TableCell sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.status : TABLE_WIDTHS.equipment.status }}>
        <StatusChip
          status={item.DESCR || item.status_name || item.status}
          size="small"
        />
      </TableCell>
      <TableCell padding="checkbox" sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.actions : TABLE_WIDTHS.equipment.actions, minWidth: isMobile ? TABLE_WIDTHS.equipmentMobile.actions : TABLE_WIDTHS.equipment.actions }} align="right">
        <ActionMenu
          onAction={onAction}
          actions={actions}
          item={item}
          label={'Actions for ' + invNo}
        />
      </TableCell>
    </TableRow>
  );
});

const EquipmentTable = memo(function EquipmentTable({
  items,
  isMobile,
  theme,
  selectedItemsSet,
  tableSort,
  onTableSort,
  onSelectAll,
  isAllSelected,
  isSomeSelected,
  onSelect,
  onAction,
  onEditConsumableQty = null,
  allowSelection = true,
  dataMode = DATA_MODE_EQUIPMENT,
  canWrite = true,
}) {
  const [scrollTop, setScrollTop] = useState(0);
  const isConsumablesMode = dataMode === DATA_MODE_CONSUMABLES;

  const getSortValue = useCallback((item, field) => {
    switch (field) {
      case 'id':
        return toItemId(item);
      case 'inv':
        return toInvNo(item);
      case 'serial':
        return String(item?.SERIAL_NO || item?.serial_no || item?.HW_SERIAL_NO || item?.hw_serial_no || '').trim();
      case 'type':
        return String(item?.TYPE_NAME || item?.type_name || '').trim();
      case 'model':
        return String(item?.MODEL_NAME || item?.model_name || '').trim();
      case 'qty':
        return readQty(item, 1);
      case 'employee':
        return String(item?.OWNER_DISPLAY_NAME || item?.employee_name || '').trim();
      case 'status':
        return String(item?.DESCR || item?.status_name || item?.status || '').trim();
      default:
        return '';
    }
  }, []);

  const sortedItems = useMemo(() => {
    const applySortDirection = (cmp) => (tableSort.direction === 'asc' ? cmp : -cmp);
    return [...(items || [])].sort((a, b) => {
      if (tableSort.field === 'qty') {
        const qtyCmp = getSortValue(a, 'qty') - getSortValue(b, 'qty');
        if (qtyCmp !== 0) {
          return applySortDirection(qtyCmp);
        }
      }

      const primaryCmp = textCollator.compare(
        String(getSortValue(a, tableSort.field)),
        String(getSortValue(b, tableSort.field))
      );
      if (primaryCmp !== 0) {
        return applySortDirection(primaryCmp);
      }

      const invCmp = textCollator.compare(toInvNo(a), toInvNo(b));
      if (invCmp !== 0) {
        return applySortDirection(invCmp);
      }

      return applySortDirection(textCollator.compare(toItemId(a), toItemId(b)));
    });
  }, [items, tableSort, getSortValue]);

  const useVirtualization = sortedItems.length >= TABLE_VIRTUALIZE_THRESHOLD;
  const rowHeight = isMobile ? 44 : 52;
  const viewportHeight = useVirtualization
    ? Math.min(TABLE_MAX_HEIGHT, Math.max(rowHeight * 6, rowHeight * Math.min(14, sortedItems.length)))
    : undefined;
  const overscanRows = 8;

  const startIndex = useVirtualization
    ? Math.max(0, Math.floor(scrollTop / rowHeight) - overscanRows)
    : 0;
  const endIndex = useVirtualization
    ? Math.min(
      sortedItems.length,
      Math.ceil((scrollTop + Number(viewportHeight || 0)) / rowHeight) + overscanRows
    )
    : sortedItems.length;

  const visibleItems = useVirtualization ? sortedItems.slice(startIndex, endIndex) : sortedItems;
  const topSpacerHeight = useVirtualization ? startIndex * rowHeight : 0;
  const bottomSpacerHeight = useVirtualization ? Math.max(0, (sortedItems.length - endIndex) * rowHeight) : 0;
  const colSpan = isConsumablesMode ? 5 : (isMobile ? 4 : (allowSelection ? 8 : 7));
  const tableMinWidth = isConsumablesMode
    ? (TABLE_WIDTHS.consumables.inv
      + TABLE_WIDTHS.consumables.type
      + TABLE_WIDTHS.consumables.model
      + TABLE_WIDTHS.consumables.qty
      + TABLE_WIDTHS.consumables.actions)
    : isMobile
      ? (TABLE_WIDTHS.equipmentMobile.inv
        + TABLE_WIDTHS.equipmentMobile.employee
        + TABLE_WIDTHS.equipmentMobile.status
        + TABLE_WIDTHS.equipmentMobile.actions)
      : ((allowSelection ? TABLE_WIDTHS.equipment.select : 0)
        + TABLE_WIDTHS.equipment.inv
        + TABLE_WIDTHS.equipment.serial
        + TABLE_WIDTHS.equipment.type
        + TABLE_WIDTHS.equipment.model
        + TABLE_WIDTHS.equipment.employee
        + TABLE_WIDTHS.equipment.status
        + TABLE_WIDTHS.equipment.actions);

  const handleContainerScroll = useCallback((event) => {
    if (!useVirtualization) return;
    setScrollTop(event.currentTarget.scrollTop);
  }, [useVirtualization]);

  return (
    <TableContainer
      component={Paper}
      variant="outlined"
      onScroll={handleContainerScroll}
      sx={{
        borderRadius: 2,
        boxShadow: 'none',
        maxHeight: viewportHeight,
        overflowY: viewportHeight ? 'auto' : 'visible',
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        scrollbarGutter: 'stable',
      }}
    >
      <Table
        size={isMobile ? 'small' : 'medium'}
        sx={{ minWidth: tableMinWidth, width: '100%', tableLayout: 'fixed' }}
      >
        <TableHead>
          <TableRow>
            {isConsumablesMode ? (
              <>
                <TableCell sx={{ width: TABLE_WIDTHS.consumables.inv }}>
                  <TableSortLabel
                    active={tableSort.field === 'inv'}
                    direction={tableSort.field === 'inv' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('inv')}
                  >
                    Инв. №
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ width: TABLE_WIDTHS.consumables.type }}>
                  <TableSortLabel
                    active={tableSort.field === 'type'}
                    direction={tableSort.field === 'type' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('type')}
                  >
                    Тип
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ width: TABLE_WIDTHS.consumables.model }}>
                  <TableSortLabel
                    active={tableSort.field === 'model'}
                    direction={tableSort.field === 'model' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('model')}
                  >
                    Модель
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ width: TABLE_WIDTHS.consumables.qty }} align="right">
                  <TableSortLabel
                    active={tableSort.field === 'qty'}
                    direction={tableSort.field === 'qty' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('qty')}
                  >
                    Количество
                  </TableSortLabel>
                </TableCell>
                <TableCell padding="checkbox" sx={{ width: TABLE_WIDTHS.consumables.actions, minWidth: TABLE_WIDTHS.consumables.actions }} />
              </>
            ) : (
              <>
                {!isMobile && allowSelection && (
                  <TableCell padding="checkbox" sx={{ width: TABLE_WIDTHS.equipment.select }}>
                    <Checkbox
                      size="small"
                      checked={isAllSelected(sortedItems)}
                      indeterminate={isSomeSelected(sortedItems) && !isAllSelected(sortedItems)}
                      onChange={(event) => onSelectAll(sortedItems, event)}
                    />
                  </TableCell>
                )}
                <TableCell sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.inv : TABLE_WIDTHS.equipment.inv }}>
                  <TableSortLabel
                    active={tableSort.field === 'inv'}
                    direction={tableSort.field === 'inv' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('inv')}
                  >
                    Инв. №
                  </TableSortLabel>
                </TableCell>
                {!isMobile && (
                  <TableCell sx={{ width: TABLE_WIDTHS.equipment.serial }}>
                    <TableSortLabel
                      active={tableSort.field === 'serial'}
                      direction={tableSort.field === 'serial' ? tableSort.direction : 'asc'}
                      onClick={() => onTableSort('serial')}
                    >
                      Серийный
                    </TableSortLabel>
                  </TableCell>
                )}
                {!isMobile && (
                  <TableCell sx={{ width: TABLE_WIDTHS.equipment.type }}>
                    <TableSortLabel
                      active={tableSort.field === 'type'}
                      direction={tableSort.field === 'type' ? tableSort.direction : 'asc'}
                      onClick={() => onTableSort('type')}
                    >
                      Тип
                    </TableSortLabel>
                  </TableCell>
                )}
                {!isMobile && (
                  <TableCell sx={{ width: TABLE_WIDTHS.equipment.model }}>
                    <TableSortLabel
                      active={tableSort.field === 'model'}
                      direction={tableSort.field === 'model' ? tableSort.direction : 'asc'}
                      onClick={() => onTableSort('model')}
                    >
                      Модель
                    </TableSortLabel>
                  </TableCell>
                )}
                <TableCell sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.employee : TABLE_WIDTHS.equipment.employee }}>
                  <TableSortLabel
                    active={tableSort.field === 'employee'}
                    direction={tableSort.field === 'employee' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('employee')}
                  >
                    Сотрудник
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.status : TABLE_WIDTHS.equipment.status }}>
                  <TableSortLabel
                    active={tableSort.field === 'status'}
                    direction={tableSort.field === 'status' ? tableSort.direction : 'asc'}
                    onClick={() => onTableSort('status')}
                  >
                    Статус
                  </TableSortLabel>
                </TableCell>
                <TableCell padding="checkbox" sx={{ width: isMobile ? TABLE_WIDTHS.equipmentMobile.actions : TABLE_WIDTHS.equipment.actions, minWidth: isMobile ? TABLE_WIDTHS.equipmentMobile.actions : TABLE_WIDTHS.equipment.actions }} />
              </>
            )}
          </TableRow>
        </TableHead>
        <TableBody>
          {topSpacerHeight > 0 && (
            <TableRow>
              <TableCell colSpan={colSpan} sx={{ p: 0, borderBottom: 'none', height: topSpacerHeight }} />
            </TableRow>
          )}

          {visibleItems.map((item, idx) => {
            const invNo = toInvNo(item);
            const isSelected = selectedItemsSet.has(invNo);
            return (
              <EquipmentRow
                key={invNo + '-' + idx}
                item={item}
                isSelected={isSelected}
                isMobile={isMobile}
                theme={theme}
                onSelect={onSelect}
                onAction={onAction}
                onEditConsumableQty={onEditConsumableQty}
                allowSelection={allowSelection}
                dataMode={dataMode}
                canWrite={canWrite}
              />
            );
          })}

          {bottomSpacerHeight > 0 && (
            <TableRow>
              <TableCell colSpan={colSpan} sx={{ p: 0, borderBottom: 'none', height: bottomSpacerHeight }} />
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
});

function Database() {
  const { hasPermission } = useAuth();
  const canDatabaseWrite = hasPermission('database.write');
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const initialLoadDoneRef = useRef(false);

  const [loading, setLoading] = useState(true);
  const [equipmentTypes, setEquipmentTypes] = useState([]);
  const [branches, setBranches] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [dataMode, setDataMode] = useState(DATA_MODE_EQUIPMENT);
  const [selectedBranch, setSelectedBranch] = useState('');
  const [tableSort, setTableSort] = useState(DEFAULT_TABLE_SORT);
  const [equipment, setEquipment] = useState({});
  const [total, setTotal] = useState(0);
  const [serverTotal, setServerTotal] = useState(0);
  const [loadedCount, setLoadedCount] = useState(0);
  const [nextEquipmentPage, setNextEquipmentPage] = useState(null);
  const [equipmentPagesTotal, setEquipmentPagesTotal] = useState(1);
  const [loadingMoreEquipment, setLoadingMoreEquipment] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [filteredData, setFilteredData] = useState(null);

  const [expandedBranches, setExpandedBranches] = useState(() => new Set());
  const [expandedLocations, setExpandedLocations] = useState(() => new Set());
  const [selectedItems, setSelectedItems] = useState([]);
  const [detailModal, setDetailModal] = useState({ open: false, data: null, loading: false });
  const [detailEditMode, setDetailEditMode] = useState(false);
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [detailSuccess, setDetailSuccess] = useState('');
  const [detailForm, setDetailForm] = useState(null);
  const [detailInitialForm, setDetailInitialForm] = useState(null);
  const [detailLocations, setDetailLocations] = useState([]);
  const [detailModels, setDetailModels] = useState([]);
  const [detailModelsLoading, setDetailModelsLoading] = useState(false);
  const [detailEmployeeOptions, setDetailEmployeeOptions] = useState([]);
  const [detailEmployeeInput, setDetailEmployeeInput] = useState('');
  const [detailEmployeeLoading, setDetailEmployeeLoading] = useState(false);
  const [detailTab, setDetailTab] = useState('general');
  const [detailActs, setDetailActs] = useState([]);
  const [detailActsLoading, setDetailActsLoading] = useState(false);
  const [detailActsError, setDetailActsError] = useState('');
  const [detailActsLoadedInvNo, setDetailActsLoadedInvNo] = useState('');
  const [detailActOpeningDocNo, setDetailActOpeningDocNo] = useState('');
  const [detailActFieldsOpen, setDetailActFieldsOpen] = useState(false);
  const [detailActSelected, setDetailActSelected] = useState(null);
  const [detailQrOpen, setDetailQrOpen] = useState(false);
  const [actionModal, setActionModal] = useState({ open: false, type: null, invNo: null, componentKind: null });

  // Action form state
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState('');
  const [newEmployee, setNewEmployee] = useState('');
  const [newEmployeeNo, setNewEmployeeNo] = useState(null);
  const [transferDepartment, setTransferDepartment] = useState('');
  const [transferDepartmentOptions, setTransferDepartmentOptions] = useState([]);
  const [transferDepartmentLoading, setTransferDepartmentLoading] = useState(false);
  const [transferBranchNo, setTransferBranchNo] = useState(null);
  const [transferLocationNo, setTransferLocationNo] = useState(null);
  const [transferLocations, setTransferLocations] = useState([]);
  const [transferLocationsLoading, setTransferLocationsLoading] = useState(false);
  const [transferEmployeeInput, setTransferEmployeeInput] = useState('');
  const [transferEmployeeOptions, setTransferEmployeeOptions] = useState([]);
  const [transferEmployeeLoading, setTransferEmployeeLoading] = useState(false);
  const [transferResult, setTransferResult] = useState(null);
  const [transferEmailMode, setTransferEmailMode] = useState('old');
  const [transferManualEmail, setTransferManualEmail] = useState('');
  const [transferRecipientInput, setTransferRecipientInput] = useState('');
  const [transferRecipientOptions, setTransferRecipientOptions] = useState([]);
  const [transferRecipient, setTransferRecipient] = useState(null);
  const [transferRecipientLoading, setTransferRecipientLoading] = useState(false);
  const [transferEmailLoading, setTransferEmailLoading] = useState(false);
  const [transferEmailStatus, setTransferEmailStatus] = useState('');
  const [transferEmailError, setTransferEmailError] = useState('');
  const [addEquipmentModalOpen, setAddEquipmentModalOpen] = useState(false);
  const [addEquipmentForm, setAddEquipmentForm] = useState(() => createAddEquipmentInitialForm());
  const [addEquipmentLoading, setAddEquipmentLoading] = useState(false);
  const [addEquipmentError, setAddEquipmentError] = useState('');
  const [addEquipmentSuccess, setAddEquipmentSuccess] = useState('');
  const [addEquipmentToast, setAddEquipmentToast] = useState({ open: false, message: '' });
  const [addConsumableModalOpen, setAddConsumableModalOpen] = useState(false);
  const [addConsumableForm, setAddConsumableForm] = useState(() => createAddConsumableInitialForm());
  const [addConsumableLoading, setAddConsumableLoading] = useState(false);
  const [addConsumableError, setAddConsumableError] = useState('');
  const [addConsumableSuccess, setAddConsumableSuccess] = useState('');
  const [addConsumableToast, setAddConsumableToast] = useState({ open: false, message: '' });
  const [addConsumableLocations, setAddConsumableLocations] = useState([]);
  const [addConsumableLocationsLoading, setAddConsumableLocationsLoading] = useState(false);
  const [addConsumableModels, setAddConsumableModels] = useState([]);
  const [addConsumableModelsLoading, setAddConsumableModelsLoading] = useState(false);
  const [editConsumableQtyModal, setEditConsumableQtyModal] = useState({ open: false, item: null });
  const [editConsumableQtyValue, setEditConsumableQtyValue] = useState('');
  const [editConsumableQtyLoading, setEditConsumableQtyLoading] = useState(false);
  const [editConsumableQtyError, setEditConsumableQtyError] = useState('');
  const [editConsumableQtyToast, setEditConsumableQtyToast] = useState({ open: false, message: '' });
  const [addEmployeeInput, setAddEmployeeInput] = useState('');
  const [addEmployeeOptions, setAddEmployeeOptions] = useState([]);
  const [addEmployeeLoading, setAddEmployeeLoading] = useState(false);
  const [addLocations, setAddLocations] = useState([]);
  const [addLocationsLoading, setAddLocationsLoading] = useState(false);
  const [addModels, setAddModels] = useState([]);
  const [addModelsLoading, setAddModelsLoading] = useState(false);
  const [uploadActModalOpen, setUploadActModalOpen] = useState(false);
  const [uploadActFile, setUploadActFile] = useState(null);
  const [uploadActDraft, setUploadActDraft] = useState(null);
  const [uploadActParsing, setUploadActParsing] = useState(false);
  const [uploadActCommitting, setUploadActCommitting] = useState(false);
  const [uploadActError, setUploadActError] = useState('');
  const [uploadActAutoEmail, setUploadActAutoEmail] = useState(true);
  const uploadActAutoEmailRef = useRef(true);

  // Synchronize ref with state
  useEffect(() => {
    uploadActAutoEmailRef.current = uploadActAutoEmail;
  }, [uploadActAutoEmail]);
  const [uploadActForm, setUploadActForm] = useState({
    document_title: '',
    from_employee: '',
    to_employee: '',
    doc_date: '',
    equipment_inv_nos_text: '',
  });
  const [uploadActToast, setUploadActToast] = useState({ open: false, message: '', severity: 'success' });
  const [uploadActCommitResult, setUploadActCommitResult] = useState(null);
  const [uploadActEmailSubject, setUploadActEmailSubject] = useState('');
  const [uploadActEmailBody, setUploadActEmailBody] = useState('');
  const [uploadActEmailRecipientsInput, setUploadActEmailRecipientsInput] = useState('');
  const [uploadActEmailRecipientOptions, setUploadActEmailRecipientOptions] = useState([]);
  const [uploadActEmailRecipients, setUploadActEmailRecipients] = useState([]);
  const [uploadActEmailRecipientsLoading, setUploadActEmailRecipientsLoading] = useState(false);
  const [uploadActEmailLoading, setUploadActEmailLoading] = useState(false);
  const [uploadActEmailError, setUploadActEmailError] = useState('');
  const [uploadActEmailStatus, setUploadActEmailStatus] = useState('');
  const [uploadActEmailLastRecipients, setUploadActEmailLastRecipients] = useState([]);
  const [uploadActEmailSummary, setUploadActEmailSummary] = useState({
    mode: '',
    successCount: 0,
    failedCount: 0,
  });
  const [cartridgeModel, setCartridgeModel] = useState('');
  const [selectedWorkConsumable, setSelectedWorkConsumable] = useState(null);
  const [workConsumableOptions, setWorkConsumableOptions] = useState([]);
  const [workConsumablesLoading, setWorkConsumablesLoading] = useState(false);
  const [componentType, setComponentType] = useState(PRINTER_COMPONENT_OPTIONS[0].value);
  const [cartridgeHistory, setCartridgeHistory] = useState(null);
  const [batteryHistory, setBatteryHistory] = useState(null);
  const [componentHistory, setComponentHistory] = useState(null);
  const [cleaningHistory, setCleaningHistory] = useState(null);
  const isConsumablesMode = dataMode === DATA_MODE_CONSUMABLES;

  // Utility function to format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const detailActSummary = useMemo(() => {
    if (!detailActSelected || typeof detailActSelected !== 'object') return null;
    const pick = (keys, fallback = '-') => {
      const value = readFirst(detailActSelected, keys, '');
      if (value === null || value === undefined) return fallback;
      const text = String(value).trim();
      return text || fallback;
    };
    const addInfo = readFirst(detailActSelected, ['add_info', 'ADD_INFO', 'addinfo', 'ADDINFO'], '');
    return {
      docNo: pick(['doc_no', 'DOC_NO']),
      docNumber: pick(['doc_number', 'DOC_NUMBER']),
      docDate: pick(['doc_date', 'DOC_DATE']),
      typeName: pick(['type_name', 'TYPE_NAME', 'type_no', 'TYPE_NO']),
      branchName: pick(['branch_name', 'BRANCH_NAME']),
      locationName: pick(['location_name', 'LOCATION_NAME']),
      employeeName: pick(['employee_name', 'EMPLOYEE_NAME']),
      itemId: pick(['item_id', 'ITEM_ID']),
      createDate: pick(['create_date', 'CREATE_DATE']),
      createUser: pick(['create_user_name', 'CREATE_USER_NAME']),
      changeDate: pick(['ch_date', 'CH_DATE']),
      changeUser: pick(['ch_user', 'CH_USER']),
      addInfo: String(addInfo || '').trim(),
    };
  }, [detailActSelected]);

  const uploadActStep = useMemo(() => {
    if (uploadActCommitResult?.doc_no) return 4;
    if (uploadActCommitting) return 3;
    if (uploadActDraft) return 2;
    if (uploadActFile) return 1;
    return 0;
  }, [uploadActCommitResult?.doc_no, uploadActCommitting, uploadActDraft, uploadActFile]);

  // Get db_name from equipment or localStorage
  const [dbNameState, setDbNameState] = useState('');

  useEffect(() => {
    let isMounted = true;

    const loadDbName = async () => {
      let dbId = normalizeDbId(localStorage.getItem('selected_database'));
      try {
        const response = await apiClient.get('/database/current');
        const data = response?.data || {};
        const currentDbId = normalizeDbId(data?.id || data?.database_id || '');
        if (currentDbId) {
          dbId = currentDbId;
        }
      } catch (e) {
        console.error('Error loading db:', e);
      }

      if (dbId) {
        localStorage.setItem('selected_database', dbId);
      }

      if (isMounted) {
        setDbNameState(dbId);
      }
    };

    loadDbName();

    return () => {
      isMounted = false;
    };
  }, []);

  const db_name = dbNameState;
  const [allEquipment, setAllEquipment] = useState({});
  const [initialLoadDone, setInitialLoadDone] = useState(false);

  const getDbCacheScope = useCallback(
    () => normalizeDbId(localStorage.getItem('selected_database') || db_name || 'default'),
    [db_name]
  );

  const fetchEquipmentTypes = useCallback(async ({ force = false } = {}) => {
    try {
      const cacheKey = buildCacheKey('equipment-types', getDbCacheScope());
      const { data: response } = await getOrFetchSWR(
        cacheKey,
        () => equipmentAPI.getTypes(),
        { staleTimeMs: SWR_STALE_TIME_MS, force }
      );
      setEquipmentTypes(response || []);
    } catch (error) {
      console.error('Error fetching types:', error);
    }
  }, [getDbCacheScope]);

  const fetchStatuses = useCallback(async ({ force = false } = {}) => {
    try {
      const cacheKey = buildCacheKey('equipment-statuses', getDbCacheScope());
      const { data: response } = await getOrFetchSWR(
        cacheKey,
        () => equipmentAPI.getStatuses(),
        { staleTimeMs: SWR_STALE_TIME_MS, force }
      );
      setStatuses(Array.isArray(response) ? response : []);
    } catch (error) {
      console.error('Error fetching statuses:', error);
    }
  }, [getDbCacheScope]);

  const fetchBranches = useCallback(async ({ force = false } = {}) => {
    try {
      const cacheKey = buildCacheKey('equipment-branches-list', getDbCacheScope());
      const { data } = await getOrFetchSWR(
        cacheKey,
        () => equipmentAPI.getBranchesList(),
        { staleTimeMs: SWR_STALE_TIME_MS, force }
      );
      setBranches(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error fetching branches:', error);
    }
  }, [getDbCacheScope]);

  const fetchEquipmentGroupedPage = useCallback(async (page, { force = false } = {}) => {
    const safePage = Math.max(1, Number(page || 1));
    const groupedCacheKey = dataMode === DATA_MODE_CONSUMABLES ? 'consumables-grouped' : 'equipment-grouped';
    const cacheKey = buildCacheKey(
      groupedCacheKey,
      getDbCacheScope(),
      safePage,
      EQUIPMENT_PAGE_LIMIT
    );
    const { data } = await getOrFetchSWR(
      cacheKey,
      () => (
        dataMode === DATA_MODE_CONSUMABLES
          ? equipmentAPI.getAllConsumablesGrouped({ page: safePage, limit: EQUIPMENT_PAGE_LIMIT })
          : equipmentAPI.getAllEquipmentGrouped({ page: safePage, limit: EQUIPMENT_PAGE_LIMIT })
      ),
      { staleTimeMs: SWR_STALE_TIME_MS, force }
    );
    return data || {};
  }, [dataMode, getDbCacheScope]);

  const loadMoreEquipmentPages = useCallback(({
    startPage = null,
    maxPages = 1,
    force = false,
    totalPagesOverride = null,
  } = {}) => {
    const resolvedTotalPages = Number(totalPagesOverride || equipmentPagesTotal || 1);
    const initialPage = startPage ?? nextEquipmentPage;
    if (!initialPage || initialPage > resolvedTotalPages || loadingMoreEquipment) return;

    setLoadingMoreEquipment(true);
    return (async () => {
      let cursor = initialPage;
      let loadedPagesInRun = 0;
      let mergedChunk = {};
      let latestServerTotal = serverTotal;

      while (cursor <= resolvedTotalPages && loadedPagesInRun < Math.max(1, maxPages)) {
        const pageResult = await fetchEquipmentGroupedPage(cursor, { force });
        mergedChunk = mergeGroupedEquipment(mergedChunk, pageResult.grouped || {});
        latestServerTotal = Number(pageResult.total || latestServerTotal || 0);
        cursor += 1;
        loadedPagesInRun += 1;
      }

      if (loadedPagesInRun > 0) {
        setAllEquipment((prev) => {
          const nextGrouped = mergeGroupedEquipment(prev, mergedChunk);
          setLoadedCount(countGroupedItems(nextGrouped));
          return nextGrouped;
        });
      }

      setServerTotal(latestServerTotal || 0);
      setNextEquipmentPage(cursor <= resolvedTotalPages ? cursor : null);
    })().catch((error) => {
      console.error('Error loading additional equipment pages:', error);
    }).finally(() => {
      setLoadingMoreEquipment(false);
    });
  }, [
    nextEquipmentPage,
    equipmentPagesTotal,
    loadingMoreEquipment,
    serverTotal,
    fetchEquipmentGroupedPage,
  ]);

  const fetchAllEquipment = useCallback(async ({ force = false } = {}) => {
    setLoading(true);
    try {
      const firstPageResult = await fetchEquipmentGroupedPage(1, { force });
      const firstGrouped = firstPageResult.grouped || {};
      const firstLoadedCount = countGroupedItems(firstGrouped);
      const totalFromServer = Number(firstPageResult.total || firstLoadedCount || 0);
      const pagesFromServer = Math.max(
        1,
        Number(firstPageResult.pages || Math.ceil((totalFromServer || 0) / EQUIPMENT_PAGE_LIMIT) || 1)
      );

      setAllEquipment(firstGrouped);
      setEquipment(firstGrouped);
      setLoadedCount(firstLoadedCount);
      setTotal(firstLoadedCount);
      setServerTotal(totalFromServer || firstLoadedCount);
      setEquipmentPagesTotal(pagesFromServer);
      setNextEquipmentPage(pagesFromServer > 1 ? 2 : null);
      setInitialLoadDone(true);

      if (pagesFromServer > 1 && EQUIPMENT_PREFETCH_PAGES > 0) {
        void loadMoreEquipmentPages({
          startPage: 2,
          maxPages: EQUIPMENT_PREFETCH_PAGES,
          force,
          totalPagesOverride: pagesFromServer,
        });
      }
    } catch (error) {
      console.error('Error fetching equipment:', error);
    } finally {
      setLoading(false);
    }
  }, [fetchEquipmentGroupedPage, loadMoreEquipmentPages]);

  const refreshCurrentDbData = useCallback(async ({ force = false } = {}) => {
    await Promise.all([
      fetchEquipmentTypes({ force }),
      fetchStatuses({ force }),
      fetchBranches({ force }),
    ]);
    await fetchAllEquipment({ force });
  }, [fetchEquipmentTypes, fetchStatuses, fetchBranches, fetchAllEquipment]);

  // Filter equipment locally when branch changes (after initial load)
  useEffect(() => {
    if (!initialLoadDone) return;

    if (!selectedBranch) {
      // No filter - show all
      setEquipment(allEquipment);
      setTotal(countGroupedItems(allEquipment));
      return;
    }

    const filtered = {};
    let totalCount = 0;
    const selectedBranchNormalized = normalizeText(selectedBranch);

    Object.entries(allEquipment).forEach(([branch, locations]) => {
      // Filter by exact branch selected in dropdown
      if (selectedBranchNormalized && normalizeText(branch) !== selectedBranchNormalized) {
        return;
      }

      filtered[branch] = {};
      Object.entries(locations).forEach(([location, items]) => {
        const matched = items;
        if (matched.length > 0) {
          filtered[branch][location] = matched;
          totalCount += matched.length;
        }
      });

      // Remove branch if no items
      if (Object.keys(filtered[branch]).length === 0) {
        delete filtered[branch];
      }
    });

    setEquipment(filtered);
    setTotal(totalCount);
  }, [selectedBranch, allEquipment, initialLoadDone]);

  useEffect(() => {
    if (initialLoadDoneRef.current) return;
    initialLoadDoneRef.current = true;
    void refreshCurrentDbData();
  }, [refreshCurrentDbData]);

  useEffect(() => {
    if (!initialLoadDoneRef.current) return;
    setTableSort(dataMode === DATA_MODE_CONSUMABLES ? CONSUMABLES_DEFAULT_TABLE_SORT : DEFAULT_TABLE_SORT);
    setSearchQuery('');
    setFilteredData(null);
    setSelectedItems([]);
    setExpandedBranches(new Set());
    setExpandedLocations(new Set());
    setInitialLoadDone(false);
    setEquipment({});
    setAllEquipment({});
    setTotal(0);
    setServerTotal(0);
    setLoadedCount(0);
    setEquipmentPagesTotal(1);
    setNextEquipmentPage(null);
    void refreshCurrentDbData({ force: true });
  }, [dataMode]);

  useEffect(() => {
    const handleDatabaseChanged = () => {
      setSelectedBranch('');
      setSearchQuery('');
      setFilteredData(null);
      setSelectedItems([]);
      setExpandedBranches(new Set());
      setExpandedLocations(new Set());
      setInitialLoadDone(false);
      setDbNameState(normalizeDbId(localStorage.getItem('selected_database')));
      void refreshCurrentDbData({ force: true });
    };

    window.addEventListener('database-changed', handleDatabaseChanged);
    return () => {
      window.removeEventListener('database-changed', handleDatabaseChanged);
    };
  }, [refreshCurrentDbData]);

  const displayData = filteredData !== null ? filteredData : equipment;
  const visibleBranchNames = useMemo(() => Object.keys(displayData || {}), [displayData]);

  const visibleLocationKeys = useMemo(() => {
    const keys = [];
    visibleBranchNames.forEach((branchName) => {
      const locations = displayData?.[branchName] || {};
      Object.keys(locations).forEach((locationName) => {
        keys.push(buildLocationKey(branchName, locationName));
      });
    });
    return keys;
  }, [displayData, visibleBranchNames]);

  const hasExpandedVisible = useMemo(() => {
    const hasExpandedBranch = visibleBranchNames.some((branchName) => expandedBranches.has(branchName));
    if (hasExpandedBranch) return true;
    return visibleLocationKeys.some((locationKey) => expandedLocations.has(locationKey));
  }, [visibleBranchNames, visibleLocationKeys, expandedBranches, expandedLocations]);

  const handleCollapseAll = useCallback(() => {
    setExpandedBranches(new Set());
    setExpandedLocations(new Set());
  }, []);

  // Create index Map for O(1) search instead of O(n)
  const equipmentIndex = useMemo(() => {
    const index = new Map();
    Object.values(allEquipment).forEach((locations) => {
      Object.values(locations).forEach(items => {
        items.forEach(item => {
          const invNo = String(item.INV_NO || item.inv_no);
          if (invNo) {
            index.set(invNo, item);
          }
        });
      });
    });
    return index;
  }, [allEquipment]);

  // O(1) search using index
  const findEquipmentByInvNo = useCallback((invNo) => {
    return equipmentIndex.get(String(invNo)) || null;
  }, [equipmentIndex]);

  const getItemBranch = useCallback(
    (item) => String(item?.BRANCH_NAME || item?.branch_name || selectedBranch || '').trim(),
    [selectedBranch]
  );

  const searchOwnersCached = useCallback(async (query, limit = 20) => {
    const normalizedQuery = String(query || '').trim().toLowerCase();
    const cacheKey = buildCacheKey(
      'owners-search',
      getDbCacheScope(),
      normalizedQuery,
      Number(limit || 20)
    );
    const { data } = await getOrFetchSWR(
      cacheKey,
      () => equipmentAPI.searchOwners(query, limit),
      { staleTimeMs: SWR_STALE_TIME_MS }
    );
    return data;
  }, [getDbCacheScope]);

  const getOwnerDepartmentsCached = useCallback(async (limit = 500) => {
    const cacheKey = buildCacheKey('owners-departments', getDbCacheScope(), Number(limit || 500));
    const { data } = await getOrFetchSWR(
      cacheKey,
      () => equipmentAPI.getOwnerDepartments(limit),
      { staleTimeMs: SWR_STALE_TIME_MS }
    );
    return data;
  }, [getDbCacheScope]);

  const getLocationsCached = useCallback(async (branchNo) => {
    const safeBranchNo = String(branchNo ?? '').trim();
    const cacheKey = buildCacheKey('locations-by-branch', getDbCacheScope(), safeBranchNo);
    const { data } = await getOrFetchSWR(
      cacheKey,
      () => equipmentAPI.getLocations(branchNo),
      { staleTimeMs: SWR_STALE_TIME_MS }
    );
    return data;
  }, [getDbCacheScope]);

  const getModelsCached = useCallback(async (typeNo, ciType = 1) => {
    const safeTypeNo = Number(typeNo || 0);
    const safeCiType = Number(ciType || 1);
    const cacheKey = buildCacheKey('models-by-type', getDbCacheScope(), safeTypeNo, safeCiType);
    const { data } = await getOrFetchSWR(
      cacheKey,
      () => equipmentAPI.getModels(typeNo, safeCiType),
      { staleTimeMs: SWR_STALE_TIME_MS }
    );
    return data;
  }, [getDbCacheScope]);

  const loadDetailedItemsByInvNos = useCallback(async (invNos) => {
    const invNoList = Array.from(
      new Set((invNos || []).map((value) => String(value || '').trim()).filter(Boolean))
    );
    const detailsMap = new Map();
    const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key);
    const hasPartNoField = (obj) => hasOwn(obj, 'PART_NO') || hasOwn(obj, 'part_no');
    const hasEmployeeDeptField = (obj) =>
      hasOwn(obj, 'OWNER_DEPT') || hasOwn(obj, 'employee_dept') || hasOwn(obj, 'owner_dept');
    const hasVendorField = (obj) =>
      hasOwn(obj, 'VENDOR_NAME') || hasOwn(obj, 'vendor_name') || hasOwn(obj, 'MANUFACTURER') || hasOwn(obj, 'manufacturer');
    const hasNetworkMetaFields = (obj) =>
      hasOwn(obj, 'MAC_ADDRESS') ||
      hasOwn(obj, 'mac_address') ||
      hasOwn(obj, 'NETBIOS_NAME') ||
      hasOwn(obj, 'network_name') ||
      hasOwn(obj, 'DOMAIN_NAME') ||
      hasOwn(obj, 'domain_name');

    invNoList.forEach((invNo) => {
      const existingItem = findEquipmentByInvNo(invNo);
      if (existingItem) {
        detailsMap.set(invNo, existingItem);
      }
    });

    const missingInvNos = invNoList.filter((invNo) => {
      const item = detailsMap.get(invNo);
      if (!item) return true;
      const hasId = item?.ID !== undefined && item?.ID !== null;
      return !hasId || !hasPartNoField(item) || !hasEmployeeDeptField(item) || !hasVendorField(item) || !hasNetworkMetaFields(item);
    });

    if (missingInvNos.length === 0) {
      return detailsMap;
    }

    try {
      const response = await equipmentAPI.getByInvNos(missingInvNos);
      const rows = Array.isArray(response?.equipment) ? response.equipment : [];
      rows.forEach((row) => {
        const invNo = toInvNo(row);
        if (!invNo) return;
        const prev = detailsMap.get(invNo) || {};
        detailsMap.set(invNo, { ...prev, ...row });
      });
    } catch (error) {
      console.error('Error loading detailed items in batch:', error);
    }

    return detailsMap;
  }, [findEquipmentByInvNo]);

  // Load detail data - first from loaded equipment, then from API batch endpoint
  useEffect(() => {
    if (detailModal.open && detailModal.invNo) {
      let canceled = false;

      // First try to show data from already loaded equipment
      const item = findEquipmentByInvNo(detailModal.invNo);
      if (item) {
        setDetailModal(prev => ({ ...prev, data: item, loading: false }));
      }

      // Always fetch detail from API to keep modal data up to date
      const fetchDetail = async () => {
        try {
          const detailsMap = await loadDetailedItemsByInvNos([detailModal.invNo]);
          const data = detailsMap.get(String(detailModal.invNo)) || item || null;
          if (!canceled) {
            setDetailModal(prev => ({ ...prev, data, loading: false }));
          }
        } catch (error) {
          if (!canceled) {
            console.error('Error fetching equipment detail:', error);
            setDetailModal(prev => ({ ...prev, loading: false }));
          }
        }
      };
      fetchDetail();

      return () => {
        canceled = true;
      };
    }
  }, [detailModal.open, detailModal.invNo, findEquipmentByInvNo, loadDetailedItemsByInvNos]);

  const statusOptions = useMemo(
    () =>
      (statuses || [])
        .map((status) => ({
          status_no: toNumberOrNull(status?.STATUS_NO ?? status?.status_no),
          status_name: String(status?.STATUS_NAME || status?.status_name || status?.DESCR || ''),
        }))
        .filter((status) => status.status_no !== null),
    [statuses]
  );

  const branchOptions = useMemo(
    () =>
      (branches || [])
        .map((branch) => ({
          branch_no: toIdOrNull(branch?.BRANCH_NO ?? branch?.branch_no ?? branch?.id),
          branch_name: String(branch?.BRANCH_NAME || branch?.branch_name || branch?.name || ''),
        }))
        .filter((branch) => branch.branch_no !== null),
    [branches]
  );

  const locationOptions = useMemo(
    () =>
      (detailLocations || [])
        .map(normalizeLocationOption)
        .filter((location) => location.loc_no !== null)
        .sort(sortLocationOptions),
    [detailLocations]
  );

  const transferLocationOptions = useMemo(
    () =>
      (transferLocations || [])
        .map(normalizeLocationOption)
        .filter((location) => location.loc_no !== null)
        .sort(sortLocationOptions),
    [transferLocations]
  );

  const transferSourceDefaults = useMemo(() => {
    const invNos = normalizeActionTargets(selectedItems, actionModal.invNo);
    const items = invNos
      .map((invNo) => findEquipmentByInvNo(invNo))
      .filter(Boolean);
    if (items.length === 0) {
      return {
        branch_no: null,
        loc_no: null,
        branch_name: '',
        location_name: '',
        mixed_branch: false,
        mixed_location: false,
      };
    }

    const firstItem = items[0];
    const firstBranchName = String(readFirst(firstItem, ['BRANCH_NAME', 'branch_name'], '') || '').trim();
    const firstLocationName = String(
      readFirst(firstItem, ['LOCATION_NAME', 'location_name', 'LOCATION', 'location'], '') || ''
    ).trim();
    const firstBranchNoRaw = toIdOrNull(readFirst(firstItem, ['BRANCH_NO', 'branch_no'], null));
    const firstLocNo = toIdOrNull(readFirst(firstItem, ['LOC_NO', 'loc_no'], null));

    const matchedBranch = branchOptions.find(
      (option) => normalizeText(option.branch_name) === normalizeText(firstBranchName)
    );
    const firstBranchNo = matchedBranch?.branch_no ?? firstBranchNoRaw ?? null;

    const mixedBranch = items.some((item) => {
      const branchName = String(readFirst(item, ['BRANCH_NAME', 'branch_name'], '') || '').trim();
      return normalizeText(branchName) !== normalizeText(firstBranchName);
    });
    const mixedLocation = items.some((item) => {
      const locationName = String(
        readFirst(item, ['LOCATION_NAME', 'location_name', 'LOCATION', 'location'], '') || ''
      ).trim();
      return normalizeText(locationName) !== normalizeText(firstLocationName);
    });

    return {
      branch_no: firstBranchNo,
      loc_no: firstLocNo,
      branch_name: firstBranchName,
      location_name: firstLocationName,
      mixed_branch: mixedBranch,
      mixed_location: mixedLocation,
    };
  }, [selectedItems, actionModal.invNo, findEquipmentByInvNo, branchOptions]);

  const typeOptions = useMemo(
    () =>
      (equipmentTypes || [])
        .map((type) => ({
          ci_type: toNumberOrNull(type?.CI_TYPE ?? type?.ci_type),
          type_no: toNumberOrNull(type?.TYPE_NO ?? type?.type_no),
          type_name: String(type?.TYPE_NAME || type?.type_name || ''),
        }))
        .filter((type) => type.type_no !== null),
    [equipmentTypes]
  );

  const equipmentTypeOptions = useMemo(
    () => typeOptions.filter((type) => type.ci_type === 1),
    [typeOptions]
  );

  const consumableTypeOptions = useMemo(
    () => typeOptions.filter((type) => type.ci_type === 4),
    [typeOptions]
  );

  const modelOptions = useMemo(
    () =>
      (detailModels || [])
        .map((model) => ({
          model_no: toNumberOrNull(model?.MODEL_NO ?? model?.model_no),
          model_name: String(model?.MODEL_NAME || model?.model_name || ''),
          type_no: toNumberOrNull(model?.TYPE_NO ?? model?.type_no),
        }))
        .filter((model) => model.model_no !== null),
    [detailModels]
  );

  const addLocationOptions = useMemo(
    () =>
      (addLocations || [])
        .map(normalizeLocationOption)
        .filter((location) => location.loc_no !== null)
        .sort(sortLocationOptions),
    [addLocations]
  );

  const addModelOptions = useMemo(
    () =>
      (addModels || [])
        .map((model) => ({
          model_no: toNumberOrNull(model?.MODEL_NO ?? model?.model_no),
          model_name: String(model?.MODEL_NAME || model?.model_name || ''),
        }))
        .filter((model) => model.model_name),
    [addModels]
  );

  const addConsumableLocationOptions = useMemo(
    () =>
      (addConsumableLocations || [])
        .map(normalizeLocationOption)
        .filter((location) => location.loc_no !== null)
        .sort(sortLocationOptions),
    [addConsumableLocations]
  );

  const addConsumableModelOptions = useMemo(
    () =>
      (addConsumableModels || [])
        .map((model) => ({
          model_no: toNumberOrNull(model?.MODEL_NO ?? model?.model_no),
          model_name: String(model?.MODEL_NAME || model?.model_name || ''),
        }))
        .filter((model) => model.model_name),
    [addConsumableModels]
  );

  const selectedAddEmployeeOption = useMemo(() => {
    if (!addEquipmentForm?.employee_no) return null;
    const matched = addEmployeeOptions.find(
      (owner) => toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no) === toNumberOrNull(addEquipmentForm.employee_no)
    );
    if (matched) return matched;
    return {
      OWNER_NO: addEquipmentForm.employee_no,
      OWNER_DISPLAY_NAME: addEquipmentForm.employee_name || 'Не указан',
      OWNER_DEPT: addEquipmentForm.employee_dept || '',
    };
  }, [addEmployeeOptions, addEquipmentForm?.employee_no, addEquipmentForm?.employee_name, addEquipmentForm?.employee_dept]);

  const addUsesManualEmployee = useMemo(
    () => !addEquipmentForm?.employee_no && String(addEquipmentForm?.employee_name || '').trim().length >= 2,
    [addEquipmentForm?.employee_no, addEquipmentForm?.employee_name]
  );

  const addUsesManualModel = useMemo(
    () =>
      !addEquipmentForm?.model_no &&
      String(addEquipmentForm?.model_name || '').trim().length >= 2 &&
      toNumberOrNull(addEquipmentForm?.type_no) !== null,
    [addEquipmentForm?.model_no, addEquipmentForm?.model_name, addEquipmentForm?.type_no]
  );

  const normalizeDetailComparable = useCallback((formState) => ({
    type_no: toNumberOrNull(formState?.type_no),
    model_no: toNumberOrNull(formState?.model_no),
    serial_no: String(formState?.serial_no || '').trim(),
    hw_serial_no: String(formState?.hw_serial_no || '').trim(),
    part_no: String(formState?.part_no || '').trim(),
    ip_address: String(formState?.ip_address || '').trim(),
    mac_address: String(formState?.mac_address || '').trim(),
    network_name: String(formState?.network_name || '').trim(),
    description: String(formState?.description || '').trim(),
    status_no: toNumberOrNull(formState?.status_no),
    empl_no: toNumberOrNull(formState?.empl_no),
    branch_no: toIdOrNull(formState?.branch_no),
    loc_no: toIdOrNull(formState?.loc_no),
  }), []);

  const detailHasChanges = useMemo(() => {
    if (!detailForm || !detailInitialForm) return false;
    const current = normalizeDetailComparable(detailForm);
    const initial = normalizeDetailComparable(detailInitialForm);
    return Object.keys(current).some((key) => current[key] !== initial[key]);
  }, [detailForm, detailInitialForm, normalizeDetailComparable]);

  const detailQrText = useMemo(
    () => (detailModal?.data ? buildEquipmentQrText(detailModal.data) : ''),
    [detailModal?.data]
  );

  const detailQrUrl = useMemo(
    () => buildEquipmentQrUrl(detailQrText),
    [detailQrText]
  );

  const detailQrFileName = useMemo(() => {
    const invNo = String(readFirst(detailModal?.data, ['INV_NO', 'inv_no'], '') || '').trim();
    const safeInvNo = (invNo || 'equipment').replace(/[^0-9A-Za-z_-]+/g, '_');
    return `qr_${safeInvNo}.png`;
  }, [detailModal?.data]);

  const handleDetailClose = useCallback(() => {
    setDetailModal({ open: false, data: null, loading: false, invNo: null });
    setDetailEditMode(false);
    setDetailSaving(false);
    setDetailError('');
    setDetailSuccess('');
    setDetailForm(null);
    setDetailInitialForm(null);
    setDetailLocations([]);
    setDetailModels([]);
    setDetailModelsLoading(false);
    setDetailEmployeeOptions([]);
    setDetailEmployeeInput('');
    setDetailEmployeeLoading(false);
    setDetailTab('general');
    setDetailActs([]);
    setDetailActsLoading(false);
    setDetailActsError('');
    setDetailActsLoadedInvNo('');
    setDetailActOpeningDocNo('');
    setDetailActFieldsOpen(false);
    setDetailActSelected(null);
    setDetailQrOpen(false);
  }, []);

  const handleDetailCancel = useCallback(() => {
    if (detailInitialForm) {
      setDetailForm(detailInitialForm);
    }
    setDetailError('');
    setDetailSuccess('');
    setDetailEditMode(false);
  }, [detailInitialForm]);

  useEffect(() => {
    if (!detailModal.open || !detailModal.data) return;
    const formState = buildDetailFormState(detailModal.data);
    setDetailForm(formState);
    setDetailInitialForm(formState);
    setDetailEditMode(false);
    setDetailError('');
    setDetailSuccess('');

    if (formState.empl_no) {
      setDetailEmployeeOptions([
        {
          OWNER_NO: formState.empl_no,
          OWNER_DISPLAY_NAME: formState.employee_name || 'Не указан',
          OWNER_DEPT: formState.employee_dept || '',
        },
      ]);
    } else {
      setDetailEmployeeOptions([]);
    }

    if (formState.model_no) {
      setDetailModels([
        {
          MODEL_NO: formState.model_no,
          MODEL_NAME: formState.model_name || 'Не указана',
          TYPE_NO: formState.type_no,
        },
      ]);
    } else {
      setDetailModels([]);
    }
  }, [detailModal.open, detailModal.data]);

  useEffect(() => {
    if (!detailModal.open || detailTab !== 'acts' || !detailModal.invNo) return;
    if (detailActsLoadedInvNo === detailModal.invNo) return;

    let canceled = false;
    setDetailActsLoading(true);
    setDetailActsError('');

    const loadActs = async () => {
      try {
        const response = await equipmentAPI.getEquipmentActs(detailModal.invNo);
        if (canceled) return;
        const nextActs = Array.isArray(response?.acts) ? response.acts : [];
        setDetailActs(nextActs);
        setDetailActsLoadedInvNo(detailModal.invNo);
      } catch (error) {
        console.error('Error loading equipment acts:', error);
        if (canceled) return;
        const apiDetail = error?.response?.data?.detail;
        setDetailActs([]);
        setDetailActsError(typeof apiDetail === 'string' ? apiDetail : 'Не удалось загрузить акты оборудования.');
      } finally {
        if (!canceled) {
          setDetailActsLoading(false);
        }
      }
    };

    loadActs();
    return () => {
      canceled = true;
    };
  }, [detailModal.open, detailModal.invNo, detailTab, detailActsLoadedInvNo]);

  useEffect(() => {
    if (!detailModal.open || !detailEditMode) return;
    if (!detailForm?.branch_no) {
      setDetailLocations([]);
      return;
    }

    let canceled = false;
    const loadLocations = async () => {
      try {
        const response = await getLocationsCached(detailForm.branch_no);
        if (!canceled) {
          const nextLocations = Array.isArray(response) ? response : [];
          setDetailLocations(nextLocations);
        }
      } catch (error) {
        console.error('Error loading locations for detail edit:', error);
        if (!canceled) {
          setDetailLocations([]);
        }
      }
    };

    loadLocations();
    return () => {
      canceled = true;
    };
  }, [detailModal.open, detailEditMode, detailForm?.branch_no]);

  useEffect(() => {
    if (!detailModal.open || !detailEditMode) return;
    if (!detailForm?.type_no) {
      setDetailModels([]);
      setDetailModelsLoading(false);
      return;
    }

    let canceled = false;
    setDetailModelsLoading(true);
    const loadModels = async () => {
      try {
        const response = await getModelsCached(detailForm.type_no);
        if (!canceled) {
          const nextModels = Array.isArray(response?.models) ? response.models : [];
          setDetailModels(nextModels);
        }
      } catch (error) {
        console.error('Error loading models for detail edit:', error);
        if (!canceled) {
          setDetailModels([]);
        }
      } finally {
        if (!canceled) {
          setDetailModelsLoading(false);
        }
      }
    };

    loadModels();
    return () => {
      canceled = true;
    };
  }, [detailModal.open, detailEditMode, detailForm?.type_no]);

  useEffect(() => {
    if (!detailModal.open || !detailEditMode) return;
    const query = String(detailEmployeeInput || '').trim();
    if (query.length < 2) {
      setDetailEmployeeLoading(false);
      return;
    }

    let canceled = false;
    setDetailEmployeeLoading(true);
    const timer = setTimeout(async () => {
      try {
        const response = await searchOwnersCached(query, 20);
        if (canceled) return;
        const owners = Array.isArray(response?.owners) ? response.owners : [];
        const currentOption = detailForm?.empl_no ? [{
          OWNER_NO: detailForm.empl_no,
          OWNER_DISPLAY_NAME: detailForm.employee_name || 'Не указан',
          OWNER_DEPT: detailForm.employee_dept || '',
        }] : [];
        const merged = [...currentOption, ...owners].filter((owner, index, arr) => {
          const ownerNo = toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no);
          return ownerNo !== null && arr.findIndex((item) => toNumberOrNull(item?.OWNER_NO ?? item?.owner_no) === ownerNo) === index;
        });
        setDetailEmployeeOptions(merged);
      } catch (error) {
        console.error('Error searching owners:', error);
      } finally {
        if (!canceled) {
          setDetailEmployeeLoading(false);
        }
      }
    }, 280);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [detailModal.open, detailEditMode, detailEmployeeInput, detailForm?.empl_no, detailForm?.employee_name, detailForm?.employee_dept]);

  useEffect(() => {
    if (!actionModal.open || actionModal.type !== 'transfer' || transferResult) return;
    const query = String(transferEmployeeInput || '').trim();
    if (query.length < 2) {
      setTransferEmployeeLoading(false);
      return;
    }

    let canceled = false;
    setTransferEmployeeLoading(true);
    const timer = setTimeout(async () => {
      try {
        const response = await searchOwnersCached(query, 20);
        if (canceled) return;
        const owners = Array.isArray(response?.owners) ? response.owners : [];
        const currentOption = newEmployeeNo ? [{
          OWNER_NO: newEmployeeNo,
          OWNER_DISPLAY_NAME: newEmployee || 'Не указан',
          OWNER_DEPT: '',
        }] : [];
        const merged = [...currentOption, ...owners].filter((owner, index, arr) => {
          const ownerNo = toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no);
          return ownerNo !== null && arr.findIndex((item) => toNumberOrNull(item?.OWNER_NO ?? item?.owner_no) === ownerNo) === index;
        });
        setTransferEmployeeOptions(merged);
      } catch (error) {
        console.error('Error searching transfer employees:', error);
      } finally {
        if (!canceled) {
          setTransferEmployeeLoading(false);
        }
      }
    }, 280);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [actionModal.open, actionModal.type, transferResult, transferEmployeeInput, newEmployeeNo, newEmployee]);

  useEffect(() => {
    if (!actionModal.open || actionModal.type !== 'transfer' || transferResult) return;

    let canceled = false;
    setTransferDepartmentLoading(true);
    const loadDepartments = async () => {
      try {
        const response = await getOwnerDepartmentsCached(1000);
        if (canceled) return;
        const raw = Array.isArray(response?.departments) ? response.departments : [];
        const normalized = raw
          .map((dept) => String(dept || '').trim())
          .filter(Boolean)
          .filter((dept, index, arr) => arr.findIndex((entry) => normalizeText(entry) === normalizeText(dept)) === index);
        setTransferDepartmentOptions(normalized);
      } catch (error) {
        console.error('Error loading owner departments:', error);
        if (!canceled) {
          setTransferDepartmentOptions([]);
        }
      } finally {
        if (!canceled) {
          setTransferDepartmentLoading(false);
        }
      }
    };

    loadDepartments();
    return () => {
      canceled = true;
    };
  }, [actionModal.open, actionModal.type, transferResult]);

  useEffect(() => {
    if (!actionModal.open || actionModal.type !== 'transfer' || transferResult) return;
    if (transferBranchNo !== null || transferLocationNo !== null) return;
    setTransferBranchNo(transferSourceDefaults.branch_no);
    setTransferLocationNo(transferSourceDefaults.loc_no);
  }, [
    actionModal.open,
    actionModal.type,
    transferResult,
    transferBranchNo,
    transferLocationNo,
    transferSourceDefaults.branch_no,
    transferSourceDefaults.loc_no,
  ]);

  useEffect(() => {
    if (!actionModal.open || actionModal.type !== 'transfer' || transferResult) return;
    if (!transferBranchNo) {
      setTransferLocations([]);
      setTransferLocationsLoading(false);
      setTransferLocationNo(null);
      return;
    }

    let canceled = false;
    setTransferLocationsLoading(true);
    const loadLocations = async () => {
      try {
        const response = await getLocationsCached(transferBranchNo);
        if (canceled) return;
        const nextLocations = Array.isArray(response) ? response : [];
        setTransferLocations(nextLocations);

        setTransferLocationNo((prevLocNo) => {
          const normalizedPrev = toIdOrNull(prevLocNo);
          if (
            normalizedPrev &&
            nextLocations.some(
              (location) => toIdOrNull(location?.LOC_NO ?? location?.loc_no) === normalizedPrev
            )
          ) {
            return normalizedPrev;
          }

          const byDefaultNo = transferSourceDefaults.loc_no
            ? nextLocations.find(
              (location) => toIdOrNull(location?.LOC_NO ?? location?.loc_no) === transferSourceDefaults.loc_no
            )
            : null;
          if (byDefaultNo) {
            return toIdOrNull(byDefaultNo?.LOC_NO ?? byDefaultNo?.loc_no);
          }

          const byDefaultName = transferSourceDefaults.location_name
            ? nextLocations.find(
              (location) =>
                normalizeText(location?.LOC_NAME ?? location?.loc_name ?? location?.DESCR) ===
                normalizeText(transferSourceDefaults.location_name)
            )
            : null;
          if (byDefaultName) {
            return toIdOrNull(byDefaultName?.LOC_NO ?? byDefaultName?.loc_no);
          }

          return toIdOrNull(nextLocations[0]?.LOC_NO ?? nextLocations[0]?.loc_no);
        });
      } catch (error) {
        console.error('Error loading transfer locations:', error);
        if (!canceled) {
          setTransferLocations([]);
          setTransferLocationNo(null);
        }
      } finally {
        if (!canceled) {
          setTransferLocationsLoading(false);
        }
      }
    };

    loadLocations();
    return () => {
      canceled = true;
    };
  }, [
    actionModal.open,
    actionModal.type,
    transferResult,
    transferBranchNo,
    transferSourceDefaults.loc_no,
    transferSourceDefaults.location_name,
  ]);

  useEffect(() => {
    if (!actionModal.open || actionModal.type !== 'transfer') return;
    if (transferEmailMode !== 'employee') {
      setTransferRecipientInput('');
      setTransferRecipientOptions([]);
      setTransferRecipient(null);
      setTransferRecipientLoading(false);
      return;
    }

    const query = String(transferRecipientInput || '').trim();
    if (query.length < 2) {
      setTransferRecipientLoading(false);
      return;
    }

    let canceled = false;
    setTransferRecipientLoading(true);
    const timer = setTimeout(async () => {
      try {
        const response = await searchOwnersCached(query, 20);
        if (canceled) return;
        const owners = Array.isArray(response?.owners) ? response.owners : [];
        setTransferRecipientOptions(owners);
      } catch (error) {
        console.error('Error searching email recipient employees:', error);
      } finally {
        if (!canceled) {
          setTransferRecipientLoading(false);
        }
      }
    }, 280);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [actionModal.open, actionModal.type, transferEmailMode, transferRecipientInput]);

  useEffect(() => {
    if (!uploadActModalOpen || !uploadActCommitResult?.doc_no) return;

    const query = String(uploadActEmailRecipientsInput || '').trim();
    if (query.length < 2) {
      setUploadActEmailRecipientOptions([]);
      setUploadActEmailRecipientsLoading(false);
      return;
    }

    let canceled = false;
    setUploadActEmailRecipientsLoading(true);
    const timer = setTimeout(async () => {
      try {
        const response = await searchOwnersCached(query, 20);
        if (canceled) return;
        const owners = Array.isArray(response?.owners) ? response.owners : [];
        setUploadActEmailRecipientOptions(owners);
      } catch (error) {
        console.error('Error searching uploaded-act recipients:', error);
        if (!canceled) {
          setUploadActEmailRecipientOptions([]);
        }
      } finally {
        if (!canceled) {
          setUploadActEmailRecipientsLoading(false);
        }
      }
    }, 280);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [uploadActModalOpen, uploadActCommitResult?.doc_no, uploadActEmailRecipientsInput]);

  const buildAddEquipmentDefaults = useCallback(() => {
    const defaultBranch = selectedBranch
      ? branchOptions.find((option) => normalizeText(option.branch_name) === normalizeText(selectedBranch))
      : null;
    const defaultStatus = statusOptions.find((option) =>
      normalizeText(option.status_name).includes('эксплуата')
    ) || statusOptions[0];

    return {
      ...createAddEquipmentInitialForm(),
      branch_no: defaultBranch?.branch_no || '',
      status_no: defaultStatus?.status_no !== undefined && defaultStatus?.status_no !== null
        ? String(defaultStatus.status_no)
        : '',
    };
  }, [branchOptions, selectedBranch, statusOptions]);

  const buildAddConsumableDefaults = useCallback(() => {
    const defaultBranch = selectedBranch
      ? branchOptions.find((option) => normalizeText(option.branch_name) === normalizeText(selectedBranch))
      : null;
    return {
      ...createAddConsumableInitialForm(),
      branch_no: defaultBranch?.branch_no || '',
    };
  }, [branchOptions, selectedBranch]);

  const [identifyPCLoading, setIdentifyPCLoading] = useState(false);

  const handleIdentifyWorkspace = async () => {
    try {
      setIdentifyPCLoading(true);
      const response = await equipmentAPI.identifyWorkspace();

      if (response.success && response.owner_info && response.owner_info.owner_name) {
        // Set the search query to the owner's name and apply filter
        const ownerName = response.owner_info.owner_name;
        setSearchQuery(ownerName);
        applySearchDebounced.cancel?.();
        runSearchNow(ownerName);

        // Auto-select linked components (if any)
        if (Array.isArray(response.linked_inv_nos) && response.linked_inv_nos.length > 0) {
          // Give search filter a tiny moment to apply before selecting items
          setTimeout(() => {
            setSelectedItems(response.linked_inv_nos.map(String));
          }, 300);
        }

        // Show success toast
        setAddEquipmentToast({
          open: true,
          message: `${response.message}. Найдено ${response.total_items_count} ед. оборудования. Связанные отмечены галочками.`,
        });
      } else {
        // Did not find or failed
        setUploadActToast({
          open: true,
          message: response.message || 'ПК не найден по вашему IP.',
          severity: 'error'
        });
      }
    } catch (err) {
      console.error('Error identifying workspace:', err);
      setUploadActToast({
        open: true,
        message: 'Ошибка при определении рабочего места: ' + (err.response?.data?.detail || err.message),
        severity: 'error'
      });
    } finally {
      setIdentifyPCLoading(false);
    }
  };

  const openAddEquipmentModal = useCallback(() => {
    if (!canDatabaseWrite) return;
    setAddEquipmentError('');
    setAddEquipmentSuccess('');
    setAddEmployeeInput('');
    setAddEmployeeOptions([]);
    setAddEmployeeLoading(false);
    setAddLocations([]);
    setAddLocationsLoading(false);
    setAddModels([]);
    setAddModelsLoading(false);
    setAddEquipmentForm(buildAddEquipmentDefaults());
    setAddEquipmentModalOpen(true);
  }, [buildAddEquipmentDefaults, canDatabaseWrite]);

  const closeAddEquipmentModal = useCallback(() => {
    setAddEquipmentModalOpen(false);
    setAddEquipmentLoading(false);
    setAddEquipmentError('');
    setAddEquipmentSuccess('');
    setAddEmployeeInput('');
    setAddEmployeeOptions([]);
    setAddEmployeeLoading(false);
    setAddLocations([]);
    setAddLocationsLoading(false);
    setAddModels([]);
    setAddModelsLoading(false);
    setAddEquipmentForm(createAddEquipmentInitialForm());
  }, []);

  const openAddConsumableModal = useCallback(() => {
    if (!canDatabaseWrite) return;
    setAddConsumableError('');
    setAddConsumableSuccess('');
    setAddConsumableForm(buildAddConsumableDefaults());
    setAddConsumableLocations([]);
    setAddConsumableModels([]);
    setAddConsumableLocationsLoading(false);
    setAddConsumableModelsLoading(false);
    setAddConsumableModalOpen(true);
  }, [buildAddConsumableDefaults, canDatabaseWrite]);

  const closeAddConsumableModal = useCallback(() => {
    setAddConsumableModalOpen(false);
    setAddConsumableLoading(false);
    setAddConsumableError('');
    setAddConsumableSuccess('');
    setAddConsumableLocations([]);
    setAddConsumableModels([]);
    setAddConsumableLocationsLoading(false);
    setAddConsumableModelsLoading(false);
    setAddConsumableForm(createAddConsumableInitialForm());
  }, []);

  const openEditConsumableQtyModal = useCallback((item) => {
    if (!canDatabaseWrite) return;
    if (!item || typeof item !== 'object') return;
    const currentQty = Math.max(0, Math.trunc(readQty(item, 0)));
    setEditConsumableQtyError('');
    setEditConsumableQtyLoading(false);
    setEditConsumableQtyValue(String(currentQty));
    setEditConsumableQtyModal({ open: true, item });
  }, [canDatabaseWrite]);

  const closeEditConsumableQtyModal = useCallback(() => {
    setEditConsumableQtyModal({ open: false, item: null });
    setEditConsumableQtyValue('');
    setEditConsumableQtyLoading(false);
    setEditConsumableQtyError('');
  }, []);

  useEffect(() => {
    if (!addEquipmentModalOpen) return;
    const query = String(addEmployeeInput || '').trim();
    if (query.length < 2) {
      setAddEmployeeLoading(false);
      return;
    }

    let canceled = false;
    setAddEmployeeLoading(true);
    const timer = setTimeout(async () => {
      try {
        const response = await searchOwnersCached(query, 20);
        if (canceled) return;
        const owners = Array.isArray(response?.owners) ? response.owners : [];
        const currentOption = addEquipmentForm?.employee_no ? [{
          OWNER_NO: addEquipmentForm.employee_no,
          OWNER_DISPLAY_NAME: addEquipmentForm.employee_name || 'Не указан',
          OWNER_DEPT: '',
        }] : [];
        const merged = [...currentOption, ...owners].filter((owner, index, arr) => {
          const ownerNo = toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no);
          return ownerNo !== null && arr.findIndex((item) => toNumberOrNull(item?.OWNER_NO ?? item?.owner_no) === ownerNo) === index;
        });
        setAddEmployeeOptions(merged);
      } catch (error) {
        console.error('Error searching add-equipment employees:', error);
      } finally {
        if (!canceled) {
          setAddEmployeeLoading(false);
        }
      }
    }, 280);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [addEquipmentModalOpen, addEmployeeInput, addEquipmentForm?.employee_no, addEquipmentForm?.employee_name]);

  useEffect(() => {
    if (!addEquipmentModalOpen) return;
    if (!addEquipmentForm?.branch_no) {
      setAddLocations([]);
      setAddLocationsLoading(false);
      return;
    }

    let canceled = false;
    setAddLocationsLoading(true);
    const loadLocations = async () => {
      try {
        const response = await getLocationsCached(addEquipmentForm.branch_no);
        if (canceled) return;
        const nextLocations = Array.isArray(response) ? response : [];
        setAddLocations(nextLocations);
        const currentLocNo = toIdOrNull(addEquipmentForm.loc_no);
        if (
          currentLocNo &&
          nextLocations.some((location) => toIdOrNull(location?.LOC_NO ?? location?.loc_no) === currentLocNo)
        ) {
          return;
        }
        const firstLocNo = toIdOrNull(nextLocations[0]?.LOC_NO ?? nextLocations[0]?.loc_no) || '';
        setAddEquipmentForm((prev) => ({ ...prev, loc_no: firstLocNo }));
      } catch (error) {
        console.error('Error loading add-equipment locations:', error);
        if (!canceled) {
          setAddLocations([]);
          setAddEquipmentForm((prev) => ({ ...prev, loc_no: '' }));
        }
      } finally {
        if (!canceled) {
          setAddLocationsLoading(false);
        }
      }
    };

    loadLocations();
    return () => {
      canceled = true;
    };
  }, [addEquipmentModalOpen, addEquipmentForm?.branch_no, addEquipmentForm?.loc_no]);

  useEffect(() => {
    if (!addEquipmentModalOpen) return;
    if (!addEquipmentForm?.type_no) {
      setAddModels([]);
      setAddModelsLoading(false);
      return;
    }

    let canceled = false;
    setAddModelsLoading(true);
    const loadModels = async () => {
      try {
        const response = await getModelsCached(addEquipmentForm.type_no);
        if (canceled) return;
        const nextModels = Array.isArray(response?.models) ? response.models : [];
        setAddModels(nextModels);
      } catch (error) {
        console.error('Error loading add-equipment models:', error);
        if (!canceled) {
          setAddModels([]);
        }
      } finally {
        if (!canceled) {
          setAddModelsLoading(false);
        }
      }
    };

    loadModels();
    return () => {
      canceled = true;
    };
  }, [addEquipmentModalOpen, addEquipmentForm?.type_no]);

  useEffect(() => {
    if (!addConsumableModalOpen) return;
    if (!addConsumableForm?.branch_no) {
      setAddConsumableLocations([]);
      setAddConsumableLocationsLoading(false);
      return;
    }

    let canceled = false;
    setAddConsumableLocationsLoading(true);
    const loadLocations = async () => {
      try {
        const response = await getLocationsCached(addConsumableForm.branch_no);
        if (canceled) return;
        const nextLocations = Array.isArray(response) ? response : [];
        setAddConsumableLocations(nextLocations);
        const currentLocNo = toIdOrNull(addConsumableForm.loc_no);
        if (
          currentLocNo &&
          nextLocations.some((location) => toIdOrNull(location?.LOC_NO ?? location?.loc_no) === currentLocNo)
        ) {
          return;
        }
        const firstLocNo = toIdOrNull(nextLocations[0]?.LOC_NO ?? nextLocations[0]?.loc_no) || '';
        setAddConsumableForm((prev) => ({ ...prev, loc_no: firstLocNo }));
      } catch (error) {
        console.error('Error loading add-consumable locations:', error);
        if (!canceled) {
          setAddConsumableLocations([]);
          setAddConsumableForm((prev) => ({ ...prev, loc_no: '' }));
        }
      } finally {
        if (!canceled) {
          setAddConsumableLocationsLoading(false);
        }
      }
    };

    loadLocations();
    return () => {
      canceled = true;
    };
  }, [addConsumableModalOpen, addConsumableForm?.branch_no, addConsumableForm?.loc_no, getLocationsCached]);

  useEffect(() => {
    if (!addConsumableModalOpen) return;
    if (!addConsumableForm?.type_no) {
      setAddConsumableModels([]);
      setAddConsumableModelsLoading(false);
      return;
    }

    let canceled = false;
    setAddConsumableModelsLoading(true);
    const loadModels = async () => {
      try {
        const response = await getModelsCached(addConsumableForm.type_no, 4);
        if (canceled) return;
        const nextModels = Array.isArray(response?.models) ? response.models : [];
        setAddConsumableModels(nextModels);
      } catch (error) {
        console.error('Error loading add-consumable models:', error);
        if (!canceled) {
          setAddConsumableModels([]);
        }
      } finally {
        if (!canceled) {
          setAddConsumableModelsLoading(false);
        }
      }
    };

    loadModels();
    return () => {
      canceled = true;
    };
  }, [addConsumableModalOpen, addConsumableForm?.type_no, getModelsCached]);

  const handleAddEquipmentSubmit = useCallback(async () => {
    if (!canDatabaseWrite) {
      setAddEquipmentError('Недостаточно прав для изменения данных.');
      return;
    }
    const serialNumber = String(addEquipmentForm.serial_number || '').trim();
    const employeeName = String(addEquipmentForm.employee_name || '').trim();
    const modelName = String(addEquipmentForm.model_name || '').trim();
    const typeNo = toNumberOrNull(addEquipmentForm.type_no);
    const statusNo = toNumberOrNull(addEquipmentForm.status_no);
    const branchNo = toIdOrNull(addEquipmentForm.branch_no);
    const locNo = toIdOrNull(addEquipmentForm.loc_no);

    if (!serialNumber) {
      setAddEquipmentError('Укажите серийный номер.');
      return;
    }
    if (!employeeName) {
      setAddEquipmentError('Выберите или введите сотрудника.');
      return;
    }
    if (typeNo === null) {
      setAddEquipmentError('Выберите тип оборудования.');
      return;
    }
    if (!modelName) {
      setAddEquipmentError('Укажите модель оборудования.');
      return;
    }
    if (statusNo === null) {
      setAddEquipmentError('Выберите статус оборудования.');
      return;
    }
    if (!branchNo) {
      setAddEquipmentError('Выберите филиал.');
      return;
    }
    if (!locNo) {
      setAddEquipmentError('Выберите местоположение.');
      return;
    }

    setAddEquipmentLoading(true);
    setAddEquipmentError('');
    setAddEquipmentSuccess('');
    try {
      const response = await equipmentAPI.createEquipment({
        serial_no: serialNumber,
        employee_name: employeeName,
        employee_no: addEquipmentForm.employee_no || undefined,
        employee_dept: String(addEquipmentForm.employee_dept || '').trim() || undefined,
        branch_no: branchNo,
        loc_no: locNo,
        type_no: typeNo,
        model_name: modelName,
        model_no: addEquipmentForm.model_no || undefined,
        status_no: statusNo,
        part_no: String(addEquipmentForm.part_no || '').trim() || undefined,
        description: String(addEquipmentForm.description || '').trim() || undefined,
        ip_address: String(addEquipmentForm.ip_address || '').trim() || undefined,
        hw_serial_no: undefined,
      });

      const invNo = String(response?.inv_no || '').trim();
      const extra = [
        response?.created_owner ? 'создан сотрудник' : '',
        response?.created_model ? 'создана модель' : '',
      ].filter(Boolean).join(', ');
      const successMessage = (
        invNo
          ? `Оборудование добавлено. Инвентарный номер: ${invNo}${extra ? ` (${extra})` : ''}.`
          : `Оборудование добавлено.${extra ? ` (${extra})` : ''}`
      );
      setAddEquipmentSuccess(successMessage);
      setAddEquipmentToast({ open: true, message: successMessage });
      setAddEquipmentError('');
      setAddEquipmentForm(buildAddEquipmentDefaults());
      setAddEmployeeInput('');
      setAddEmployeeOptions([]);
      setAddLocations([]);
      setAddModels([]);
      await fetchAllEquipment({ force: true });
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setAddEquipmentError(typeof apiDetail === 'string' ? apiDetail : 'Не удалось добавить оборудование.');
    } finally {
      setAddEquipmentLoading(false);
    }
  }, [addEquipmentForm, buildAddEquipmentDefaults, canDatabaseWrite, fetchAllEquipment]);

  const handleAddConsumableSubmit = useCallback(async () => {
    if (!canDatabaseWrite) {
      setAddConsumableError('Недостаточно прав для изменения данных.');
      return;
    }
    const typeNo = toNumberOrNull(addConsumableForm.type_no);
    const branchNo = toIdOrNull(addConsumableForm.branch_no);
    const locNo = toIdOrNull(addConsumableForm.loc_no);
    const modelName = String(addConsumableForm.model_name || '').trim();
    const qty = Number(addConsumableForm.qty || 0);

    if (typeNo === null) {
      setAddConsumableError('Выберите тип расходника.');
      return;
    }
    if (!modelName) {
      setAddConsumableError('Укажите модель расходника.');
      return;
    }
    if (!branchNo) {
      setAddConsumableError('Выберите филиал.');
      return;
    }
    if (!locNo) {
      setAddConsumableError('Выберите местоположение.');
      return;
    }
    if (!Number.isFinite(qty) || qty <= 0) {
      setAddConsumableError('Количество должно быть больше 0.');
      return;
    }

    setAddConsumableLoading(true);
    setAddConsumableError('');
    setAddConsumableSuccess('');
    try {
      const response = await equipmentAPI.createConsumable({
        branch_no: branchNo,
        loc_no: locNo,
        type_no: typeNo,
        model_name: modelName,
        model_no: addConsumableForm.model_no || undefined,
        qty: Math.trunc(qty),
      });

      const invNo = String(response?.inv_no || '').trim();
      const successMessage = invNo
        ? `Расходник добавлен. Инвентарный номер: ${invNo}.`
        : 'Расходник добавлен.';

      setAddConsumableSuccess(successMessage);
      setAddConsumableToast({ open: true, message: successMessage });
      setAddConsumableForm(buildAddConsumableDefaults());
      setAddConsumableLocations([]);
      setAddConsumableModels([]);
      await fetchAllEquipment({ force: true });
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setAddConsumableError(typeof apiDetail === 'string' ? apiDetail : 'Не удалось добавить расходник.');
    } finally {
      setAddConsumableLoading(false);
    }
  }, [addConsumableForm, buildAddConsumableDefaults, canDatabaseWrite, fetchAllEquipment]);

  const handleEditConsumableQtySubmit = useCallback(async () => {
    if (!canDatabaseWrite) {
      setEditConsumableQtyError('Недостаточно прав для изменения данных.');
      return;
    }
    const item = editConsumableQtyModal.item;
    if (!item || typeof item !== 'object') {
      setEditConsumableQtyError('Не удалось определить выбранный расходник.');
      return;
    }

    const itemId = toNumberOrNull(readFirst(item, ['ID', 'id'], null));
    const invNo = String(readFirst(item, ['INV_NO', 'inv_no'], '') || '').trim();
    const parsedQty = Number(editConsumableQtyValue);

    if (!Number.isFinite(parsedQty) || parsedQty < 0 || !Number.isInteger(parsedQty)) {
      setEditConsumableQtyError('Количество должно быть целым числом 0 или больше.');
      return;
    }
    if (itemId === null && !invNo) {
      setEditConsumableQtyError('Не удалось определить ID или инвентарный номер расходника.');
      return;
    }

    const targetQty = Math.trunc(parsedQty);
    setEditConsumableQtyLoading(true);
    setEditConsumableQtyError('');
    try {
      await equipmentAPI.updateConsumableQty({
        item_id: itemId ?? undefined,
        inv_no: invNo || undefined,
        qty: targetQty,
      });

      const label = String(readFirst(item, ['MODEL_NAME', 'model_name'], '') || '').trim();
      const message = label
        ? `Количество обновлено: ${label} -> ${targetQty}.`
        : `Количество обновлено: ${targetQty}.`;
      setEditConsumableQtyToast({ open: true, message });
      closeEditConsumableQtyModal();
      await fetchAllEquipment({ force: true });
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setEditConsumableQtyError(
        typeof apiDetail === 'string' ? apiDetail : 'Не удалось обновить количество расходника.'
      );
    } finally {
      setEditConsumableQtyLoading(false);
    }
  }, [canDatabaseWrite, editConsumableQtyModal.item, editConsumableQtyValue, fetchAllEquipment, closeEditConsumableQtyModal]);

  const resetUploadActState = useCallback(() => {
    setUploadActFile(null);
    setUploadActDraft(null);
    setUploadActParsing(false);
    setUploadActCommitting(false);
    setUploadActError('');
    setUploadActCommitResult(null);
    setUploadActAutoEmail(true);
    setUploadActEmailSubject('');
    setUploadActEmailBody('');
    setUploadActEmailRecipientsInput('');
    setUploadActEmailRecipientOptions([]);
    setUploadActEmailRecipients([]);
    setUploadActEmailRecipientsLoading(false);
    setUploadActEmailLoading(false);
    setUploadActEmailError('');
    setUploadActEmailStatus('');
    setUploadActEmailLastRecipients([]);
    setUploadActEmailSummary({ mode: '', successCount: 0, failedCount: 0 });
    setUploadActForm({
      document_title: '',
      from_employee: '',
      to_employee: '',
      doc_date: '',
      equipment_inv_nos_text: '',
    });
  }, []);

  const openUploadActModal = useCallback(() => {
    if (!canDatabaseWrite) return;
    resetUploadActState();
    setUploadActModalOpen(true);
  }, [canDatabaseWrite, resetUploadActState]);

  const closeUploadActModal = useCallback(() => {
    setUploadActModalOpen(false);
    resetUploadActState();
  }, [resetUploadActState]);

  const handleUploadActFileSelect = useCallback((event) => {
    const nextFile = event?.target?.files?.[0] || null;
    setUploadActFile(nextFile);
    setUploadActDraft(null);
    setUploadActError('');
  }, []);

  const applyUploadActDraft = useCallback((draft) => {
    setUploadActDraft(draft);
    setUploadActForm({
      document_title: String(draft?.document_title || '').trim(),
      from_employee: String(draft?.from_employee || '').trim(),
      to_employee: String(draft?.to_employee || '').trim(),
      doc_date: String(draft?.doc_date || '').trim(),
      equipment_inv_nos_text: Array.isArray(draft?.equipment_inv_nos)
        ? draft.equipment_inv_nos.map((invNo) => String(invNo)).join(', ')
        : '',
    });
    setUploadActError('');
    setUploadActAutoEmail(true);
    uploadActAutoEmailRef.current = true;
  }, []);

  const isApiUnavailableForActParse = useCallback((error) => {
    const statusCode = Number(error?.response?.status || 0);
    if (!error?.response) return true;
    if (statusCode >= 500) return true;
    const detail = String(error?.response?.data?.detail || error?.message || '').toLowerCase();
    return (
      detail.includes('openrouter')
      || detail.includes('api')
      || detail.includes('timeout')
      || detail.includes('timed out')
    );
  }, []);

  const handleUploadActParse = useCallback(async (manualMode = false) => {
    if (!canDatabaseWrite) {
      setUploadActError('Недостаточно прав для изменения данных.');
      return;
    }
    if (!uploadActFile) {
      setUploadActError('Выберите PDF-файл акта.');
      return;
    }

    const fileName = String(uploadActFile.name || '').toLowerCase();
    if (!fileName.endsWith('.pdf')) {
      setUploadActError('Поддерживается только PDF.');
      return;
    }

    setUploadActParsing(true);
    setUploadActError('');
    try {
      const draft = await equipmentAPI.parseUploadedAct(uploadActFile, { manualMode });
      applyUploadActDraft(draft);
      if (manualMode) {
        setUploadActToast({
          open: true,
          severity: 'info',
          message: 'Черновик создан в ручном режиме. Заполните поля акта и инвентарные номера.',
        });
      }
    } catch (error) {
      if (!manualMode && isApiUnavailableForActParse(error)) {
        try {
          const fallbackDraft = await equipmentAPI.parseUploadedAct(uploadActFile, { manualMode: true });
          applyUploadActDraft(fallbackDraft);
          setUploadActToast({
            open: true,
            severity: 'warning',
            message: 'API распознавания недоступен. Создан ручной черновик для заполнения.',
          });
          return;
        } catch (fallbackError) {
          const fallbackDetail = fallbackError?.response?.data?.detail;
          setUploadActError(
            typeof fallbackDetail === 'string'
              ? fallbackDetail
              : 'Не удалось создать ручной черновик акта.'
          );
          return;
        }
      }
      const apiDetail = error?.response?.data?.detail;
      setUploadActError(typeof apiDetail === 'string' ? apiDetail : 'Не удалось распознать акт.');
    } finally {
      setUploadActParsing(false);
    }
  }, [applyUploadActDraft, canDatabaseWrite, isApiUnavailableForActParse, uploadActFile]);

  const handleUploadActCommit = useCallback(async () => {
    if (!canDatabaseWrite) {
      setUploadActError('Недостаточно прав для изменения данных.');
      return;
    }
    const draftId = String(uploadActDraft?.draft_id || '').trim();
    if (!draftId) {
      setUploadActError('Черновик не найден. Выполните распознавание снова.');
      return;
    }

    const finalInvNos = parseInvNosInput(uploadActForm.equipment_inv_nos_text);
    if (finalInvNos.length === 0) {
      setUploadActError('Укажите хотя бы один инвентарный номер для привязки акта.');
      return;
    }

    setUploadActCommitting(true);
    setUploadActError('');
    try {
      const result = await equipmentAPI.commitUploadedActDraft({
        draft_id: draftId,
        document_title: String(uploadActForm.document_title || '').trim() || undefined,
        from_employee: String(uploadActForm.from_employee || '').trim() || undefined,
        to_employee: String(uploadActForm.to_employee || '').trim() || undefined,
        doc_date: String(uploadActForm.doc_date || '').trim() || undefined,
        equipment_inv_nos: finalInvNos,
      });
      setUploadActCommitResult(result || null);
      setUploadActEmailSubject(`Акт №${result?.doc_no || ''}`.trim());
      setUploadActEmailBody(
        `Во вложении акт №${result?.doc_no || ''}.\n\nПисьмо сформировано автоматически системой IT Invent.`
      );
      setUploadActEmailError('');
      setUploadActEmailStatus('');
      setUploadActEmailLastRecipients([]);
      setUploadActEmailSummary({ mode: '', successCount: 0, failedCount: 0 });

      setUploadActToast({
        open: true,
        severity: 'success',
        message: `Акт загружен. DOC_NO: ${result?.doc_no}, FILE_NO: ${result?.file_no}.`,
      });

      const autoFrom = String(uploadActForm.from_employee || '').trim();
      const autoTo = String(uploadActForm.to_employee || '').trim();
      if (uploadActAutoEmailRef.current && (autoFrom || autoTo)) {
        setUploadActEmailLoading(true);
        try {
          const autoResult = await equipmentAPI.sendUploadedActEmail({
            doc_no: Number(result?.doc_no),
            mode: 'auto',
            from_employee: autoFrom || undefined,
            to_employee: autoTo || undefined,
            subject: `Акт №${result?.doc_no || ''}`.trim(),
            body: `Во вложении акт №${result?.doc_no || ''}.\n\nПисьмо сформировано автоматически системой IT Invent.`,
          });
          const successCount = Number(autoResult?.success_count || 0);
          const failedCount = Number(autoResult?.failed_count || 0);
          const recipients = Array.isArray(autoResult?.recipients) ? autoResult.recipients : [];
          setUploadActEmailLastRecipients(recipients);
          setUploadActEmailSummary({ mode: 'auto', successCount, failedCount });
          setUploadActEmailStatus(`Автоотправка: отправлено ${successCount}, ошибок ${failedCount}.`);
          if (failedCount > 0) {
            setUploadActEmailError('Часть писем не отправлена. Проверьте статусы ниже.');
          }
        } catch (error) {
          const apiDetail = error?.response?.data?.detail;
          setUploadActEmailError(
            typeof apiDetail === 'string' ? apiDetail : 'Автоотправка не выполнена.'
          );
        } finally {
          setUploadActEmailLoading(false);
        }
      } else {
        setUploadActEmailStatus(
          'Акт сохранён. Укажите сотрудников в блоке ниже и отправьте вручную.'
        );
      }
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setUploadActError(typeof apiDetail === 'string' ? apiDetail : 'Не удалось записать акт в базу.');
    } finally {
      setUploadActCommitting(false);
    }
  }, [canDatabaseWrite, uploadActDraft?.draft_id, uploadActForm, uploadActAutoEmail]);

  const handleUploadActEmailSend = useCallback(async () => {
    if (!canDatabaseWrite) {
      setUploadActEmailError('Недостаточно прав для изменения данных.');
      return;
    }
    if (!uploadActCommitResult?.doc_no) return;

    const ownerNos = (uploadActEmailRecipients || [])
      .map((owner) => toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no))
      .filter((ownerNo) => ownerNo !== null);

    if (ownerNos.length === 0) {
      setUploadActEmailError('Выберите хотя бы одного сотрудника.');
      return;
    }

    setUploadActEmailLoading(true);
    setUploadActEmailError('');
    setUploadActEmailStatus('');
    try {
      const result = await equipmentAPI.sendUploadedActEmail({
        doc_no: Number(uploadActCommitResult.doc_no),
        mode: 'selected',
        owner_nos: ownerNos,
        subject: String(uploadActEmailSubject || '').trim() || undefined,
        body: String(uploadActEmailBody || '').trim() || undefined,
      });
      const successCount = Number(result?.success_count || 0);
      const failedCount = Number(result?.failed_count || 0);
      const recipients = Array.isArray(result?.recipients) ? result.recipients : [];
      setUploadActEmailLastRecipients(recipients);
      setUploadActEmailSummary({ mode: 'selected', successCount, failedCount });
      setUploadActEmailStatus(`Отправлено: ${successCount}, ошибок: ${failedCount}.`);
      if (failedCount > 0) {
        setUploadActEmailError('Часть писем не отправлена. Проверьте список статусов.');
      }
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setUploadActEmailError(typeof apiDetail === 'string' ? apiDetail : 'Ошибка отправки email.');
    } finally {
      setUploadActEmailLoading(false);
    }
  }, [canDatabaseWrite, uploadActCommitResult?.doc_no, uploadActEmailRecipients, uploadActEmailSubject, uploadActEmailBody]);

  const selectedEmployeeOption = useMemo(() => {
    if (!detailForm?.empl_no) return null;
    const matched = detailEmployeeOptions.find(
      (owner) => toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no) === toNumberOrNull(detailForm.empl_no)
    );
    if (matched) return matched;
    return {
      OWNER_NO: detailForm.empl_no,
      OWNER_DISPLAY_NAME: detailForm.employee_name || 'Не указан',
      OWNER_DEPT: detailForm.employee_dept || '',
    };
  }, [detailEmployeeOptions, detailForm?.empl_no, detailForm?.employee_name, detailForm?.employee_dept]);

  const selectedTransferEmployeeOption = useMemo(() => {
    if (!newEmployeeNo) return null;
    const matched = transferEmployeeOptions.find(
      (owner) => toNumberOrNull(owner?.OWNER_NO ?? owner?.owner_no) === toNumberOrNull(newEmployeeNo)
    );
    if (matched) return matched;
    return {
      OWNER_NO: newEmployeeNo,
      OWNER_DISPLAY_NAME: newEmployee || 'Не указан',
      OWNER_DEPT: '',
    };
  }, [transferEmployeeOptions, newEmployeeNo, newEmployee]);

  const transferEmployeeInputTrimmed = useMemo(
    () => String(transferEmployeeInput || '').trim(),
    [transferEmployeeInput]
  );

  const transferEmployeeHasExactMatch = useMemo(() => {
    const normalizedInput = normalizeText(transferEmployeeInputTrimmed);
    if (!normalizedInput) return false;
    return transferEmployeeOptions.some(
      (owner) => normalizeText(toOwnerOption(owner).owner_display_name) === normalizedInput
    );
  }, [transferEmployeeInputTrimmed, transferEmployeeOptions]);

  const canAddTransferEmployee = useMemo(() => {
    if (transferResult) return false;
    if (newEmployeeNo) return false;
    if (transferEmployeeInputTrimmed.length < 2) return false;
    if (transferEmployeeHasExactMatch) return false;
    return normalizeText(newEmployee) !== normalizeText(transferEmployeeInputTrimmed);
  }, [
    transferResult,
    newEmployeeNo,
    transferEmployeeInputTrimmed,
    transferEmployeeHasExactMatch,
    newEmployee,
  ]);

  const transferEmployeeAutocompleteOptions = useMemo(() => {
    if (!canAddTransferEmployee) return transferEmployeeOptions;
    if (transferEmployeeOptions.length > 0) return transferEmployeeOptions;
    return [{
      __create: true,
      OWNER_NO: null,
      OWNER_DISPLAY_NAME: transferEmployeeInputTrimmed,
      OWNER_DEPT: '',
    }];
  }, [canAddTransferEmployee, transferEmployeeOptions, transferEmployeeInputTrimmed]);

  const transferUsesManualEmployee = useMemo(
    () => !newEmployeeNo && String(newEmployee || '').trim().length >= 2,
    [newEmployeeNo, newEmployee]
  );

  const handleCreateTransferEmployee = useCallback(() => {
    const candidate = String(transferEmployeeInput || '').trim();
    if (!validateEmployeeName(candidate)) {
      setActionError('Некорректное ФИО. Используйте корректное имя (2-100 символов, без спецсимволов).');
      return;
    }
    setNewEmployee(candidate);
    setNewEmployeeNo(null);
    setTransferEmployeeInput(candidate);
    setActionError('');
  }, [transferEmployeeInput]);

  const handleDetailSave = useCallback(async () => {
    if (!canDatabaseWrite) {
      setDetailError('Недостаточно прав для изменения данных.');
      return;
    }
    if (!detailModal?.invNo || !detailForm || !detailInitialForm) return;

    const comparableCurrent = normalizeDetailComparable(detailForm);
    const comparableInitial = normalizeDetailComparable(detailInitialForm);
    const payload = {};
    Object.keys(comparableCurrent).forEach((key) => {
      if (comparableCurrent[key] !== comparableInitial[key]) {
        payload[key] = comparableCurrent[key];
      }
    });

    if (Object.keys(payload).length === 0) {
      setDetailEditMode(false);
      return;
    }

    if (payload.branch_no !== undefined && comparableCurrent.loc_no === null) {
      setDetailError('Выберите местоположение для выбранного филиала.');
      return;
    }

    if ((payload.type_no !== undefined || payload.model_no !== undefined) && comparableCurrent.model_no === null) {
      setDetailError('Выберите модель для выбранного типа.');
      return;
    }

    setDetailSaving(true);
    setDetailError('');
    setDetailSuccess('');

    try {
      const updated = await equipmentAPI.updateByInvNo(detailModal.invNo, payload);
      const nextForm = buildDetailFormState(updated);
      setDetailModal((prev) => ({ ...prev, data: updated, loading: false }));
      setDetailForm(nextForm);
      setDetailInitialForm(nextForm);
      setDetailEditMode(false);
      setDetailSuccess('Изменения сохранены.');

      const groupedItem = toGroupedItem(updated);
      setAllEquipment((prev) => upsertItemInGrouped(prev, groupedItem));
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setDetailError(typeof apiDetail === 'string' ? apiDetail : 'Ошибка при сохранении изменений.');
    } finally {
      setDetailSaving(false);
    }
  }, [canDatabaseWrite, detailModal?.invNo, detailForm, detailInitialForm, normalizeDetailComparable]);

  const handleDetailEditKeyDown = useCallback((event) => {
    if (event.key !== 'Enter') return;
    if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
    if (!canDatabaseWrite || !detailModal.open || !detailEditMode || detailTab !== 'general') return;
    if (detailSaving || !detailHasChanges) return;

    const target = event.target;
    const tagName = String(target?.tagName || '').toLowerCase();
    if (tagName === 'textarea' || target?.isContentEditable) return;

    const role = target?.getAttribute?.('role');
    if (role === 'combobox' || role === 'listbox' || role === 'option' || role === 'menuitem') return;

    if (target?.closest?.('.MuiAutocomplete-popper, [role="listbox"], [role="menu"]')) return;

    event.preventDefault();
    event.stopPropagation();
    void handleDetailSave();
  }, [
    canDatabaseWrite,
    detailModal.open,
    detailEditMode,
    detailTab,
    detailSaving,
    detailHasChanges,
    handleDetailSave,
  ]);

  const resolveSingleActionTarget = useCallback(() => {
    if (selectedItems.length > 1) {
      return { multiple: true, item: null };
    }
    const invNos = selectedItems.length > 0 ? selectedItems : [actionModal.invNo];
    const invNo = invNos[0];
    if (!invNo) {
      return { multiple: false, item: null };
    }
    return { multiple: false, item: findEquipmentByInvNo(invNo) };
  }, [actionModal.invNo, findEquipmentByInvNo, selectedItems]);

  useEffect(() => {
    const loadWorkConsumables = async () => {
      if (!actionModal.open) return;
      const requiresConsumableLookup =
        actionModal.type === 'cartridge' ||
        (actionModal.type === 'component' && Boolean(actionModal.componentKind));
      if (!requiresConsumableLookup) return;

      setWorkConsumablesLoading(true);
      try {
        const toOptions = (rows) => (Array.isArray(rows) ? rows : [])
          .map((entry) => toConsumableSourceOption(entry))
          .filter((entry) => entry.id !== null);

        const dedupeById = (rows) => {
          const seen = new Set();
          return rows.filter((entry) => {
            const id = toNumberOrNull(entry?.id);
            if (id === null || seen.has(id)) return false;
            seen.add(id);
            return true;
          });
        };

        let options = [];
        try {
          const primaryResponse = await equipmentAPI.lookupConsumables({
            only_positive_qty: true,
            limit: 500,
          });
          options = toOptions(primaryResponse);
        } catch (error) {
          console.warn('Primary consumables lookup failed, trying fallback:', error);
        }

        if (options.length === 0) {
          try {
            const secondaryResponse = await equipmentAPI.lookupConsumables({
              only_positive_qty: false,
              limit: 500,
            });
            options = toOptions(secondaryResponse);
          } catch (error) {
            console.warn('Secondary consumables lookup failed, trying grouped fallback:', error);
          }
        }

        if (options.length === 0) {
          const groupedResponse = await equipmentAPI.getAllConsumablesGrouped({
            page: 1,
            limit: 1000,
          });
          const groupedRows = flattenGroupedConsumables(groupedResponse?.grouped || {});
          options = toOptions(groupedRows);
        }

        options = dedupeById(options);
        setWorkConsumableOptions(options);
        setSelectedWorkConsumable((prev) => {
          const prevId = toNumberOrNull(prev?.id);
          if (prevId === null) return null;
          return options.find((entry) => entry.id === prevId) || null;
        });
      } catch (error) {
        console.error('Error loading consumables for works:', error);
        setWorkConsumableOptions([]);
        setSelectedWorkConsumable(null);
      } finally {
        setWorkConsumablesLoading(false);
      }
    };

    loadWorkConsumables();
  }, [actionModal.open, actionModal.type, actionModal.componentKind]);

  useEffect(() => {
    const loadCartridgeHistory = async () => {
      if (!actionModal.open || actionModal.type !== 'cartridge') return;

      setCartridgeHistory(null);
      const { multiple, item } = resolveSingleActionTarget();
      if (multiple) {
        setCartridgeHistory({ ...EMPTY_HISTORY, multiple: true });
        return;
      }
      if (!item) {
        setCartridgeHistory({ ...EMPTY_HISTORY });
        return;
      }

      try {
        const serialNo = item?.SERIAL_NO || item?.serial_no || '';
        const hwSerialNo = item?.HW_SERIAL_NO || item?.hw_serial_no || '';
        const invNo = String(item?.INV_NO || item?.inv_no || '').trim();
        if (!serialNo && !hwSerialNo && !invNo) {
          setCartridgeHistory({ ...EMPTY_HISTORY });
          return;
        }
        const response = await jsonAPI.getCartridgeReplacementHistory(
          serialNo || undefined,
          hwSerialNo || undefined,
          invNo || undefined,
          undefined,
          cartridgeModel || undefined
        );
        setCartridgeHistory(response?.data || response || { ...EMPTY_HISTORY });
      } catch (error) {
        console.error('Error fetching cartridge history:', error);
        setCartridgeHistory({ ...EMPTY_HISTORY });
      }
    };

    loadCartridgeHistory();
  }, [actionModal.open, actionModal.type, cartridgeModel, resolveSingleActionTarget]);

  useEffect(() => {
    if (!selectedWorkConsumable) return;
    if (actionModal.type === 'cartridge') {
      setCartridgeModel(selectedWorkConsumable.model_name || '');
    }
  }, [selectedWorkConsumable, actionModal.type]);

  useEffect(() => {
    const loadBatteryHistory = async () => {
      if (!actionModal.open || actionModal.type !== 'battery') return;

      setBatteryHistory(null);
      const { multiple, item } = resolveSingleActionTarget();
      if (multiple) {
        setBatteryHistory({ ...EMPTY_HISTORY, multiple: true });
        return;
      }
      if (!item) {
        setBatteryHistory({ ...EMPTY_HISTORY });
        return;
      }

      try {
        const serialNo = item?.SERIAL_NO || item?.serial_no || '';
        const hwSerialNo = item?.HW_SERIAL_NO || item?.hw_serial_no || '';
        if (!serialNo && !hwSerialNo) {
          setBatteryHistory({ ...EMPTY_HISTORY });
          return;
        }
        const response = await jsonAPI.getBatteryReplacementHistory(serialNo, hwSerialNo);
        setBatteryHistory(response?.data || response || { ...EMPTY_HISTORY });
      } catch (error) {
        console.error('Error fetching battery history:', error);
        setBatteryHistory({ ...EMPTY_HISTORY });
      }
    };

    loadBatteryHistory();
  }, [actionModal.open, actionModal.type, resolveSingleActionTarget]);

  useEffect(() => {
    const loadComponentHistory = async () => {
      if (!actionModal.open || actionModal.type !== 'component') return;

      setComponentHistory(null);
      const { multiple, item } = resolveSingleActionTarget();
      if (multiple) {
        setComponentHistory({ ...EMPTY_HISTORY, multiple: true });
        return;
      }
      if (!item) {
        setComponentHistory({ ...EMPTY_HISTORY });
        return;
      }

      try {
        const serialNo = item?.SERIAL_NO || item?.serial_no || '';
        const hwSerialNo = item?.HW_SERIAL_NO || item?.hw_serial_no || '';
        if (!serialNo && !hwSerialNo) {
          setComponentHistory({ ...EMPTY_HISTORY });
          return;
        }
        const componentName = getComponentLabel(actionModal.componentKind, componentType);
        const response = await jsonAPI.getComponentReplacementHistory(
          serialNo,
          hwSerialNo,
          componentType,
          componentName
        );
        setComponentHistory(response?.data || response || { ...EMPTY_HISTORY });
      } catch (error) {
        console.error('Error fetching component history:', error);
        setComponentHistory({ ...EMPTY_HISTORY });
      }
    };

    loadComponentHistory();
  }, [actionModal.open, actionModal.type, actionModal.componentKind, componentType, resolveSingleActionTarget]);

  // Load cleaning history when action modal opens for cleaning
  useEffect(() => {
    const loadCleaningHistory = async () => {
      if (!actionModal.open || actionModal.type !== 'cleaning') return;

      setCleaningHistory(null);
      const { multiple, item } = resolveSingleActionTarget();
      if (multiple) {
        setCleaningHistory({ ...EMPTY_HISTORY, multiple: true });
        return;
      }
      if (!item) {
        setCleaningHistory({ ...EMPTY_HISTORY });
        return;
      }

      try {
        const serialNo = item?.SERIAL_NO || item?.serial_no || '';
        const hwSerialNo = item?.HW_SERIAL_NO || item?.hw_serial_no || '';
        if (!serialNo && !hwSerialNo) {
          setCleaningHistory({ ...EMPTY_HISTORY });
          return;
        }
        const response = await jsonAPI.getPcCleaningHistory(serialNo, hwSerialNo);
        setCleaningHistory(response?.data || response || { ...EMPTY_HISTORY });
      } catch (error) {
        console.error('Error fetching cleaning history:', error);
        setCleaningHistory({ ...EMPTY_HISTORY });
      }
    };

    loadCleaningHistory();
  }, [actionModal.open, actionModal.type, resolveSingleActionTarget]);

  const handleBranchChange = useCallback((branch) => {
    setSelectedBranch(branch);
    setFilteredData(null);
    setSelectedItems([]);
  }, []);

  const handleTableSort = useCallback((field) => {
    setTableSort((prev) => {
      if (prev.field === field) {
        return {
          field,
          direction: prev.direction === 'asc' ? 'desc' : 'asc',
        };
      }
      return {
        field,
        direction: 'asc',
      };
    });
  }, []);

  useEffect(() => {
    if (selectedBranch) {
      setExpandedBranches(new Set([selectedBranch]));
    } else {
      setExpandedBranches(new Set());
    }
    setExpandedLocations(new Set());
  }, [selectedBranch]);

  const toggleBranch = useCallback((branchName) => {
    setExpandedBranches((prev) => {
      const next = new Set(prev);
      if (next.has(branchName)) {
        next.delete(branchName);
        setExpandedLocations((prevLocations) => {
          const filtered = new Set();
          prevLocations.forEach((key) => {
            if (!key.startsWith(`${branchName}::`)) {
              filtered.add(key);
            }
          });
          return filtered;
        });
      } else {
        next.add(branchName);
      }
      return next;
    });
  }, []);

  const toggleLocation = useCallback((branchName, locationName) => {
    const key = buildLocationKey(branchName, locationName);
    setExpandedLocations((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleCheckboxChange = useCallback((invNo) => {
    const normalizedInvNo = String(invNo || '').trim();
    if (!normalizedInvNo) return;

    setSelectedItems((prev) =>
      prev.includes(normalizedInvNo)
        ? prev.filter((id) => id !== normalizedInvNo)
        : [...prev, normalizedInvNo]
    );
  }, []);

  const handleSelectAll = useCallback((items, event) => {
    const isChecked = event.target.checked;
    if (isChecked) {
      const allInvNos = items
        .map((item) => toInvNo(item))
        .filter(Boolean);
      setSelectedItems(allInvNos);
    } else {
      setSelectedItems([]);
    }
  }, []);

  const resetTransferState = useCallback(() => {
    setNewEmployee('');
    setNewEmployeeNo(null);
    setTransferDepartment('');
    setTransferDepartmentOptions([]);
    setTransferDepartmentLoading(false);
    setTransferBranchNo(null);
    setTransferLocationNo(null);
    setTransferLocations([]);
    setTransferLocationsLoading(false);
    setTransferEmployeeInput('');
    setTransferEmployeeOptions([]);
    setTransferEmployeeLoading(false);
    setTransferResult(null);
    setTransferEmailMode('old');
    setTransferManualEmail('');
    setTransferRecipientInput('');
    setTransferRecipientOptions([]);
    setTransferRecipient(null);
    setTransferRecipientLoading(false);
    setTransferEmailLoading(false);
    setTransferEmailStatus('');
    setTransferEmailError('');
  }, []);

  const handleAction = useCallback((actionType, itemOrInvNo) => {
    if (dataMode === DATA_MODE_CONSUMABLES) return;
    if (actionType !== 'view' && !canDatabaseWrite) return;
    const invNo = toInvNo(itemOrInvNo);
    if (actionType === 'view') {
      setDetailEditMode(false);
      setDetailSaving(false);
      setDetailError('');
      setDetailSuccess('');
      setDetailForm(null);
      setDetailInitialForm(null);
      setDetailLocations([]);
      setDetailEmployeeOptions([]);
      setDetailEmployeeInput('');
      setDetailTab('general');
      setDetailActs([]);
      setDetailActsLoading(false);
      setDetailActsError('');
      setDetailActsLoadedInvNo('');
      setDetailActOpeningDocNo('');
      setDetailActFieldsOpen(false);
      setDetailActSelected(null);
      setDetailModal({ open: true, data: null, loading: true, invNo });
    } else {
      if (actionType === 'transfer') {
        resetTransferState();
      }
      const item = findEquipmentByInvNo(invNo);
      const flags = getItemCapabilityFlags(item);
      const componentKind =
        actionType === 'component'
          ? (flags.isPc && !flags.isPrinterOrMfu ? 'pc' : 'printer')
          : null;
      if (actionType === 'component') {
        setComponentType(componentKind === 'pc' ? PC_COMPONENT_OPTIONS[0].value : PRINTER_COMPONENT_OPTIONS[0].value);
      }
      setActionModal({ open: true, type: actionType, invNo, componentKind });
    }
  }, [canDatabaseWrite, dataMode, findEquipmentByInvNo, resetTransferState]);

  const handleTransferActDownload = useCallback(async (act) => {
    try {
      const response = await equipmentAPI.downloadTransferAct(act.act_id);
      const blob = new Blob([response.data], {
        type: response.headers?.['content-type'] || 'application/octet-stream',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = act.file_name || `transfer_act_${act.act_id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading transfer act:', error);
      setActionError('Не удалось скачать акт.');
    }
  }, []);

  const handleOpenEquipmentActFile = useCallback((act) => {
    const docNo = String(readFirst(act, ['doc_no', 'DOC_NO'], '')).trim();
    if (!docNo) {
      setDetailActsError('У акта отсутствует DOC_NO, открыть файл невозможно.');
      return;
    }

    const itemIdRaw = readFirst(act, ['item_id', 'ITEM_ID'], null);
    const itemId = toNumberOrNull(itemIdRaw);

    setDetailActOpeningDocNo(docNo);
    setDetailActsError('');
    try {
      const selectedDb = normalizeDbId(localStorage.getItem('selected_database') || '');
      const requestUrl = new URL(
        `${API_V1_BASE}/equipment/acts/${encodeURIComponent(docNo)}/file`,
        window.location.origin
      );
      if (itemId !== null && itemId !== undefined) {
        requestUrl.searchParams.set('item_id', String(itemId));
      }
      if (detailModal?.invNo) {
        requestUrl.searchParams.set('inv_no', String(detailModal.invNo));
      }
      if (selectedDb) {
        requestUrl.searchParams.set('db_id', selectedDb);
      }
      const opened = window.open(requestUrl.toString(), '_blank', 'noopener,noreferrer');
      if (!opened) {
        setDetailActsError('Браузер заблокировал открытие новой вкладки. Разрешите pop-up для сайта.');
      }
    } catch (error) {
      console.error('Error opening equipment act file:', error);
      const apiDetail = error?.response?.data?.detail;
      setDetailActsError(typeof apiDetail === 'string' ? apiDetail : 'Не удалось открыть файл акта.');
    } finally {
      setDetailActOpeningDocNo('');
    }
  }, [detailModal?.invNo]);

  const handleOpenActFields = useCallback((act) => {
    setDetailActSelected(act || null);
    setDetailActFieldsOpen(true);
  }, []);

  const handleCloseActFields = useCallback(() => {
    setDetailActFieldsOpen(false);
    setDetailActSelected(null);
  }, []);

  const handleTransferEmailSend = useCallback(async () => {
    if (!canDatabaseWrite) {
      setTransferEmailError('Недостаточно прав для изменения данных.');
      return;
    }
    if (!transferResult?.acts?.length) return;

    const payload = {
      act_ids: transferResult.acts.map((act) => act.act_id),
      mode: transferEmailMode,
    };

    if (transferEmailMode === 'manual') {
      const email = String(transferManualEmail || '').trim();
      if (!email) {
        setTransferEmailError('Введите email получателя.');
        return;
      }
      payload.manual_email = email;
    }

    if (transferEmailMode === 'employee') {
      const ownerNo = toNumberOrNull(transferRecipient?.OWNER_NO ?? transferRecipient?.owner_no);
      if (!ownerNo) {
        setTransferEmailError('Выберите сотрудника-получателя.');
        return;
      }
      payload.owner_no = ownerNo;
    }

    setTransferEmailLoading(true);
    setTransferEmailError('');
    setTransferEmailStatus('');
    try {
      const result = await equipmentAPI.sendTransferActsEmail(payload);
      const successCount = Number(result?.success_count || 0);
      const failedCount = Number(result?.failed_count || 0);
      const errors = Array.isArray(result?.errors) ? result.errors : [];
      setTransferEmailStatus(`Отправлено: ${successCount}, ошибок: ${failedCount}`);
      if (errors.length > 0) {
        setTransferEmailError(errors.join('; '));
      }
    } catch (error) {
      const apiDetail = error?.response?.data?.detail;
      setTransferEmailError(typeof apiDetail === 'string' ? apiDetail : 'Ошибка отправки email.');
    } finally {
      setTransferEmailLoading(false);
    }
  }, [canDatabaseWrite, transferResult, transferEmailMode, transferManualEmail, transferRecipient]);

  const getInvalidTargets = useCallback((invNos, predicate) => (
    (invNos || []).filter((invNo) => {
      const item = findEquipmentByInvNo(invNo);
      if (!item) return true;
      return !predicate(item);
    })
  ), [findEquipmentByInvNo]);

  const searchSourceData = useMemo(() => {
    if (!selectedBranch) return allEquipment;
    const selectedBranchNormalized = normalizeText(selectedBranch);
    const scoped = {};
    Object.entries(allEquipment).forEach(([branchName, locations]) => {
      if (normalizeText(branchName) === selectedBranchNormalized) {
        scoped[branchName] = locations;
      }
    });
    return scoped;
  }, [allEquipment, selectedBranch]);

  const searchIndex = useMemo(() => {
    const entries = [];

    Object.entries(searchSourceData).forEach(([branchName, locations]) => {
      Object.entries(locations).forEach(([locationName, items]) => {
        items.forEach((item) => {
          const ipAddress = String(item.IP_ADDRESS || item.ip_address || '').trim();
          const macAddress = String(item.MAC_ADDRESS || item.mac_address || item.MAC_ADDR || item.mac_addr || '').trim();
          const computerName = String(
            item.NETBIOS_NAME || item.netbios_name || item.NETWORK_NAME || item.network_name || ''
          ).trim();
          const domainName = String(item.DOMAIN_NAME || item.domain_name || '').trim();
          const macCompact = macAddress.replace(/[^A-Za-z0-9]/g, '');

          const searchable = [
            item.ID || item.id || '',
            item.INV_NO || item.inv_no || '',
            item.SERIAL_NO || item.serial_no || '',
            item.HW_SERIAL_NO || item.hw_serial_no || '',
            item.MODEL_NAME || item.model_name || '',
            item.TYPE_NAME || item.type_name || '',
            item.OWNER_DISPLAY_NAME || item.employee_name || '',
            ipAddress,
            macAddress,
            macCompact,
            computerName,
            domainName,
          ]
            .join(' ')
            .toLowerCase();

          entries.push({ branchName, locationName, item, searchable });
        });
      });
    });

    return entries;
  }, [searchSourceData]);

  const runSearchNow = useCallback((query) => {
    const normalizedQuery = String(query || '').trim().toLowerCase();

    if (normalizedQuery.length < 2) {
      setFilteredData(null);
      return;
    }

    const matchedEntries = searchIndex.filter((entry) => entry.searchable.includes(normalizedQuery));
    if (matchedEntries.length > 0) {
      const grouped = groupSearchResults(matchedEntries);
      setFilteredData(grouped);

      // Auto-expand branches and locations to clearly show search results
      const newExpandedBranches = new Set();
      const newExpandedLocations = new Set();

      Object.keys(grouped).forEach((branchName) => {
        newExpandedBranches.add(branchName);
        Object.keys(grouped[branchName] || {}).forEach((locationName) => {
          newExpandedLocations.add(buildLocationKey(branchName, locationName));
        });
      });

      setExpandedBranches(newExpandedBranches);
      setExpandedLocations(newExpandedLocations);
    } else {
      setFilteredData({});
    }
  }, [searchIndex]);

  const applySearchDebounced = useMemo(
    () => debounce((query) => runSearchNow(query), 1200),
    [runSearchNow]
  );

  const handleSearchChange = useCallback(
    (e) => {
      const query = e.target.value;
      setSearchQuery(query);
      applySearchDebounced(query);
    },
    [applySearchDebounced]
  );

  const handleSearchKeyDown = useCallback(
    (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      applySearchDebounced.cancel?.();
      runSearchNow(searchQuery);
    },
    [applySearchDebounced, runSearchNow, searchQuery]
  );

  const searchQueryRef = useRef('');
  useEffect(() => {
    searchQueryRef.current = searchQuery;
  }, [searchQuery]);

  useEffect(() => {
    applySearchDebounced.cancel?.();
    const activeQuery = String(searchQueryRef.current || '').trim();
    if (activeQuery.length >= 2) {
      runSearchNow(activeQuery);
      return;
    }
    setFilteredData(null);
  }, [selectedBranch, searchIndex, applySearchDebounced, runSearchNow]);

  useEffect(() => () => {
    applySearchDebounced.cancel?.();
  }, [applySearchDebounced]);

  const clearSearch = useCallback(() => {
    applySearchDebounced.cancel?.();
    setSearchQuery('');
    setFilteredData(null);
  }, [applySearchDebounced]);

  const selectedItemsSet = useMemo(() => new Set(selectedItems), [selectedItems]);
  const visibleInvNoSet = useMemo(() => {
    const ids = new Set();
    Object.values(displayData || {}).forEach((locations) => {
      Object.values(locations || {}).forEach((items) => {
        (items || []).forEach((item) => {
          const invNo = toInvNo(item);
          if (invNo) ids.add(invNo);
        });
      });
    });
    return ids;
  }, [displayData]);
  const selectedVisibleCount = useMemo(
    () => selectedItems.reduce((acc, id) => (visibleInvNoSet.has(String(id)) ? acc + 1 : acc), 0),
    [selectedItems, visibleInvNoSet]
  );
  const selectedHiddenCount = Math.max(0, selectedItems.length - selectedVisibleCount);

  const selectedItemsCapabilities = useMemo(() => {
    if (selectedItems.length === 0) {
      return {
        canCartridge: false,
        canBattery: false,
        canComponent: false,
        componentKind: null,
        canCleaning: false,
      };
    }

    const items = selectedItems
      .map((invNo) => findEquipmentByInvNo(invNo))
      .filter(Boolean);

    const hasFullResolvedSet = items.length === selectedItems.length;
    const allMatch = (predicate) => hasFullResolvedSet && items.every(predicate);

    const printerOnly = allMatch((item) => getItemCapabilityFlags(item).isPrinterOrMfu);
    const pcOnly = allMatch((item) => getItemCapabilityFlags(item).isPc);

    return {
      canCartridge: printerOnly,
      canBattery: allMatch((item) => getItemCapabilityFlags(item).isUps),
      canComponent: printerOnly || pcOnly,
      componentKind: printerOnly ? 'printer' : (pcOnly ? 'pc' : null),
      canCleaning: pcOnly,
    };
  }, [selectedItems, findEquipmentByInvNo]);

  const activeComponentOptions = useMemo(() => (
    actionModal.componentKind === 'pc' ? PC_COMPONENT_OPTIONS : PRINTER_COMPONENT_OPTIONS
  ), [actionModal.componentKind]);

  const actionWorkConsumableOptions = useMemo(() => {
    const options = Array.isArray(workConsumableOptions) ? workConsumableOptions : [];
    const isCartridgeAction = actionModal.type === 'cartridge';
    const isPrinterComponentAction =
      actionModal.type === 'component' && actionModal.componentKind === 'printer';
    if (isCartridgeAction) {
      return options.filter((entry) => isCartridgeLikeConsumable(entry));
    }
    if (!isPrinterComponentAction) {
      return options;
    }
    return options.filter((entry) => !isCartridgeLikeConsumable(entry));
  }, [actionModal.type, actionModal.componentKind, workConsumableOptions]);

  useEffect(() => {
    const selectedId = toNumberOrNull(selectedWorkConsumable?.id);
    if (selectedId === null) return;
    const existsInCurrentList = actionWorkConsumableOptions.some(
      (entry) => toNumberOrNull(entry?.id) === selectedId
    );
    if (!existsInCurrentList) {
      setSelectedWorkConsumable(null);
    }
  }, [actionWorkConsumableOptions, selectedWorkConsumable]);

  const isAllSelected = useCallback((items) => {
    if (items.length === 0) return false;
    return items.every((item) => {
      const id = toInvNo(item);
      return selectedItemsSet.has(id);
    });
  }, [selectedItemsSet]);

  const isSomeSelected = useCallback((items) => {
    return items.some((item) => {
      const id = toInvNo(item);
      return selectedItemsSet.has(id);
    });
  }, [selectedItemsSet]);

  const renderTable = useCallback((items) => (
    <EquipmentTable
      items={items}
      isMobile={isMobile}
      theme={theme}
      selectedItemsSet={selectedItemsSet}
      tableSort={tableSort}
      onTableSort={handleTableSort}
      onSelectAll={handleSelectAll}
      isAllSelected={isAllSelected}
      isSomeSelected={isSomeSelected}
      onSelect={handleCheckboxChange}
      onAction={handleAction}
      onEditConsumableQty={canDatabaseWrite ? openEditConsumableQtyModal : null}
      allowSelection={!isConsumablesMode && canDatabaseWrite}
      dataMode={dataMode}
      canWrite={canDatabaseWrite}
    />
  ), [
    isMobile,
    theme,
    selectedItemsSet,
    tableSort,
    handleTableSort,
    handleSelectAll,
    isAllSelected,
    isSomeSelected,
    handleCheckboxChange,
    handleAction,
    canDatabaseWrite,
    openEditConsumableQtyModal,
    isConsumablesMode,
    dataMode,
  ]);

  const dataSections = useMemo(() => {
    if (Object.keys(displayData).length === 0) return null;
    return Object.keys(displayData).map((branchName) => {
      const locations = displayData[branchName];
      const isBranchExpanded = expandedBranches.has(branchName);
      const branchTotal = Object.values(locations).reduce((sum, items) => sum + items.length, 0);

      return (
        <Box
          key={branchName}
          sx={{
            mb: 1.5,
            border: '1px solid ' + theme.palette.divider,
            borderRadius: 1,
            overflow: 'hidden',
          }}
        >
          <Box
            onClick={() => toggleBranch(branchName)}
            sx={{
              p: isMobile ? 1 : 1.2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              cursor: 'pointer',
              backgroundColor:
                theme.palette.mode === 'dark'
                  ? '#0f172a'
                  : theme.palette.grey[100],
              '&:hover': {
                backgroundColor:
                  theme.palette.mode === 'dark'
                    ? '#1e293b'
                    : theme.palette.grey[200],
              },
              color: theme.palette.mode === 'dark' ? '#ffffff' : 'inherit',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {isBranchExpanded ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
              <Typography variant={isMobile ? 'subtitle1' : 'h6'} sx={{ fontSize: isMobile ? '0.85rem' : undefined }}>
                {branchName}
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: isMobile ? '0.75rem' : undefined }}>
              ({branchTotal.toLocaleString()})
            </Typography>
          </Box>

          <Collapse in={isBranchExpanded} timeout="auto" unmountOnExit>
            {Object.keys(locations).sort((a, b) => locationNameCollator.compare(String(a || ''), String(b || ''))).map((locationName) => {
              const locationKey = buildLocationKey(branchName, locationName);
              const locationItems = locations[locationName];
              const isLocationExpanded = expandedLocations.has(locationKey);

              return (
                <Box key={locationName} sx={{ borderTop: '1px solid ' + theme.palette.divider }}>
                  <Box
                    onClick={() => toggleLocation(branchName, locationName)}
                    sx={{
                      p: isMobile ? 0.9 : 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      backgroundColor: theme.palette.mode === 'dark' ? '#111827' : 'transparent',
                      '&:hover': {
                        backgroundColor: theme.palette.mode === 'dark' ? '#1f2937' : theme.palette.action.hover,
                      },
                      color: theme.palette.mode === 'dark' ? '#e5e7eb' : 'inherit',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      {isLocationExpanded ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
                      <Typography variant="body2" sx={{ fontWeight: 600, fontSize: isMobile ? '0.75rem' : undefined }}>
                        {locationName}
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ fontSize: isMobile ? '0.75rem' : undefined }}>
                      ({locationItems.length.toLocaleString()})
                    </Typography>
                  </Box>
                  <Collapse in={isLocationExpanded} timeout="auto" unmountOnExit>
                    <Box sx={{ p: isMobile ? 0.5 : 1, borderTop: '1px solid ' + theme.palette.divider }}>
                      {renderTable(locationItems)}
                    </Box>
                  </Collapse>
                </Box>
              );
            })}
          </Collapse>
        </Box>
      );
    });
  }, [displayData, expandedBranches, expandedLocations, isMobile, renderTable, theme, toggleBranch, toggleLocation]);

  if (loading && filteredData === null) {
    return (
      <MainLayout>
        <LoadingSpinner message="Загрузка данных..." />
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <Box sx={{ pb: isMobile ? 2 : 3 }}>
        <Box sx={{
          mb: 3,
          display: 'flex',
          flexDirection: isMobile ? 'column' : 'row',
          justifyContent: 'space-between',
          alignItems: isMobile ? 'flex-start' : 'center',
          gap: 2,

        }}>
          <Box>
            <Typography variant={isMobile ? 'h5' : 'h4'} component="h1">
              {selectedBranch || 'IT-invent WEB'}
              {filteredData === null && selectedBranch && (
                <Typography component="span" variant="inherit" color="text.secondary">
                  {' '}({total.toLocaleString()})
                </Typography>
              )}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              Режим: {isConsumablesMode ? 'Расходники' : 'Оборудование'}
            </Typography>
            {filteredData === null && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Загружено: {loadedCount.toLocaleString()}
                {serverTotal > 0 ? ` из ${serverTotal.toLocaleString()}` : ''}
              </Typography>
            )}
          </Box>
        </Box>

        <Paper variant="outlined" sx={{ mb: 1.5, p: 0.5 }}>
          <Tabs
            value={dataMode}
            onChange={(_, value) => setDataMode(value)}
            variant="fullWidth"
          >
            <Tab value={DATA_MODE_EQUIPMENT} label="Оборудование" />
            <Tab value={DATA_MODE_CONSUMABLES} label="Расходники" />
          </Tabs>
        </Paper>

        <Box sx={{
          mb: 2,
          display: 'flex',
          flexDirection: isMobile ? 'column' : 'row',
          gap: isMobile ? 1 : 2,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}>
          <TextField
            placeholder={
              isConsumablesMode
                ? 'Поиск по ID, инв. №, серийному, типу, модели, сотруднику...'
                : 'Поиск по ID, инв. №, серийному, IP, MAC, имени ПК...'
            }
            value={searchQuery}
            onChange={handleSearchChange}
            onKeyDown={handleSearchKeyDown}
            sx={{
              flexGrow: 1,
              minWidth: isMobile ? '100%' : 250,
              maxWidth: isMobile ? '100%' : 400,
            }}
            size={isMobile ? 'medium' : 'small'}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  {searchQuery && (
                    <IconButton size="small" onClick={clearSearch} edge="end">
                      <CloseIcon />
                    </IconButton>
                  )}
                </InputAdornment>
              ),
            }}
          />

          {branches.length > 0 && (
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Филиал</InputLabel>
              <Select
                value={selectedBranch}
                onChange={(e) => handleBranchChange(e.target.value)}
                label="Филиал"
              >
                <MenuItem value="">Выберите филиал</MenuItem>
                {branches.map((branch) => (
                  <MenuItem key={branch.BRANCH_NO} value={branch.BRANCH_NAME}>
                    {branch.BRANCH_NAME}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          {!isConsumablesMode && (
            <Button
              variant="outlined"
              color="secondary"
              startIcon={identifyPCLoading ? <CircularProgress size={20} color="inherit" /> : <MyLocationIcon />}
              onClick={handleIdentifyWorkspace}
              disabled={identifyPCLoading}
              sx={{ minWidth: isMobile ? '100%' : 210 }}
            >
              {identifyPCLoading ? 'Определение...' : 'Определить ПК'}
            </Button>
          )}
          {!isConsumablesMode && canDatabaseWrite && (
            <Button
              variant="outlined"
              startIcon={<UploadFileIcon />}
              onClick={openUploadActModal}
              sx={{ minWidth: isMobile ? '100%' : 250 }}
            >
              Загрузить подписанный акт
            </Button>
          )}
          {!isConsumablesMode && canDatabaseWrite && (
            <Button
              variant="contained"
              onClick={openAddEquipmentModal}
              sx={{ minWidth: isMobile ? '100%' : 210 }}
            >
              Добавить оборудование
            </Button>
          )}
          {isConsumablesMode && canDatabaseWrite && (
            <Button
              variant="contained"
              onClick={openAddConsumableModal}
              sx={{ minWidth: isMobile ? '100%' : 210 }}
            >
              Добавить расходник
            </Button>
          )}
          {filteredData === null && nextEquipmentPage && (
            <Button
              variant="text"
              onClick={() => loadMoreEquipmentPages({ maxPages: 1 })}
              disabled={loadingMoreEquipment}
              sx={{ minWidth: isMobile ? '100%' : 200 }}
            >
              {loadingMoreEquipment
                ? 'Загрузка...'
                : `Загрузить ещё (${nextEquipmentPage}/${equipmentPagesTotal})`}
            </Button>
          )}
          {hasExpandedVisible && (
            <Button
              variant="text"
              size="small"
              onClick={handleCollapseAll}
              startIcon={<ExpandMoreIcon sx={{ transform: 'rotate(180deg)', fontSize: 15 }} />}
              sx={{
                minWidth: isMobile ? '100%' : 'auto',
                px: 0.9,
                py: 0.3,
                height: 30,
                borderRadius: 1.25,
                textTransform: 'none',
                fontSize: '0.75rem',
                fontWeight: 500,
                color: 'text.secondary',
                '&:hover': {
                  backgroundColor: theme.palette.action.hover,
                  color: 'text.primary',
                },
              }}
            >
              Свернуть разделы
            </Button>
          )}
        </Box>

        {!isConsumablesMode && canDatabaseWrite && selectedItems.length > 0 && (
          <Paper
            elevation={3}
            sx={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              right: 0,
              zIndex: 1200,
              p: { xs: 1, sm: 1.5 },
              display: 'flex',
              gap: 1,
              alignItems: 'center',
              flexWrap: 'wrap',
              justifyContent: 'center',
              backgroundColor: theme.palette.primary.main,
              color: theme.palette.primary.contrastText,
            }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mr: 1 }}>
              Выбрано: {selectedItems.length}
            </Typography>
            {selectedHiddenCount > 0 ? (
              <Typography variant="caption" sx={{ mr: 1, opacity: 0.95 }}>
                {`В фильтре видно: ${selectedVisibleCount}, скрыто: ${selectedHiddenCount}`}
              </Typography>
            ) : null}
            <Button
              size={isMobile ? 'medium' : 'small'}
              variant={isMobile ? 'text' : 'outlined'}
              color="inherit"
              sx={{
                color: 'common.white',
                borderColor: 'rgba(255,255,255,0.6)',
                '&:hover': {
                  borderColor: 'common.white',
                  backgroundColor: 'rgba(255,255,255,0.14)',
                },
              }}
              onClick={() => {
                resetTransferState();
                setActionModal({ open: true, type: 'transfer', invNo: null, componentKind: null });
              }}
            >
              Переместить
            </Button>
            <Button
              size={isMobile ? 'medium' : 'small'}
              variant={isMobile ? 'text' : 'outlined'}
              color="inherit"
              disabled={!selectedItemsCapabilities.canCartridge}
              sx={{
                color: 'common.white',
                borderColor: 'rgba(255,255,255,0.6)',
                '&:hover': {
                  borderColor: 'common.white',
                  backgroundColor: 'rgba(255,255,255,0.14)',
                },
                '&.Mui-disabled': {
                  color: 'rgba(255,255,255,0.5)',
                  borderColor: 'rgba(255,255,255,0.3)',
                },
              }}
              onClick={() => setActionModal({ open: true, type: 'cartridge', invNo: null, componentKind: null })}
            >
              {!isMobile && 'Картридж'}
            </Button>
            <Button
              size={isMobile ? 'medium' : 'small'}
              variant={isMobile ? 'text' : 'outlined'}
              color="inherit"
              disabled={!selectedItemsCapabilities.canBattery}
              sx={{
                color: 'common.white',
                borderColor: 'rgba(255,255,255,0.6)',
                '&:hover': {
                  borderColor: 'common.white',
                  backgroundColor: 'rgba(255,255,255,0.14)',
                },
                '&.Mui-disabled': {
                  color: 'rgba(255,255,255,0.5)',
                  borderColor: 'rgba(255,255,255,0.3)',
                },
              }}
              onClick={() => setActionModal({ open: true, type: 'battery', invNo: null, componentKind: null })}
            >
              {!isMobile && 'Батарея'}
            </Button>
            <Button
              size={isMobile ? 'medium' : 'small'}
              variant={isMobile ? 'text' : 'outlined'}
              color="inherit"
              disabled={!selectedItemsCapabilities.canComponent}
              sx={{
                color: 'common.white',
                borderColor: 'rgba(255,255,255,0.6)',
                '&:hover': {
                  borderColor: 'common.white',
                  backgroundColor: 'rgba(255,255,255,0.14)',
                },
                '&.Mui-disabled': {
                  color: 'rgba(255,255,255,0.5)',
                  borderColor: 'rgba(255,255,255,0.3)',
                },
              }}
              onClick={() => {
                const kind = selectedItemsCapabilities.componentKind || 'printer';
                setComponentType(kind === 'pc' ? PC_COMPONENT_OPTIONS[0].value : PRINTER_COMPONENT_OPTIONS[0].value);
                setActionModal({ open: true, type: 'component', invNo: null, componentKind: kind });
              }}
            >
              {!isMobile && 'Компонент'}
            </Button>
            <IconButton
              onClick={() => setSelectedItems([])}
              size={isMobile ? 'medium' : 'small'}
              sx={{
                color: 'common.white',
                '&:hover': { backgroundColor: 'rgba(255,255,255,0.14)' },
              }}
            >
              <CloseIcon />
            </IconButton>
          </Paper>
        )}

        <Fade key={dataMode} in timeout={{ enter: 320, exit: 160 }}>
          <Box
            sx={{
              animation: 'database-tab-slide 320ms ease',
              '@keyframes database-tab-slide': {
                from: { opacity: 0, transform: 'translateY(8px)' },
                to: { opacity: 1, transform: 'translateY(0)' },
              },
            }}
          >
            {dataSections || (
              !selectedBranch ? (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <Typography color="text.secondary">Выберите филиал</Typography>
                </Box>
              ) : (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <Typography color="text.secondary">Нет данных</Typography>
                </Box>
              )
            )}
          </Box>
        </Fade>

        <Snackbar
          open={addEquipmentToast.open}
          autoHideDuration={4500}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          onClose={() => setAddEquipmentToast({ open: false, message: '' })}
        >
          <Alert
            severity="success"
            variant="filled"
            onClose={() => setAddEquipmentToast({ open: false, message: '' })}
            sx={{ width: '100%' }}
          >
            {addEquipmentToast.message}
          </Alert>
        </Snackbar>

        <Snackbar
          open={addConsumableToast.open}
          autoHideDuration={4500}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          onClose={() => setAddConsumableToast({ open: false, message: '' })}
        >
          <Alert
            severity="success"
            variant="filled"
            onClose={() => setAddConsumableToast({ open: false, message: '' })}
            sx={{ width: '100%' }}
          >
            {addConsumableToast.message}
          </Alert>
        </Snackbar>

        <Snackbar
          open={editConsumableQtyToast.open}
          autoHideDuration={4500}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          onClose={() => setEditConsumableQtyToast({ open: false, message: '' })}
        >
          <Alert
            severity="success"
            variant="filled"
            onClose={() => setEditConsumableQtyToast({ open: false, message: '' })}
            sx={{ width: '100%' }}
          >
            {editConsumableQtyToast.message}
          </Alert>
        </Snackbar>

        <Snackbar
          open={uploadActToast.open}
          autoHideDuration={5000}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          onClose={() => setUploadActToast({ open: false, message: '', severity: 'success' })}
        >
          <Alert
            severity={uploadActToast.severity || 'success'}
            variant="filled"
            onClose={() => setUploadActToast({ open: false, message: '', severity: 'success' })}
            sx={{ width: '100%' }}
          >
            {uploadActToast.message}
          </Alert>
        </Snackbar>

        <Dialog
          open={uploadActModalOpen}
          onClose={closeUploadActModal}
          maxWidth="md"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>Загрузка подписанного акта</DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Box sx={{ display: 'grid', gap: 2 }}>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  borderRadius: 2,
                  background: 'linear-gradient(135deg, rgba(25,118,210,0.08), rgba(2,136,209,0.02))',
                }}
              >
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                  Этапы загрузки акта
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {[
                    { step: 1, label: 'Файл' },
                    { step: 2, label: 'Проверка' },
                    { step: 3, label: 'Запись в базу' },
                    { step: 4, label: 'Отправка email' },
                  ].map((entry) => {
                    const active = uploadActStep >= entry.step;
                    return (
                      <Chip
                        key={entry.step}
                        size="small"
                        label={`${entry.step}. ${entry.label}`}
                        color={active ? 'primary' : 'default'}
                        variant={active ? 'filled' : 'outlined'}
                        sx={{
                          transition: 'all 200ms ease',
                          transform: active ? 'translateY(0)' : 'translateY(1px)',
                        }}
                      />
                    );
                  })}
                </Box>
              </Paper>

              <Collapse in={!uploadActCommitResult} mountOnEnter unmountOnExit>
                <Box sx={{ display: 'grid', gap: 2 }}>
                  <Fade in timeout={220}>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                        1. Выбор и распознавание PDF
                      </Typography>
                      <Alert severity="info" variant="outlined" sx={{ mb: 1.5 }}>
                        Загрузите подписанный PDF. Если API распознавания недоступен, используйте ручной режим без API.
                      </Alert>
                      <Box sx={{ display: 'grid', gap: 1.5 }}>
                        <Button
                          component="label"
                          variant="outlined"
                          startIcon={<UploadFileIcon />}
                          disabled={uploadActParsing || uploadActCommitting}
                          sx={{ justifyContent: 'flex-start' }}
                        >
                          {uploadActFile ? `Файл: ${uploadActFile.name}` : 'Выбрать PDF'}
                          <input
                            hidden
                            type="file"
                            accept="application/pdf,.pdf"
                            onChange={handleUploadActFileSelect}
                          />
                        </Button>

                        <Button
                          variant="contained"
                          onClick={() => handleUploadActParse(false)}
                          disabled={!uploadActFile || uploadActParsing || uploadActCommitting}
                        >
                          {uploadActParsing ? 'Распознавание...' : 'Распознать акт'}
                        </Button>
                        <Button
                          variant="outlined"
                          onClick={() => handleUploadActParse(true)}
                          disabled={!uploadActFile || uploadActParsing || uploadActCommitting}
                        >
                          {uploadActParsing ? 'Подготовка...' : 'Заполнить вручную (без API)'}
                        </Button>
                      </Box>
                    </Paper>
                  </Fade>

                  {uploadActError && (
                    <Alert severity="error" onClose={() => setUploadActError('')}>
                      {uploadActError}
                    </Alert>
                  )}

                  <Collapse in={Boolean(uploadActDraft)} mountOnEnter unmountOnExit>
                    <Fade in={Boolean(uploadActDraft)} timeout={280}>
                      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                          2. Проверка данных акта
                        </Typography>

                        {Array.isArray(uploadActDraft?.warnings) && uploadActDraft.warnings.length > 0 && (
                          <Alert severity="warning" sx={{ mb: 1.5 }}>
                            {uploadActDraft.warnings.join(' | ')}
                          </Alert>
                        )}

                        <Box sx={{ display: 'grid', gap: 1.5 }}>
                          <TextField
                            label="Название документа"
                            value={uploadActForm.document_title}
                            onChange={(e) => setUploadActForm((prev) => ({ ...prev, document_title: e.target.value }))}
                            fullWidth
                            size={isMobile ? 'medium' : 'small'}
                          />
                          <Grid container spacing={1.5}>
                            <Grid item xs={12} md={6}>
                              <TextField
                                label="От сотрудника"
                                value={uploadActForm.from_employee}
                                onChange={(e) => setUploadActForm((prev) => ({ ...prev, from_employee: e.target.value }))}
                                fullWidth
                                size={isMobile ? 'medium' : 'small'}
                              />
                            </Grid>
                            <Grid item xs={12} md={6}>
                              <TextField
                                label="На сотрудника"
                                value={uploadActForm.to_employee}
                                onChange={(e) => setUploadActForm((prev) => ({ ...prev, to_employee: e.target.value }))}
                                fullWidth
                                size={isMobile ? 'medium' : 'small'}
                              />
                            </Grid>
                          </Grid>
                          <Grid container spacing={1.5}>
                            <Grid item xs={12} md={4}>
                              <TextField
                                label="Дата документа (YYYY-MM-DD)"
                                value={uploadActForm.doc_date}
                                onChange={(e) => setUploadActForm((prev) => ({ ...prev, doc_date: e.target.value }))}
                                fullWidth
                                size={isMobile ? 'medium' : 'small'}
                                placeholder="2026-02-17"
                              />
                            </Grid>
                            <Grid item xs={12} md={8}>
                              <TextField
                                label="Инв. № (через запятую)"
                                value={uploadActForm.equipment_inv_nos_text}
                                onChange={(e) => setUploadActForm((prev) => ({ ...prev, equipment_inv_nos_text: e.target.value }))}
                                fullWidth
                                size={isMobile ? 'medium' : 'small'}
                                placeholder="100887, 100888, 100889"
                              />
                            </Grid>
                          </Grid>

                          <FormControlLabel
                            control={
                              <Switch
                                checked={uploadActAutoEmail}
                                onChange={(e) => setUploadActAutoEmail(e.target.checked)}
                                color="primary"
                              />
                            }
                            label="Автоматически отправить акт на email участникам (От кого / На кого)"
                            sx={{ mt: 0.5, mb: 0.5 }}
                          />

                          <Paper variant="outlined" sx={{ p: 1.25 }}>
                            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                              Найденные позиции
                            </Typography>
                            {Array.isArray(uploadActDraft?.resolved_items) && uploadActDraft.resolved_items.length > 0 ? (
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>ID</TableCell>
                                    <TableCell>Инв. №</TableCell>
                                    <TableCell>Серийный №</TableCell>
                                    <TableCell>Модель</TableCell>
                                    <TableCell>Сотрудник</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {uploadActDraft.resolved_items.map((row, idx) => (
                                    <TableRow key={`${String(row?.item_id || 'unknown')}-${idx}`}>
                                      <TableCell>{row?.item_id || '-'}</TableCell>
                                      <TableCell>{row?.inv_no || '-'}</TableCell>
                                      <TableCell>{row?.serial_no || '-'}</TableCell>
                                      <TableCell>{row?.model_name || '-'}</TableCell>
                                      <TableCell>{row?.employee_name || '-'}</TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            ) : (
                              <Typography variant="body2" color="text.secondary">
                                Позиции не определены автоматически. Укажите инв. номера вручную.
                              </Typography>
                            )}
                          </Paper>
                        </Box>
                      </Paper>
                    </Fade>
                  </Collapse>
                </Box>
              </Collapse>

              <Collapse in={Boolean(uploadActCommitResult)} mountOnEnter unmountOnExit>
                <Fade in={Boolean(uploadActCommitResult)} timeout={260}>
                  <Box sx={{ display: 'grid', gap: 1.5 }}>
                    <Alert severity="success" variant="outlined">
                      Акт сохранён в базе: DOC_NO {uploadActCommitResult?.doc_no}, FILE_NO {uploadActCommitResult?.file_no}.
                    </Alert>

                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                        4. Отправка акта по email
                      </Typography>

                      {(uploadActEmailSummary.successCount > 0 || uploadActEmailSummary.failedCount > 0) && (
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1.5 }}>
                          <Chip
                            size="small"
                            color="success"
                            label={`Отправлено: ${uploadActEmailSummary.successCount}`}
                          />
                          <Chip
                            size="small"
                            color={uploadActEmailSummary.failedCount > 0 ? 'warning' : 'default'}
                            label={`Ошибок: ${uploadActEmailSummary.failedCount}`}
                          />
                          <Chip
                            size="small"
                            variant="outlined"
                            label={uploadActEmailSummary.mode === 'auto' ? 'Автоотправка' : 'Ручная отправка'}
                          />
                        </Box>
                      )}

                      <Box sx={{ display: 'grid', gap: 1.25 }}>
                        <TextField
                          label="Тема письма"
                          value={uploadActEmailSubject}
                          onChange={(e) => setUploadActEmailSubject(e.target.value)}
                          fullWidth
                          size={isMobile ? 'medium' : 'small'}
                        />
                        <TextField
                          label="Текст письма"
                          value={uploadActEmailBody}
                          onChange={(e) => setUploadActEmailBody(e.target.value)}
                          fullWidth
                          multiline
                          minRows={3}
                          size={isMobile ? 'medium' : 'small'}
                        />

                        <Autocomplete
                          multiple
                          options={uploadActEmailRecipientOptions}
                          loading={uploadActEmailRecipientsLoading}
                          value={uploadActEmailRecipients}
                          inputValue={uploadActEmailRecipientsInput}
                          onInputChange={(_, value) => setUploadActEmailRecipientsInput(value)}
                          onChange={(_, value) => {
                            setUploadActEmailRecipients(Array.isArray(value) ? value : []);
                            setUploadActEmailError('');
                          }}
                          getOptionLabel={(option) => {
                            const mapped = toOwnerOption(option);
                            if (!mapped.owner_display_name) return '';
                            return mapped.owner_dept
                              ? `${mapped.owner_display_name} (${mapped.owner_dept})`
                              : mapped.owner_display_name;
                          }}
                          isOptionEqualToValue={(option, value) =>
                            toNumberOrNull(option?.OWNER_NO ?? option?.owner_no) ===
                            toNumberOrNull(value?.OWNER_NO ?? value?.owner_no)
                          }
                          noOptionsText="Сотрудники не найдены"
                          renderInput={(params) => (
                            <TextField
                              {...params}
                              label="Отправить еще сотрудникам"
                              placeholder="Введите ФИО для поиска"
                              size={isMobile ? 'medium' : 'small'}
                            />
                          )}
                        />

                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                          <Button
                            variant="contained"
                            onClick={handleUploadActEmailSend}
                            disabled={uploadActEmailLoading}
                            startIcon={uploadActEmailLoading ? <CircularProgress size={16} color="inherit" /> : null}
                          >
                            {uploadActEmailLoading ? 'Отправка...' : 'Отправить выбранным'}
                          </Button>
                        </Box>
                      </Box>
                    </Paper>

                    {uploadActEmailStatus && (
                      <Alert severity="success">{uploadActEmailStatus}</Alert>
                    )}
                    {uploadActEmailError && (
                      <Alert severity="warning">{uploadActEmailError}</Alert>
                    )}

                    <Collapse in={Array.isArray(uploadActEmailLastRecipients) && uploadActEmailLastRecipients.length > 0}>
                      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                          Статусы отправки
                        </Typography>
                        <Box sx={{ display: 'grid', gap: 1 }}>
                          {uploadActEmailLastRecipients.map((recipient, idx) => {
                            const status = String(recipient?.status || '').trim();
                            const color =
                              status === 'sent'
                                ? 'success'
                                : status === 'missing_email' || status === 'not_found'
                                  ? 'warning'
                                  : 'error';
                            return (
                              <Fade
                                in
                                timeout={180 + (idx * 70)}
                                key={`${String(recipient?.owner_no || recipient?.employee_name || 'recipient')}-${idx}`}
                              >
                                <Box
                                  sx={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    gap: 1,
                                    p: 1,
                                    border: '1px solid',
                                    borderColor: 'divider',
                                    borderRadius: 1,
                                  }}
                                >
                                  <Box>
                                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                      {recipient?.employee_name || 'Неизвестный сотрудник'}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                      {recipient?.email || recipient?.detail || '-'}
                                    </Typography>
                                  </Box>
                                  <Chip
                                    size="small"
                                    color={color}
                                    label={
                                      status === 'sent'
                                        ? 'Отправлено'
                                        : status === 'missing_email'
                                          ? 'Нет email'
                                          : status === 'not_found'
                                            ? 'Не найден'
                                            : 'Ошибка'
                                    }
                                  />
                                </Box>
                              </Fade>
                            );
                          })}
                        </Box>
                      </Paper>
                    </Collapse>
                  </Box>
                </Fade>
              </Collapse>
            </Box>
          </DialogContent>
          <DialogActions sx={{ p: 2 }}>
            <Button
              onClick={closeUploadActModal}
              variant="outlined"
              disabled={uploadActParsing || uploadActCommitting || uploadActEmailLoading}
            >
              {uploadActCommitResult ? 'Готово' : 'Закрыть'}
            </Button>
            {!uploadActCommitResult && (
              <Button
                onClick={handleUploadActCommit}
                variant="contained"
                disabled={
                  !uploadActDraft
                  || uploadActParsing
                  || uploadActCommitting
                  || uploadActEmailLoading
                }
              >
                {uploadActCommitting ? 'Запись...' : 'Подтвердить и записать'}
              </Button>
            )}
          </DialogActions>
        </Dialog>

        <Dialog
          open={addEquipmentModalOpen}
          onClose={closeAddEquipmentModal}
          maxWidth="md"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>Добавить оборудование</DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Box sx={{ display: 'grid', gap: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Обязательные поля отмечены `*`. Форма разделена на поля выбора из списка и поля ручного ввода.
              </Typography>
              <Alert severity="info" variant="outlined">
                Если сотрудника или модели нет в списке, вводите полное название:
                ФИО сотрудника полностью и полное имя модели оборудования.
              </Alert>

              <Fade in={addEquipmentModalOpen} timeout={280}>
                <Box sx={{
                  p: 1.5,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                  transition: 'transform 220ms ease, box-shadow 220ms ease',
                  '&:hover': { boxShadow: 2, transform: 'translateY(-1px)' },
                }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Chip size="small" color="primary" label="Выбор из списка" />
                    <Typography variant="subtitle2">Обязательные поля</Typography>
                  </Box>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <Autocomplete
                        options={addEmployeeOptions}
                        loading={addEmployeeLoading}
                        value={selectedAddEmployeeOption}
                        inputValue={addEmployeeInput}
                        onInputChange={(_, value, reason) => {
                          if (reason !== 'input' && reason !== 'clear') return;
                          const nextValue = String(value || '');
                          setAddEmployeeInput(nextValue);
                          setAddEquipmentForm((prev) => ({
                            ...prev,
                            employee_name: nextValue,
                            employee_no: null,
                            employee_dept: '',
                          }));
                          setAddEquipmentError('');
                        }}
                        onChange={(_, value) => {
                          const option = toOwnerOption(value);
                          if (!option?.owner_no) {
                            return;
                          }
                          setAddEquipmentForm((prev) => ({
                            ...prev,
                            employee_name: option.owner_display_name || '',
                            employee_no: option.owner_no,
                            employee_dept: option.owner_dept || '',
                          }));
                          setAddEmployeeInput(option.owner_display_name || '');
                          setAddEquipmentError('');
                        }}
                        getOptionLabel={(option) => {
                          const mapped = toOwnerOption(option);
                          if (!mapped.owner_display_name) return '';
                          return mapped.owner_dept
                            ? `${mapped.owner_display_name} (${mapped.owner_dept})`
                            : mapped.owner_display_name;
                        }}
                        isOptionEqualToValue={(option, value) =>
                          toNumberOrNull(option?.OWNER_NO ?? option?.owner_no) ===
                          toNumberOrNull(value?.OWNER_NO ?? value?.owner_no)
                        }
                        noOptionsText="Сотрудники не найдены"
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="Сотрудник *"
                            placeholder="Выберите из списка или введите вручную"
                            size={isMobile ? 'medium' : 'small'}
                          />
                        )}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <FormControl size={isMobile ? 'medium' : 'small'} fullWidth required>
                        <InputLabel>Филиал *</InputLabel>
                        <Select
                          label="Филиал *"
                          value={addEquipmentForm.branch_no}
                          onChange={(e) => {
                            const value = toIdOrNull(e.target.value) || '';
                            setAddEquipmentForm((prev) => ({
                              ...prev,
                              branch_no: value,
                              loc_no: '',
                            }));
                            setAddLocations([]);
                            setAddEquipmentError('');
                          }}
                        >
                          <MenuItem value="">
                            <em>Выберите филиал</em>
                          </MenuItem>
                          {branchOptions.map((branch) => (
                            <MenuItem key={branch.branch_no} value={branch.branch_no}>
                              {branch.branch_name}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <LocationAutocompleteField
                        label="Местоположение *"
                        value={addEquipmentForm.loc_no}
                        options={addLocationOptions}
                        disabled={!addEquipmentForm.branch_no || addLocationsLoading}
                        loading={addLocationsLoading}
                        required
                        size={isMobile ? 'medium' : 'small'}
                        onChange={(locNo) => {
                          setAddEquipmentForm((prev) => ({
                            ...prev,
                            loc_no: toIdOrNull(locNo) || '',
                          }));
                          setAddEquipmentError('');
                        }}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <FormControl size={isMobile ? 'medium' : 'small'} fullWidth required>
                        <InputLabel>Тип оборудования *</InputLabel>
                        <Select
                          label="Тип оборудования *"
                          value={addEquipmentForm.type_no}
                          onChange={(e) => {
                            const value = String(e.target.value || '');
                            setAddEquipmentForm((prev) => ({
                              ...prev,
                              type_no: value,
                              model_name: '',
                              model_no: null,
                            }));
                            setAddModels([]);
                            setAddEquipmentError('');
                          }}
                        >
                          <MenuItem value="">
                            <em>Выберите тип</em>
                          </MenuItem>
                          {equipmentTypeOptions.map((type) => (
                            <MenuItem key={type.type_no} value={String(type.type_no)}>
                              {type.type_name}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12}>
                      <FormControl size={isMobile ? 'medium' : 'small'} fullWidth required>
                        <InputLabel>Статус *</InputLabel>
                        <Select
                          label="Статус *"
                          value={addEquipmentForm.status_no}
                          onChange={(e) => {
                            setAddEquipmentForm((prev) => ({
                              ...prev,
                              status_no: String(e.target.value || ''),
                            }));
                            setAddEquipmentError('');
                          }}
                        >
                          <MenuItem value="">
                            <em>Выберите статус</em>
                          </MenuItem>
                          {statusOptions.map((status) => (
                            <MenuItem key={status.status_no} value={String(status.status_no)}>
                              {status.status_name}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>
                </Box>
              </Fade>

              <Fade in={addEquipmentModalOpen} timeout={420}>
                <Box sx={{
                  p: 1.5,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                  transition: 'transform 220ms ease, box-shadow 220ms ease',
                  '&:hover': { boxShadow: 2, transform: 'translateY(-1px)' },
                }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Chip size="small" color="secondary" label="Вручную" />
                    <Typography variant="subtitle2">Серийный номер и модель обязательны</Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    Инвентарный номер генерируется автоматически при сохранении.
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="Серийный номер *"
                        value={addEquipmentForm.serial_number}
                        onChange={(e) => {
                          setAddEquipmentForm((prev) => ({ ...prev, serial_number: e.target.value }));
                          setAddEquipmentError('');
                        }}
                        size={isMobile ? 'medium' : 'small'}
                        fullWidth
                        required
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="Парт-номер (PART_NO)"
                        value={addEquipmentForm.part_no}
                        onChange={(e) => setAddEquipmentForm((prev) => ({ ...prev, part_no: e.target.value }))}
                        size={isMobile ? 'medium' : 'small'}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Autocomplete
                        freeSolo
                        options={addModelOptions}
                        loading={addModelsLoading}
                        inputValue={addEquipmentForm.model_name}
                        value={
                          addEquipmentForm.model_no
                            ? addModelOptions.find((model) => model.model_no === addEquipmentForm.model_no) || null
                            : null
                        }
                        onInputChange={(_, value, reason) => {
                          if (reason !== 'input' && reason !== 'clear') return;
                          setAddEquipmentForm((prev) => ({
                            ...prev,
                            model_name: String(value || ''),
                            model_no: null,
                          }));
                          setAddEquipmentError('');
                        }}
                        onChange={(_, value) => {
                          if (!value) {
                            setAddEquipmentForm((prev) => ({ ...prev, model_name: '', model_no: null }));
                            return;
                          }
                          if (typeof value === 'string') {
                            setAddEquipmentForm((prev) => ({ ...prev, model_name: value, model_no: null }));
                            return;
                          }
                          setAddEquipmentForm((prev) => ({
                            ...prev,
                            model_name: String(value.model_name || ''),
                            model_no: value.model_no ?? null,
                          }));
                          setAddEquipmentError('');
                        }}
                        getOptionLabel={(option) => (
                          typeof option === 'string' ? option : String(option?.model_name || '')
                        )}
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="Модель *"
                            placeholder="Введите модель или выберите из списка"
                            size={isMobile ? 'medium' : 'small'}
                            required
                          />
                        )}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="IP-адрес"
                        value={addEquipmentForm.ip_address}
                        onChange={(e) => setAddEquipmentForm((prev) => ({ ...prev, ip_address: e.target.value }))}
                        size={isMobile ? 'medium' : 'small'}
                        fullWidth
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        label="Описание"
                        value={addEquipmentForm.description}
                        onChange={(e) => setAddEquipmentForm((prev) => ({ ...prev, description: e.target.value }))}
                        size={isMobile ? 'medium' : 'small'}
                        fullWidth
                        multiline
                        minRows={3}
                      />
                    </Grid>
                  </Grid>
                  <Collapse in={addUsesManualEmployee} timeout={220}>
                    <Alert severity="info" sx={{ mt: 1.5 }}>
                      Сотрудник {addEquipmentForm.employee_name} не найден в списке и будет создан автоматически.
                    </Alert>
                  </Collapse>
                  <Collapse in={addUsesManualModel} timeout={260}>
                    <Alert severity="info" sx={{ mt: 1.5 }}>
                      Модель {addEquipmentForm.model_name} не найдена в списке и будет создана автоматически.
                    </Alert>
                  </Collapse>
                </Box>
              </Fade>

              <Collapse in={Boolean(addEquipmentError)} timeout={220}>
                <Alert severity="error">{addEquipmentError}</Alert>
              </Collapse>
              {addEquipmentSuccess && (
                <Typography variant="caption" color="text.secondary">
                  {addEquipmentSuccess}
                </Typography>
              )}
            </Box>
          </DialogContent>
          <DialogActions sx={{ p: 2 }}>
            <Button onClick={closeAddEquipmentModal} variant="outlined" disabled={addEquipmentLoading}>
              Закрыть
            </Button>
            <Button
              onClick={handleAddEquipmentSubmit}
              variant="contained"
              disabled={addEquipmentLoading}
              sx={{
                transition: 'transform 180ms ease, box-shadow 180ms ease',
                '&:hover': { transform: 'translateY(-1px)', boxShadow: 4 },
              }}
            >
              {addEquipmentLoading ? 'Сохранение...' : 'Добавить'}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={addConsumableModalOpen}
          onClose={closeAddConsumableModal}
          maxWidth="sm"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>Добавить расходник</DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Box sx={{ display: 'grid', gap: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Обязательные поля: филиал, местоположение, тип, модель и количество.
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <FormControl size={isMobile ? 'medium' : 'small'} fullWidth required>
                    <InputLabel>Филиал *</InputLabel>
                    <Select
                      label="Филиал *"
                      value={addConsumableForm.branch_no}
                      onChange={(e) => {
                        const value = toIdOrNull(e.target.value) || '';
                        setAddConsumableForm((prev) => ({
                          ...prev,
                          branch_no: value,
                          loc_no: '',
                        }));
                        setAddConsumableLocations([]);
                        setAddConsumableError('');
                      }}
                    >
                      <MenuItem value="">
                        <em>Выберите филиал</em>
                      </MenuItem>
                      {branchOptions.map((branch) => (
                        <MenuItem key={branch.branch_no} value={branch.branch_no}>
                          {branch.branch_name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>

                <Grid item xs={12} md={6}>
                  <LocationAutocompleteField
                    label="Местоположение *"
                    value={addConsumableForm.loc_no}
                    options={addConsumableLocationOptions}
                    disabled={!addConsumableForm.branch_no || addConsumableLocationsLoading}
                    loading={addConsumableLocationsLoading}
                    required
                    size={isMobile ? 'medium' : 'small'}
                    onChange={(locNo) => {
                      setAddConsumableForm((prev) => ({
                        ...prev,
                        loc_no: toIdOrNull(locNo) || '',
                      }));
                      setAddConsumableError('');
                    }}
                  />
                </Grid>

                <Grid item xs={12} md={6}>
                  <FormControl size={isMobile ? 'medium' : 'small'} fullWidth required>
                    <InputLabel>Тип расходника *</InputLabel>
                    <Select
                      label="Тип расходника *"
                      value={addConsumableForm.type_no}
                      onChange={(e) => {
                        const value = String(e.target.value || '');
                        setAddConsumableForm((prev) => ({
                          ...prev,
                          type_no: value,
                          model_name: '',
                          model_no: null,
                        }));
                        setAddConsumableModels([]);
                        setAddConsumableError('');
                      }}
                    >
                      <MenuItem value="">
                        <em>Выберите тип</em>
                      </MenuItem>
                      {consumableTypeOptions.map((type) => (
                        <MenuItem key={type.type_no} value={String(type.type_no)}>
                          {type.type_name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>

                <Grid item xs={12} md={6}>
                  <TextField
                    label="Количество *"
                    type="number"
                    inputProps={{ min: 1, step: 1 }}
                    value={addConsumableForm.qty}
                    onChange={(e) => {
                      setAddConsumableForm((prev) => ({ ...prev, qty: e.target.value }));
                      setAddConsumableError('');
                    }}
                    size={isMobile ? 'medium' : 'small'}
                    fullWidth
                    required
                  />
                </Grid>

                <Grid item xs={12}>
                  <Autocomplete
                    freeSolo
                    options={addConsumableModelOptions}
                    loading={addConsumableModelsLoading}
                    inputValue={addConsumableForm.model_name}
                    value={
                      addConsumableForm.model_no
                        ? addConsumableModelOptions.find((model) => model.model_no === addConsumableForm.model_no) || null
                        : null
                    }
                    onInputChange={(_, value, reason) => {
                      if (reason !== 'input' && reason !== 'clear') return;
                      setAddConsumableForm((prev) => ({
                        ...prev,
                        model_name: String(value || ''),
                        model_no: null,
                      }));
                      setAddConsumableError('');
                    }}
                    onChange={(_, value) => {
                      if (!value) {
                        setAddConsumableForm((prev) => ({ ...prev, model_name: '', model_no: null }));
                        return;
                      }
                      if (typeof value === 'string') {
                        setAddConsumableForm((prev) => ({ ...prev, model_name: value, model_no: null }));
                        return;
                      }
                      setAddConsumableForm((prev) => ({
                        ...prev,
                        model_name: String(value.model_name || ''),
                        model_no: value.model_no ?? null,
                      }));
                      setAddConsumableError('');
                    }}
                    getOptionLabel={(option) => (
                      typeof option === 'string' ? option : String(option?.model_name || '')
                    )}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Модель *"
                        placeholder="Введите модель или выберите из списка"
                        size={isMobile ? 'medium' : 'small'}
                        required
                      />
                    )}
                  />
                </Grid>
              </Grid>

              <Collapse
                in={
                  !addConsumableForm.model_no &&
                  String(addConsumableForm.model_name || '').trim().length >= 2 &&
                  toNumberOrNull(addConsumableForm.type_no) !== null
                }
                timeout={220}
              >
                <Alert severity="info">
                  Модель {addConsumableForm.model_name} не найдена в списке и будет создана автоматически.
                </Alert>
              </Collapse>

              <Collapse in={Boolean(addConsumableError)} timeout={220}>
                <Alert severity="error">{addConsumableError}</Alert>
              </Collapse>

              {addConsumableSuccess && (
                <Typography variant="caption" color="text.secondary">
                  {addConsumableSuccess}
                </Typography>
              )}
            </Box>
          </DialogContent>
          <DialogActions sx={{ p: 2 }}>
            <Button onClick={closeAddConsumableModal} variant="outlined" disabled={addConsumableLoading}>
              Закрыть
            </Button>
            <Button
              onClick={handleAddConsumableSubmit}
              variant="contained"
              disabled={addConsumableLoading}
            >
              {addConsumableLoading ? 'Сохранение...' : 'Добавить'}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={editConsumableQtyModal.open}
          onClose={closeEditConsumableQtyModal}
          maxWidth="xs"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>Изменить количество</DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Box sx={{ display: 'grid', gap: 1.5 }}>
              <Typography variant="body2" color="text.secondary">
                {String(
                  readFirst(editConsumableQtyModal.item, ['MODEL_NAME', 'model_name'], 'Расходник')
                )}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Инв. № {String(readFirst(editConsumableQtyModal.item, ['INV_NO', 'inv_no'], '-'))} | ID{' '}
                {String(readFirst(editConsumableQtyModal.item, ['ID', 'id'], '-'))}
              </Typography>
              <TextField
                label="Количество"
                type="number"
                value={editConsumableQtyValue}
                onChange={(e) => {
                  setEditConsumableQtyValue(e.target.value);
                  setEditConsumableQtyError('');
                }}
                inputProps={{ min: 0, step: 1 }}
                size={isMobile ? 'medium' : 'small'}
                fullWidth
                required
              />
              <Collapse in={Boolean(editConsumableQtyError)} timeout={220}>
                <Alert severity="error">{editConsumableQtyError}</Alert>
              </Collapse>
            </Box>
          </DialogContent>
          <DialogActions sx={{ p: 2 }}>
            <Button onClick={closeEditConsumableQtyModal} variant="outlined" disabled={editConsumableQtyLoading}>
              Закрыть
            </Button>
            <Button
              onClick={handleEditConsumableQtySubmit}
              variant="contained"
              disabled={editConsumableQtyLoading}
            >
              {editConsumableQtyLoading ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={detailModal.open}
          onClose={handleDetailClose}
          maxWidth="lg"
          fullWidth
          fullScreen={isMobile}
          scroll="paper"
          sx={{
            '& .MuiDialog-paper': {
              height: isMobile ? '100%' : '88vh',
              maxHeight: isMobile ? '100%' : '88vh',
            },
          }}
        >
          <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', px: 2, py: 1.5 }}>
            <Box>
              <Typography component="span" variant="h6">
                {readFirst(detailModal.data, ['MODEL_NAME', 'model_name'], 'Карточка оборудования')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Инв. № {readFirst(detailModal.data, ['INV_NO', 'inv_no'], '-')} | ID {readFirst(detailModal.data, ['ID', 'id'], '-')}
              </Typography>
            </Box>
            <IconButton onClick={handleDetailClose} edge="end">
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <Divider />
          <DialogContent sx={{ p: { xs: 1.5, md: 2 } }} onKeyDown={handleDetailEditKeyDown}>
            {detailModal.loading ? (
              <LoadingSpinner message="Загрузка..." />
            ) : detailModal.data && detailForm ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                {detailError && (
                  <Alert severity="error" onClose={() => setDetailError('')}>
                    {detailError}
                  </Alert>
                )}
                {detailSuccess && !detailEditMode && (
                  <Alert severity="success" onClose={() => setDetailSuccess('')}>
                    {detailSuccess}
                  </Alert>
                )}

                <Paper variant="outlined" sx={{ p: 0.5 }}>
                  <Tabs
                    value={detailTab}
                    onChange={(_, value) => setDetailTab(value)}
                    variant="fullWidth"
                  >
                    <Tab label="Общее" value="general" />
                    <Tab label="Текущий акт" value="acts" disabled={detailEditMode} />
                  </Tabs>
                </Paper>

                {detailTab === 'general' ? (
                  <>
                    <Paper variant="outlined" sx={{ p: 1.5 }}>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                        <Chip label={`Инв. № ${readFirst(detailModal.data, ['INV_NO', 'inv_no'], '-')}`} size="small" />
                        <Chip label={`ID ${readFirst(detailModal.data, ['ID', 'id'], '-')}`} size="small" variant="outlined" />
                        {!detailEditMode ? (
                          <StatusChip
                            status={readFirst(detailModal.data, ['DESCR', 'status_name', 'status'], '-')}
                            size="small"
                          />
                        ) : (
                          <FormControl size="small" sx={{ minWidth: 220 }}>
                            <InputLabel>Статус</InputLabel>
                            <Select
                              value={detailForm.status_no ?? ''}
                              onChange={(e) => setDetailForm((prev) => ({ ...prev, status_no: toNumberOrNull(e.target.value) }))}
                              label="Статус"
                            >
                              {statusOptions.map((status) => (
                                <MenuItem key={status.status_no} value={status.status_no}>
                                  {status.status_name}
                                </MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        )}
                        <Chip label={detailForm.branch_name || 'Филиал не указан'} size="small" variant="outlined" />
                        <Chip label={detailForm.location_name || 'Местоположение не указано'} size="small" variant="outlined" />
                      </Box>
                    </Paper>

                    <Grid container spacing={1.5}>
                      <Grid item xs={12} lg={7}>
                        <Paper variant="outlined" sx={{ p: 1.5, height: '100%' }}>
                          <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 600 }}>
                            Идентификация
                          </Typography>
                          <Grid container spacing={1.25}>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <FormControl fullWidth size={isMobile ? 'medium' : 'small'}>
                                  <InputLabel>Тип оборудования</InputLabel>
                                  <Select
                                    value={detailForm.type_no ?? ''}
                                    label="Тип оборудования"
                                    onChange={(e) => {
                                      const typeNo = toNumberOrNull(e.target.value);
                                      const selectedType = equipmentTypeOptions.find((type) => type.type_no === typeNo);
                                      setDetailForm((prev) => ({
                                        ...prev,
                                        type_no: typeNo,
                                        type_name: selectedType?.type_name || '',
                                        model_no: null,
                                        model_name: '',
                                      }));
                                    }}
                                  >
                                    {equipmentTypeOptions.map((type) => (
                                      <MenuItem key={type.type_no} value={type.type_no}>
                                        {type.type_name}
                                      </MenuItem>
                                    ))}
                                  </Select>
                                </FormControl>
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Тип оборудования</Typography>
                                  <Typography variant="body2">{detailForm.type_name || '-'}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <FormControl
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  disabled={!detailForm.type_no || detailModelsLoading}
                                >
                                  <InputLabel>Модель</InputLabel>
                                  <Select
                                    value={detailForm.model_no ?? ''}
                                    label="Модель"
                                    onChange={(e) => {
                                      const modelNo = toNumberOrNull(e.target.value);
                                      const selectedModel = modelOptions.find((model) => model.model_no === modelNo);
                                      setDetailForm((prev) => ({
                                        ...prev,
                                        model_no: modelNo,
                                        model_name: selectedModel?.model_name || '',
                                      }));
                                    }}
                                  >
                                    {modelOptions.map((model) => (
                                      <MenuItem key={model.model_no} value={model.model_no}>
                                        {model.model_name}
                                      </MenuItem>
                                    ))}
                                  </Select>
                                </FormControl>
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Модель</Typography>
                                  <Typography variant="body2">{detailForm.model_name || '-'}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={6}>
                              <Typography variant="caption" color="text.secondary">Производитель</Typography>
                              <Typography variant="body2">
                                {readFirst(detailModal.data, ['VENDOR_NAME', 'vendor_name', 'MANUFACTURER', 'manufacturer'], '-')}
                              </Typography>
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <TextField
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  label="Серийный номер"
                                  value={detailForm.serial_no}
                                  onChange={(e) => setDetailForm((prev) => ({ ...prev, serial_no: e.target.value }))}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Серийный номер</Typography>
                                  <Typography variant="body2">{readFirst(detailModal.data, ['SERIAL_NO', 'serial_no'], '-')}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <TextField
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  label="Аппаратный серийный номер"
                                  value={detailForm.hw_serial_no}
                                  onChange={(e) => setDetailForm((prev) => ({ ...prev, hw_serial_no: e.target.value }))}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">HW серийный номер</Typography>
                                  <Typography variant="body2">{readFirst(detailModal.data, ['HW_SERIAL_NO', 'hw_serial_no'], '-')}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <TextField
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  label="Part Number"
                                  value={detailForm.part_no}
                                  onChange={(e) => setDetailForm((prev) => ({ ...prev, part_no: e.target.value }))}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Part Number</Typography>
                                  <Typography variant="body2">{readFirst(detailModal.data, ['PART_NO', 'part_no'], '-')}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <TextField
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  label="IP-адрес"
                                  value={detailForm.ip_address}
                                  onChange={(e) => setDetailForm((prev) => ({ ...prev, ip_address: e.target.value }))}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">IP-адрес</Typography>
                                  <Typography variant="body2">{detailForm.ip_address || '-'}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <TextField
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  label="MAC-адрес"
                                  value={detailForm.mac_address}
                                  onChange={(e) => setDetailForm((prev) => ({ ...prev, mac_address: e.target.value }))}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">MAC-адрес</Typography>
                                  <Typography variant="body2">{detailForm.mac_address || '-'}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <TextField
                                  fullWidth
                                  size={isMobile ? 'medium' : 'small'}
                                  label="Имя компьютера"
                                  value={detailForm.network_name}
                                  onChange={(e) => setDetailForm((prev) => ({ ...prev, network_name: e.target.value }))}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Имя компьютера</Typography>
                                  <Typography variant="body2">{detailForm.network_name || detailForm.domain_name || '-'}</Typography>
                                </>
                              )}
                            </Grid>
                            <Grid item xs={12} sm={6}>
                              <Typography variant="caption" color="text.secondary">Домен</Typography>
                              <Typography variant="body2">{detailForm.domain_name || '-'}</Typography>
                            </Grid>
                          </Grid>
                        </Paper>
                      </Grid>

                      <Grid item xs={12} lg={5}>
                        <Paper variant="outlined" sx={{ p: 1.5, height: '100%' }}>
                          <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 600 }}>
                            Назначение
                          </Typography>
                          <Grid container spacing={1.25}>
                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              <Typography variant="caption" color="text.secondary">Сотрудник</Typography>
                              <Typography variant="body2">{detailForm.employee_name || '-'}</Typography>
                              <Typography variant="caption" color="text.secondary">
                                Отдел: {detailForm.employee_dept || '-'}
                              </Typography>
                              <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 0.5 }}>
                                Изменение сотрудника доступно только через операцию «Перемещение».
                              </Typography>
                            </Grid>

                            <Grid item xs={12} sm={detailEditMode ? 12 : 6}>
                              {detailEditMode ? (
                                <FormControl fullWidth size={isMobile ? 'medium' : 'small'}>
                                  <InputLabel>Филиал</InputLabel>
                                  <Select
                                    value={detailForm.branch_no ?? ''}
                                    label="Филиал"
                                    onChange={(e) => {
                                      const branchNo = toIdOrNull(e.target.value);
                                      const selectedBranchOption = branchOptions.find((branch) => branch.branch_no === branchNo);
                                      setDetailForm((prev) => ({
                                        ...prev,
                                        branch_no: branchNo,
                                        branch_name: selectedBranchOption?.branch_name || '',
                                        loc_no: null,
                                        location_name: '',
                                      }));
                                    }}
                                  >
                                    {branchOptions.map((branch) => (
                                      <MenuItem key={branch.branch_no} value={branch.branch_no}>
                                        {branch.branch_name}
                                      </MenuItem>
                                    ))}
                                  </Select>
                                </FormControl>
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Филиал</Typography>
                                  <Typography variant="body2">{detailForm.branch_name || '-'}</Typography>
                                </>
                              )}
                            </Grid>

                            <Grid item xs={12}>
                              {detailEditMode ? (
                                <LocationAutocompleteField
                                  label="Местоположение"
                                  value={detailForm.loc_no ?? ''}
                                  options={locationOptions}
                                  disabled={!detailForm.branch_no}
                                  size={isMobile ? 'medium' : 'small'}
                                  onChange={(locNo) => {
                                    const selectedLocation = locationOptions.find((location) => location.loc_no === toIdOrNull(locNo));
                                    setDetailForm((prev) => ({
                                      ...prev,
                                      loc_no: toIdOrNull(locNo),
                                      location_name: selectedLocation?.loc_name || '',
                                    }));
                                  }}
                                />
                              ) : (
                                <>
                                  <Typography variant="caption" color="text.secondary">Местоположение</Typography>
                                  <Typography variant="body2">{detailForm.location_name || '-'}</Typography>
                                </>
                              )}
                            </Grid>
                          </Grid>
                        </Paper>
                      </Grid>

                      <Grid item xs={12}>
                        <Paper variant="outlined" sx={{ p: 1.5 }}>
                          <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 600 }}>
                            Описание
                          </Typography>
                          {detailEditMode ? (
                            <TextField
                              fullWidth
                              multiline
                              minRows={4}
                              maxRows={10}
                              label="Описание"
                              value={detailForm.description}
                              onChange={(e) => setDetailForm((prev) => ({ ...prev, description: e.target.value }))}
                            />
                          ) : (
                            <Typography
                              variant="body2"
                              sx={{
                                whiteSpace: 'pre-wrap',
                                maxHeight: 140,
                                overflowY: 'auto',
                                pr: 0.5,
                              }}
                            >
                              {detailForm.description || 'Описание отсутствует'}
                            </Typography>
                          )}
                        </Paper>
                      </Grid>
                    </Grid>
                  </>
                ) : (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    {detailActsError && (
                      <Alert severity="error" onClose={() => setDetailActsError('')}>
                        {detailActsError}
                      </Alert>
                    )}
                    {detailActsLoading ? (
                      <LoadingSpinner message="Загрузка актов..." />
                    ) : detailActs.length === 0 ? (
                      <Paper variant="outlined" sx={{ p: 2 }}>
                        <Typography variant="body2" color="text.secondary">
                          Для этого оборудования не найдено привязанных актов.
                        </Typography>
                      </Paper>
                    ) : (
                      <>
                        <Paper variant="outlined" sx={{ p: 2 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            Текущий акт
                          </Typography>
                          <Typography variant="body2">
                            № {readFirst(detailActs[0], ['doc_number', 'DOC_NUMBER'], '-')}
                            {' | '}
                            Дата: {formatDate(readFirst(detailActs[0], ['doc_date', 'DOC_DATE'], ''))}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                            Создан: {formatDate(readFirst(detailActs[0], ['create_date', 'CREATE_DATE'], ''))}
                          </Typography>
                        </Paper>

                        <TableContainer component={Paper} variant="outlined">
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>№ документа</TableCell>
                                <TableCell>Дата</TableCell>
                                <TableCell>Тип</TableCell>
                                <TableCell>Филиал / Локация</TableCell>
                                <TableCell>Сотрудник</TableCell>
                                <TableCell align="right">Действия</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {detailActs.map((act, index) => (
                                <TableRow key={`${readFirst(act, ['doc_no', 'DOC_NO'], index)}-${index}`} hover>
                                  <TableCell>{readFirst(act, ['doc_number', 'DOC_NUMBER'], '-')}</TableCell>
                                  <TableCell>{formatDate(readFirst(act, ['doc_date', 'DOC_DATE'], ''))}</TableCell>
                                  <TableCell>{readFirst(act, ['type_name', 'TYPE_NAME', 'type_no', 'TYPE_NO'], '-')}</TableCell>
                                  <TableCell>
                                    {readFirst(act, ['branch_name', 'BRANCH_NAME'], '-')}
                                    {' / '}
                                    {readFirst(act, ['location_name', 'LOCATION_NAME'], '-')}
                                  </TableCell>
                                  <TableCell>{readFirst(act, ['employee_name', 'EMPLOYEE_NAME'], '-')}</TableCell>
                                  <TableCell align="right">
                                    <Box
                                      sx={{
                                        display: 'flex',
                                        flexWrap: 'wrap',
                                        gap: 0.75,
                                        alignItems: 'center',
                                        justifyContent: 'flex-end',
                                      }}
                                    >
                                      <Button
                                        size="small"
                                        variant="outlined"
                                        onClick={() => handleOpenActFields(act)}
                                      >
                                        Поля
                                      </Button>
                                      <Button
                                        size="small"
                                        variant="outlined"
                                        onClick={() => handleOpenEquipmentActFile(act)}
                                        disabled={detailActOpeningDocNo === String(readFirst(act, ['doc_no', 'DOC_NO'], ''))}
                                      >
                                        {detailActOpeningDocNo === String(readFirst(act, ['doc_no', 'DOC_NO'], '')) ? 'Открытие...' : 'Открыть'}
                                      </Button>
                                    </Box>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    )}
                  </Box>
                )}
              </Box>
            ) : (
              <Typography color="error">Ошибка загрузки данных</Typography>
            )}
          </DialogContent>
          <DialogActions sx={{ p: 2, justifyContent: 'flex-end', gap: 1 }}>
            {detailModal.data && detailTab === 'general' && canDatabaseWrite && (
              detailEditMode ? (
                <>
                  <Button onClick={handleDetailCancel} variant="outlined" disabled={detailSaving}>
                    Отмена
                  </Button>
                  <Button onClick={handleDetailSave} variant="contained" disabled={detailSaving || !detailHasChanges}>
                    {detailSaving ? 'Сохранение...' : 'Сохранить'}
                  </Button>
                </>
              ) : (
                <Button
                  onClick={() => {
                    setDetailError('');
                    setDetailSuccess('');
                    setDetailEditMode(true);
                  }}
                  variant="contained"
                >
                  Редактировать
                </Button>
              )
            )}
            {detailModal.data && detailTab === 'general' && !detailEditMode && (
              <Button
                onClick={() => setDetailQrOpen(true)}
                variant="outlined"
                startIcon={<QrCode2Icon />}
              >
                Создать QR-code
              </Button>
            )}
            <Button onClick={handleDetailClose} variant="outlined">
              Закрыть
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={detailActFieldsOpen}
          onClose={handleCloseActFields}
          maxWidth="md"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>
            Поля документа{' '}
            {detailActSelected
              ? `№ ${readFirst(detailActSelected, ['doc_number', 'DOC_NUMBER', 'doc_no', 'DOC_NO'], '-')}`
              : ''}
          </DialogTitle>
          <DialogContent dividers>
            {!detailActSummary ? (
              <Typography variant="body2" color="text.secondary">
                Документ не выбран.
              </Typography>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
                    gap: 1.5,
                  }}
                >
                  <Paper variant="outlined" sx={{ p: 1.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                      Документ
                    </Typography>
                    <Box sx={{ display: 'grid', gridTemplateColumns: '130px 1fr', rowGap: 0.5, columnGap: 1 }}>
                      <Typography variant="body2" color="text.secondary">Номер</Typography>
                      <Typography variant="body2">{detailActSummary.docNumber}</Typography>
                      <Typography variant="body2" color="text.secondary">DOC_NO</Typography>
                      <Typography variant="body2">{detailActSummary.docNo}</Typography>
                      <Typography variant="body2" color="text.secondary">Дата</Typography>
                      <Typography variant="body2">{formatDate(detailActSummary.docDate)}</Typography>
                      <Typography variant="body2" color="text.secondary">Тип</Typography>
                      <Typography variant="body2">{detailActSummary.typeName}</Typography>
                    </Box>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                      Привязка
                    </Typography>
                    <Box sx={{ display: 'grid', gridTemplateColumns: '130px 1fr', rowGap: 0.5, columnGap: 1 }}>
                      <Typography variant="body2" color="text.secondary">Филиал</Typography>
                      <Typography variant="body2">{detailActSummary.branchName}</Typography>
                      <Typography variant="body2" color="text.secondary">Локация</Typography>
                      <Typography variant="body2">{detailActSummary.locationName}</Typography>
                      <Typography variant="body2" color="text.secondary">Сотрудник</Typography>
                      <Typography variant="body2">{detailActSummary.employeeName}</Typography>
                      <Typography variant="body2" color="text.secondary">ITEM_ID</Typography>
                      <Typography variant="body2">{detailActSummary.itemId}</Typography>
                    </Box>
                  </Paper>
                </Box>
                <Paper variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                    Служебное
                  </Typography>
                  <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '130px 1fr' }, rowGap: 0.5, columnGap: 1 }}>
                    <Typography variant="body2" color="text.secondary">Создан</Typography>
                    <Typography variant="body2">
                      {formatDate(detailActSummary.createDate)} / {detailActSummary.createUser}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Изменен</Typography>
                    <Typography variant="body2">
                      {formatDate(detailActSummary.changeDate)} / {detailActSummary.changeUser}
                    </Typography>
                  </Box>
                </Paper>
                {detailActSummary.addInfo && (
                  <Paper variant="outlined" sx={{ p: 1.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                      Описание
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {detailActSummary.addInfo}
                    </Typography>
                  </Paper>
                )}
              </Box>
            )}
          </DialogContent>
          <DialogActions sx={{ p: 2 }}>
            {detailActSelected && (
              <Button
                variant="outlined"
                onClick={() => handleOpenEquipmentActFile(detailActSelected)}
                disabled={detailActOpeningDocNo === String(readFirst(detailActSelected, ['doc_no', 'DOC_NO'], ''))}
              >
                {detailActOpeningDocNo === String(readFirst(detailActSelected, ['doc_no', 'DOC_NO'], ''))
                  ? 'Открытие...'
                  : 'Открыть файл'}
              </Button>
            )}
            <Button variant="contained" onClick={handleCloseActFields}>
              Закрыть
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={detailQrOpen}
          onClose={() => setDetailQrOpen(false)}
          maxWidth="xs"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>QR-code оборудования</DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
              {detailQrUrl ? (
                <Box
                  component="img"
                  src={detailQrUrl}
                  alt="Equipment QR"
                  sx={{
                    width: isMobile ? 260 : 300,
                    height: isMobile ? 260 : 300,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    backgroundColor: '#fff',
                    p: 1,
                  }}
                />
              ) : (
                <Alert severity="warning" sx={{ width: '100%' }}>
                  Недостаточно данных для генерации QR-code.
                </Alert>
              )}
              <TextField
                fullWidth
                multiline
                minRows={4}
                label="Содержимое QR"
                value={detailQrText}
                InputProps={{ readOnly: true }}
              />
            </Box>
          </DialogContent>
          <DialogActions sx={{ p: 2 }}>
            <Button onClick={() => setDetailQrOpen(false)} variant="outlined">
              Закрыть
            </Button>
            <Button
              component="a"
              href={detailQrUrl || '#'}
              target="_blank"
              rel="noopener noreferrer"
              download={detailQrFileName}
              variant="contained"
              disabled={!detailQrUrl}
            >
              Скачать PNG
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={actionModal.open}
          onClose={() => {
            setActionModal({ open: false, type: null, invNo: null, componentKind: null });
            setActionError('');
            resetTransferState();
            setCartridgeModel('');
            setSelectedWorkConsumable(null);
            setWorkConsumableOptions([]);
            setWorkConsumablesLoading(false);
            setCartridgeHistory(null);
            setComponentType(PRINTER_COMPONENT_OPTIONS[0].value);
            setBatteryHistory(null);
            setComponentHistory(null);
            setCleaningHistory(null);
          }}
          maxWidth="sm"
          fullWidth
          fullScreen={isMobile}
        >
          <DialogTitle>
            {actionModal.type === 'transfer' && 'Перемещение оборудования'}
            {actionModal.type === 'cartridge' && 'Замена картриджа'}
            {actionModal.type === 'battery' && 'Замена батареи'}
            {actionModal.type === 'component' && (actionModal.componentKind === 'pc' ? 'Замена компонента ПК' : 'Замена компонента')}
            {actionModal.type === 'cleaning' && 'Чистка ПК'}
          </DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {selectedItems.length > 1
                ? 'Выбрано ' + selectedItems.length + ' ед. оборудования'
                : selectedItems.length === 1
                  ? 'Выбрано 1 ед. оборудования'
                  : 'Подтвердите действие.'}
            </Typography>

            {actionModal.type === 'transfer' && (
              <Box sx={{ display: 'grid', gap: 2 }}>
                {!transferResult && (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      Текущие значения по умолчанию: {transferSourceDefaults.branch_name || '-'} / {transferSourceDefaults.location_name || '-'}
                    </Typography>
                    {(transferSourceDefaults.mixed_branch || transferSourceDefaults.mixed_location) && (
                      <Alert severity="info">
                        Выбраны позиции из разных филиалов или локаций. Указанные ниже значения будут применены ко всем выбранным позициям.
                      </Alert>
                    )}
                    <Autocomplete
                      options={transferEmployeeAutocompleteOptions}
                      loading={transferEmployeeLoading}
                      value={selectedTransferEmployeeOption}
                      inputValue={transferEmployeeInput}
                      clearOnBlur={false}
                      onInputChange={(_, value, reason) => {
                        if (reason !== 'input' && reason !== 'clear') {
                          return;
                        }
                        const nextValue = String(value || '');
                        setTransferEmployeeInput(nextValue);
                        setActionError('');
                        const normalizedNext = normalizeText(nextValue);
                        const normalizedCurrent = normalizeText(newEmployee);
                        if (newEmployeeNo || (newEmployee && normalizedNext !== normalizedCurrent)) {
                          setNewEmployee('');
                          setNewEmployeeNo(null);
                          setTransferDepartment('');
                        }
                      }}
                      onChange={(_, value) => {
                        if (value?.__create) {
                          handleCreateTransferEmployee();
                          return;
                        }
                        const option = toOwnerOption(value);
                        if (!option?.owner_no) {
                          setNewEmployee('');
                          setNewEmployeeNo(null);
                          setTransferDepartment('');
                          setActionError('');
                          return;
                        }
                        setNewEmployee(option.owner_display_name || '');
                        setNewEmployeeNo(option.owner_no);
                        setTransferDepartment(option.owner_dept || '');
                        setTransferEmployeeInput(option.owner_display_name || '');
                        setActionError('');
                      }}
                      getOptionLabel={(option) => {
                        if (option?.__create) {
                          return `Добавить сотрудника: ${transferEmployeeInputTrimmed}`;
                        }
                        const mapped = toOwnerOption(option);
                        if (!mapped.owner_display_name) return '';
                        return mapped.owner_dept
                          ? `${mapped.owner_display_name} (${mapped.owner_dept})`
                          : mapped.owner_display_name;
                      }}
                      renderOption={(props, option) => {
                        const { key, ...restProps } = props;
                        if (option?.__create) {
                          return (
                            <li key={key} {...restProps}>
                              <Button
                                variant="outlined"
                                size="small"
                                fullWidth
                                sx={{ pointerEvents: 'none', justifyContent: 'flex-start' }}
                              >
                                Добавить сотрудника: {transferEmployeeInputTrimmed}
                              </Button>
                            </li>
                          );
                        }
                        const mapped = toOwnerOption(option);
                        return (
                          <li key={key} {...restProps}>
                            {mapped.owner_dept
                              ? `${mapped.owner_display_name} (${mapped.owner_dept})`
                              : mapped.owner_display_name}
                          </li>
                        );
                      }}
                      isOptionEqualToValue={(option, value) =>
                        toNumberOrNull(option?.OWNER_NO ?? option?.owner_no) ===
                        toNumberOrNull(value?.OWNER_NO ?? value?.owner_no)
                      }
                      noOptionsText="Сотрудники не найдены"
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          autoFocus
                          label="Новый сотрудник"
                          placeholder="Начните вводить ФИО"
                          size={isMobile ? 'medium' : 'small'}
                          helperText="Введите минимум 2 символа для поиска"
                        />
                      )}
                    />
                    {transferUsesManualEmployee && (
                      <Alert severity="info">
                        Сотрудник {newEmployee} будет создан автоматически при перемещении, если его нет в базе.
                      </Alert>
                    )}
                    {transferUsesManualEmployee && (
                      <FormControl
                        size={isMobile ? 'medium' : 'small'}
                        fullWidth
                        required
                        error={!transferDepartment}
                        disabled={transferDepartmentLoading}
                      >
                        <InputLabel>Отдел нового сотрудника</InputLabel>
                        <Select
                          label="Отдел нового сотрудника"
                          value={transferDepartment}
                          onChange={(e) => {
                            setTransferDepartment(String(e.target.value || '').trim());
                            setActionError('');
                          }}
                        >
                          <MenuItem value="">
                            <em>Выберите отдел</em>
                          </MenuItem>
                          {transferDepartmentOptions.map((dept) => (
                            <MenuItem key={dept} value={dept}>
                              {dept}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    )}
                    <FormControl size={isMobile ? 'medium' : 'small'} fullWidth>
                      <InputLabel>Филиал назначения</InputLabel>
                      <Select
                        label="Филиал назначения"
                        value={transferBranchNo ?? ''}
                        onChange={(e) => {
                          const value = toIdOrNull(e.target.value);
                          setTransferBranchNo(value);
                          setTransferLocationNo(null);
                          setTransferLocations([]);
                          setActionError('');
                        }}
                      >
                        <MenuItem value="">
                          <em>Выберите филиал</em>
                        </MenuItem>
                        {branchOptions.map((branch) => (
                          <MenuItem key={branch.branch_no} value={branch.branch_no}>
                            {branch.branch_name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl
                      size={isMobile ? 'medium' : 'small'}
                      fullWidth
                      disabled={!transferBranchNo || transferLocationsLoading}
                    >
                      <LocationAutocompleteField
                        label="Местоположение назначения"
                        value={transferLocationNo ?? ''}
                        options={transferLocationOptions}
                        disabled={!transferBranchNo || transferLocationsLoading}
                        loading={transferLocationsLoading}
                        size={isMobile ? 'medium' : 'small'}
                        onChange={(locNo) => {
                          setTransferLocationNo(toIdOrNull(locNo));
                          setActionError('');
                        }}
                      />
                    </FormControl>
                    {transferLocationsLoading && (
                      <Typography variant="caption" color="text.secondary">
                        Загрузка списка местоположений...
                      </Typography>
                    )}
                  </>
                )}

                {transferResult && (
                  <Box sx={{ display: 'grid', gap: 1.5 }}>
                    <Alert severity={transferResult.failed_count > 0 ? 'warning' : 'success'}>
                      Перенесено: {transferResult.success_count}, ошибок: {transferResult.failed_count}
                    </Alert>

                    {Array.isArray(transferResult.failed) && transferResult.failed.length > 0 && (
                      <Box>
                        {transferResult.failed.slice(0, 5).map((failedItem, idx) => (
                          <Typography key={`${failedItem.inv_no}-${idx}`} variant="body2" color="error">
                            {failedItem.inv_no}: {failedItem.error}
                          </Typography>
                        ))}
                      </Box>
                    )}

                    {Array.isArray(transferResult.acts) && transferResult.acts.length > 0 && (
                      <Box sx={{ display: 'grid', gap: 1 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                          Сформированные акты
                        </Typography>
                        {transferResult.acts.map((act) => (
                          <Box
                            key={act.act_id}
                            sx={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: 1,
                              p: 1,
                              border: '1px solid',
                              borderColor: 'divider',
                              borderRadius: 1,
                            }}
                          >
                            <Typography variant="body2">
                              {act.old_employee} ({act.equipment_count})
                            </Typography>
                            <Button size="small" variant="outlined" onClick={() => handleTransferActDownload(act)}>
                              Скачать
                            </Button>
                          </Box>
                        ))}
                      </Box>
                    )}

                    <Divider />

                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                      Отправка акта по email
                    </Typography>
                    <FormControl size={isMobile ? 'medium' : 'small'} fullWidth>
                      <InputLabel>Кому отправить</InputLabel>
                      <Select
                        label="Кому отправить"
                        value={transferEmailMode}
                        onChange={(e) => setTransferEmailMode(e.target.value)}
                      >
                        <MenuItem value="old">Старому сотруднику</MenuItem>
                        <MenuItem value="new">Новому сотруднику</MenuItem>
                        <MenuItem value="employee">Выбрать сотрудника</MenuItem>
                        <MenuItem value="manual">Ввести email вручную</MenuItem>
                      </Select>
                    </FormControl>

                    {transferEmailMode === 'manual' && (
                      <TextField
                        fullWidth
                        label="Email получателя"
                        value={transferManualEmail}
                        onChange={(e) => setTransferManualEmail(e.target.value)}
                        size={isMobile ? 'medium' : 'small'}
                      />
                    )}

                    {transferEmailMode === 'employee' && (
                      <Autocomplete
                        options={transferRecipientOptions}
                        loading={transferRecipientLoading}
                        value={transferRecipient}
                        inputValue={transferRecipientInput}
                        onInputChange={(_, value) => setTransferRecipientInput(value)}
                        onChange={(_, value) => setTransferRecipient(value)}
                        getOptionLabel={(option) => {
                          const mapped = toOwnerOption(option);
                          if (!mapped.owner_display_name) return '';
                          return mapped.owner_dept
                            ? `${mapped.owner_display_name} (${mapped.owner_dept})`
                            : mapped.owner_display_name;
                        }}
                        isOptionEqualToValue={(option, value) =>
                          toNumberOrNull(option?.OWNER_NO ?? option?.owner_no) ===
                          toNumberOrNull(value?.OWNER_NO ?? value?.owner_no)
                        }
                        noOptionsText="Сотрудники не найдены"
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            label="Сотрудник-получатель"
                            placeholder="Введите ФИО"
                            size={isMobile ? 'medium' : 'small'}
                          />
                        )}
                      />
                    )}

                    {transferEmailStatus && (
                      <Alert severity="success">{transferEmailStatus}</Alert>
                    )}
                    {transferEmailError && (
                      <Alert severity="error">{transferEmailError}</Alert>
                    )}

                    <Button
                      variant="contained"
                      onClick={handleTransferEmailSend}
                      disabled={!canDatabaseWrite || transferEmailLoading}
                    >
                      {transferEmailLoading ? 'Отправка...' : 'Отправить акт'}
                    </Button>
                  </Box>
                )}
              </Box>
            )}

            {actionModal.type === 'cartridge' && (
              <>
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <Autocomplete
                      options={actionWorkConsumableOptions}
                      loading={workConsumablesLoading}
                      value={selectedWorkConsumable}
                      onChange={(_, value) => setSelectedWorkConsumable(value || null)}
                      isOptionEqualToValue={(option, value) =>
                        toNumberOrNull(option?.id) === toNumberOrNull(value?.id)
                      }
                      getOptionLabel={(option) => formatConsumableSourceLabel(option)}
                      renderOption={(props, option) => {
                        const { key, ...restProps } = props;
                        const normalized = toConsumableSourceOption(option);
                        return (
                          <li key={key} {...restProps}>
                            <Box sx={{ display: 'grid' }}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {normalized.model_name || '-'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {normalized.type_name || '-'} | {normalized.branch_name || '-'} / {normalized.location_name || '-'} | Остаток: {normalized.qty}
                              </Typography>
                            </Box>
                          </li>
                        );
                      }}
                      noOptionsText={
                        actionModal.componentKind === 'printer'
                          ? 'Нет запчастей (картриджи скрыты)'
                          : 'Расходники не найдены'
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="Картридж / расходник"
                          placeholder="Выберите расходник из таблицы"
                          size={isMobile ? 'medium' : 'small'}
                          helperText="В списке виден источник: филиал и местоположение"
                        />
                      )}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="body2" color="text.secondary">
                      {selectedWorkConsumable
                        ? `Источник: ${selectedWorkConsumable.branch_name || '-'} / ${selectedWorkConsumable.location_name || '-'} | Остаток: ${selectedWorkConsumable.qty}`
                        : 'Источник не выбран'}
                    </Typography>
                  </Grid>
                </Grid>

                <Box
                  sx={{
                    mt: 2,
                    p: 2,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    bgcolor: 'action.hover'
                  }}
                >
                  <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
                    ИСТОРИЯ ЗАМЕНЫ КАРТРИДЖА
                    {cartridgeModel ? `: ${cartridgeModel}` : ''}
                  </Typography>
                  {cartridgeHistory ? (
                    cartridgeHistory.multiple ? (
                      <Typography variant="body2" color="text.secondary">
                        Для групповой операции история не отображается.
                      </Typography>
                    ) : cartridgeHistory.last_date ? (
                      <>
                        <Typography variant="body2" color="text.secondary">
                          Последняя: {formatDate(cartridgeHistory.last_date)}
                        </Typography>
                        {cartridgeHistory.time_ago_str && (
                          <Typography variant="body2" color="text.secondary">
                            Прошло: {cartridgeHistory.time_ago_str}
                          </Typography>
                        )}
                        <Typography variant="body2" color="text.secondary">
                          Всего замен: {cartridgeHistory.count}
                        </Typography>
                      </>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        История замен картриджа пуста
                      </Typography>
                    )
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Загрузка истории...
                    </Typography>
                  )}
                </Box>
              </>
            )}

            {actionModal.type === 'battery' && (
              <Box
                sx={{
                  mt: 1,
                  p: 2,
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'action.hover'
                }}
              >
                <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
                  ИСТОРИЯ ЗАМЕНЫ БАТАРЕИ
                </Typography>
                {batteryHistory ? (
                  batteryHistory.multiple ? (
                    <Typography variant="body2" color="text.secondary">
                      Для групповой операции история не отображается.
                    </Typography>
                  ) : batteryHistory.last_date ? (
                    <>
                      <Typography variant="body2" color="text.secondary">
                        Последняя: {formatDate(batteryHistory.last_date)}
                      </Typography>
                      {batteryHistory.time_ago_str && (
                        <Typography variant="body2" color="text.secondary">
                          Прошло: {batteryHistory.time_ago_str}
                        </Typography>
                      )}
                      <Typography variant="body2" color="text.secondary">
                        Всего замен: {batteryHistory.count}
                      </Typography>
                    </>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      История замен батареи пуста
                    </Typography>
                  )
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Загрузка истории...
                  </Typography>
                )}
              </Box>
            )}

            {actionModal.type === 'component' && (
              <>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <FormControl fullWidth size={isMobile ? 'medium' : 'small'}>
                      <InputLabel>
                        {actionModal.componentKind === 'pc' ? 'Компонент ПК' : 'Тип компонента'}
                      </InputLabel>
                      <Select
                        value={componentType}
                        onChange={(e) => setComponentType(normalizePrinterComponentType(e.target.value))}
                        label={actionModal.componentKind === 'pc' ? 'Компонент ПК' : 'Тип компонента'}
                        disabled={actionLoading}
                      >
                        {activeComponentOptions.map((option) => (
                          <MenuItem key={option.value} value={option.value}>
                            {option.label}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12}>
                    <Autocomplete
                      options={actionWorkConsumableOptions}
                      loading={workConsumablesLoading}
                      value={selectedWorkConsumable}
                      onChange={(_, value) => setSelectedWorkConsumable(value || null)}
                      isOptionEqualToValue={(option, value) =>
                        toNumberOrNull(option?.id) === toNumberOrNull(value?.id)
                      }
                      getOptionLabel={(option) => formatConsumableSourceLabel(option)}
                      renderOption={(props, option) => {
                        const { key, ...restProps } = props;
                        const normalized = toConsumableSourceOption(option);
                        return (
                          <li key={key} {...restProps}>
                            <Box sx={{ display: 'grid' }}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {normalized.model_name || '-'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {normalized.type_name || '-'} | {normalized.branch_name || '-'} / {normalized.location_name || '-'} | Остаток: {normalized.qty}
                              </Typography>
                            </Box>
                          </li>
                        );
                      }}
                      noOptionsText="Картриджи не найдены"
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label={
                            actionModal.componentKind === 'printer'
                              ? 'Запчасть / расходник'
                              : 'Компонент / расходник'
                          }
                          placeholder="Выберите расходник из таблицы"
                          size={isMobile ? 'medium' : 'small'}
                          helperText="В списке виден источник: филиал и местоположение"
                        />
                      )}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="body2" color="text.secondary">
                      {selectedWorkConsumable
                        ? `Источник: ${selectedWorkConsumable.branch_name || '-'} / ${selectedWorkConsumable.location_name || '-'} | Остаток: ${selectedWorkConsumable.qty}`
                        : 'Источник не выбран'}
                    </Typography>
                  </Grid>
                </Grid>

                <Box
                  sx={{
                    mt: 2,
                    p: 2,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    bgcolor: 'action.hover'
                  }}
                >
                  <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
                    ИСТОРИЯ ЗАМЕНЫ: {getComponentLabel(actionModal.componentKind, componentType)}
                  </Typography>
                  {componentHistory ? (
                    componentHistory.multiple ? (
                      <Typography variant="body2" color="text.secondary">
                        Для групповой операции история не отображается.
                      </Typography>
                    ) : componentHistory.last_date ? (
                      <>
                        <Typography variant="body2" color="text.secondary">
                          Последняя: {formatDate(componentHistory.last_date)}
                        </Typography>
                        {componentHistory.time_ago_str && (
                          <Typography variant="body2" color="text.secondary">
                            Прошло: {componentHistory.time_ago_str}
                          </Typography>
                        )}
                        <Typography variant="body2" color="text.secondary">
                          Всего замен: {componentHistory.count}
                        </Typography>
                      </>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        История замен по этому компоненту пуста
                      </Typography>
                    )
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Загрузка истории...
                    </Typography>
                  )}
                </Box>
              </>
            )}

            {actionModal.type === 'cleaning' && (
              <Box
                sx={{
                  mt: 2,
                  p: 2,
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'action.hover'
                }}
              >
                <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
                  ИСТОРИЯ ЧИСТОК
                </Typography>
                {cleaningHistory ? (
                  cleaningHistory.multiple ? (
                    <Typography variant="body2" color="text.secondary">
                      Для групповой операции история не отображается.
                    </Typography>
                  ) : cleaningHistory.last_date ? (
                    <>
                      <Typography variant="body2" color="text.secondary">
                        Последняя: {formatDate(cleaningHistory.last_date)}
                      </Typography>
                      {cleaningHistory.time_ago_str && (
                        <Typography variant="body2" color="text.secondary">
                          Прошло: {cleaningHistory.time_ago_str}
                        </Typography>
                      )}
                      <Typography variant="body2" color="text.secondary">
                        Всего чисток: {cleaningHistory.count}
                      </Typography>
                    </>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      История чисток пуста
                    </Typography>
                  )
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Загрузка истории...
                  </Typography>
                )}
              </Box>
            )}

            {actionError && (
              <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                {actionError}
              </Typography>
            )}
          </DialogContent>
          <DialogActions sx={{ p: 2, justifyContent: 'flex-end', gap: 1 }}>
            <Button
              variant="outlined"
              onClick={() => {
                setActionModal({ open: false, type: null, invNo: null, componentKind: null });
                setActionError('');
                resetTransferState();
                setCartridgeModel('');
                setSelectedWorkConsumable(null);
                setWorkConsumableOptions([]);
                setWorkConsumablesLoading(false);
                setCartridgeHistory(null);
                setComponentType(PRINTER_COMPONENT_OPTIONS[0].value);
                setBatteryHistory(null);
                setComponentHistory(null);
                setCleaningHistory(null);
              }}
            >
              Закрыть
            </Button>
            {canDatabaseWrite && !(actionModal.type === 'transfer' && transferResult) && (
              <Button
                onClick={async () => {
                  if (!canDatabaseWrite) {
                    setActionError('Недостаточно прав для изменения данных.');
                    return;
                  }
                  try {
                    setActionLoading(true);
                    setActionError('');
                    const effectiveDbName = normalizeDbId(db_name || localStorage.getItem('selected_database'));

                    const ensureDetailedItem = async (invNo, detailsMap) => {
                      let item = detailsMap?.get(invNo) || findEquipmentByInvNo(invNo);
                      if (!item) {
                        throw new Error(`Оборудование ${invNo} не найдено в текущем списке`);
                      }

                      const hasId = item?.ID !== undefined && item?.ID !== null;
                      if (!hasId) {
                        try {
                          const eqResponse = await equipmentAPI.getByInvNos([invNo]);
                          const fetched = Array.isArray(eqResponse?.equipment) ? eqResponse.equipment[0] : null;
                          if (fetched) {
                            item = { ...item, ...fetched };
                          }
                        } catch (eqErr) {
                          console.error('Error fetching full equipment data:', eqErr);
                        }
                      }

                      return item;
                    };

                    if (actionModal.type === 'transfer') {
                      const targetInvNos = normalizeActionTargets(selectedItems, actionModal.invNo);
                      if (targetInvNos.length === 0) {
                        setActionError('Не выбрано оборудование для перемещения');
                        return;
                      }

                      const employeeName = String(newEmployee || '').trim();
                      if (!newEmployeeNo && employeeName.length < 2) {
                        setActionError('Выберите сотрудника из списка или нажмите "Добавить сотрудника".');
                        return;
                      }
                      if (!newEmployeeNo && !validateEmployeeName(employeeName)) {
                        setActionError('Некорректное ФИО нового сотрудника.');
                        return;
                      }
                      if (!newEmployeeNo && !String(transferDepartment || '').trim()) {
                        setActionError('Выберите отдел для нового сотрудника из списка.');
                        return;
                      }
                      if (!transferBranchNo) {
                        setActionError('Выберите филиал назначения из списка.');
                        return;
                      }
                      if (!transferLocationNo) {
                        setActionError('Выберите местоположение назначения из списка.');
                        return;
                      }

                      const response = await equipmentAPI.transfer({
                        inv_nos: targetInvNos,
                        new_employee: employeeName,
                        new_employee_no: newEmployeeNo || undefined,
                        new_employee_dept: !newEmployeeNo ? String(transferDepartment || '').trim() || undefined : undefined,
                        branch_no: transferBranchNo,
                        loc_no: transferLocationNo,
                      });
                      setTransferResult(response);
                      setTransferEmailStatus('');
                      setTransferEmailError('');
                      setSelectedItems([]);
                      await fetchAllEquipment({ force: true });

                      if (Number(response?.failed_count || 0) > 0) {
                        setActionError(`Перенесено ${response.success_count}, ошибок ${response.failed_count}`);
                      } else {
                        setActionError('');
                      }
                      return;
                    }

                    if (actionModal.type === 'cartridge') {
                      const targetInvNos = normalizeActionTargets(selectedItems, actionModal.invNo);
                      if (targetInvNos.length === 0) {
                        setActionError('Не выбрано оборудование для операции');
                        return;
                      }
                      const invalidInvNos = getInvalidTargets(
                        targetInvNos,
                        (item) => getItemCapabilityFlags(item).isPrinterOrMfu
                      );
                      if (invalidInvNos.length > 0) {
                        setActionError(`Замена картриджа доступна только для МФУ/принтеров/плоттеров. Неверные INV: ${invalidInvNos.slice(0, 5).join(', ')}`);
                        return;
                      }
                      if (!selectedWorkConsumable?.id) {
                        setActionError('Выберите картридж из таблицы расходников.');
                        return;
                      }
                      const effectiveCartridgeColor = DEFAULT_CARTRIDGE_COLOR;

                      const detailedItemsByInv = await loadDetailedItemsByInvNos(targetInvNos);

                      const settled = await runInBatches(targetInvNos, async (invNo) => {
                        const item = await ensureDetailedItem(invNo, detailedItemsByInv);
                        const serialNumber = String(item?.SERIAL_NO || item?.serial_no || '').trim();
                        const employee = String(item?.OWNER_DISPLAY_NAME || item?.employee_name || 'Не указан').trim();
                        const location = String(item?.LOCATION || item?.location || '').trim();
                        const branchName = getItemBranch(item);
                        if (!serialNumber) {
                          throw new Error(`Для оборудования ${invNo} не указан серийный номер`);
                        }
                        if (!branchName) {
                          throw new Error(`Для оборудования ${invNo} не указан филиал`);
                        }
                        if (!location) {
                          throw new Error(`Для оборудования ${invNo} не указана локация`);
                        }

                        await equipmentAPI.consumeConsumable({
                          item_id: selectedWorkConsumable.id,
                          qty: 1,
                          reason: 'cartridge',
                        });

                        return jsonAPI.addCartridgeReplacement({
                          printer_model: item?.MODEL_NAME || item?.model_name || 'Unknown',
                          cartridge_color: effectiveCartridgeColor,
                          component_type: 'cartridge',
                          component_color: effectiveCartridgeColor,
                          cartridge_model: selectedWorkConsumable.model_name || cartridgeModel || undefined,
                          detection_source: 'sql-consumables',
                          printer_is_color: undefined,
                          branch: branchName,
                          location,
                          serial_number: serialNumber,
                          employee,
                          inv_no: invNo,
                          db_name: effectiveDbName,
                          equipment_id: item?.ID,
                          current_description: String(item?.DESCRIPTION || item?.description || item?.descr || ''),
                          hw_serial_no: String(item?.HW_SERIAL_NO || item?.hw_serial_no || ''),
                          model_name: String(item?.MODEL_NAME || item?.model_name || ''),
                          manufacturer: String(item?.MANUFACTURER || item?.manufacturer || ''),
                          additional_data: {
                            consumable_item_id: selectedWorkConsumable.id,
                            consumable_inv_no: selectedWorkConsumable.inv_no || '',
                            consumable_model: selectedWorkConsumable.model_name || '',
                            consumable_branch: selectedWorkConsumable.branch_name || '',
                            consumable_location: selectedWorkConsumable.location_name || '',
                          },
                        });
                      });

                      const failed = settled.filter((r) => r.status === 'rejected');
                      if (failed.length > 0) {
                        throw failed[0].reason;
                      }
                    } else if (actionModal.type === 'battery') {
                      const targetInvNos = normalizeActionTargets(selectedItems, actionModal.invNo);
                      if (targetInvNos.length === 0) {
                        setActionError('Не выбрано оборудование для операции');
                        return;
                      }
                      const invalidInvNos = getInvalidTargets(
                        targetInvNos,
                        (item) => getItemCapabilityFlags(item).isUps
                      );
                      if (invalidInvNos.length > 0) {
                        setActionError(`Замена батареи доступна только для ИБП. Неверные INV: ${invalidInvNos.slice(0, 5).join(', ')}`);
                        return;
                      }

                      const detailedItemsByInv = await loadDetailedItemsByInvNos(targetInvNos);

                      const settled = await runInBatches(targetInvNos, async (invNo) => {
                        const item = await ensureDetailedItem(invNo, detailedItemsByInv);
                        const serialNumber = String(item?.SERIAL_NO || item?.serial_no || '').trim();
                        const employee = String(item?.OWNER_DISPLAY_NAME || item?.employee_name || 'Не указан').trim();
                        const location = String(item?.LOCATION || item?.location || '').trim();
                        const branchName = getItemBranch(item);
                        if (!serialNumber) {
                          throw new Error(`Для оборудования ${invNo} не указан серийный номер`);
                        }
                        if (!branchName) {
                          throw new Error(`Для оборудования ${invNo} не указан филиал`);
                        }
                        if (!location) {
                          throw new Error(`Для оборудования ${invNo} не указана локация`);
                        }

                        return jsonAPI.addBatteryReplacement({
                          serial_number: serialNumber,
                          employee,
                          branch: branchName,
                          location,
                          inv_no: invNo,
                          db_name: effectiveDbName,
                          equipment_id: item?.ID,
                          current_description: String(item?.DESCRIPTION || item?.description || item?.descr || ''),
                          hw_serial_no: String(item?.HW_SERIAL_NO || item?.hw_serial_no || ''),
                          model_name: String(item?.MODEL_NAME || item?.model_name || ''),
                          manufacturer: String(item?.MANUFACTURER || item?.manufacturer || ''),
                        });
                      });

                      const failed = settled.filter((r) => r.status === 'rejected');
                      if (failed.length > 0) {
                        throw failed[0].reason;
                      }
                    } else if (actionModal.type === 'component') {
                      const targetInvNos = normalizeActionTargets(selectedItems, actionModal.invNo);
                      if (targetInvNos.length === 0) {
                        setActionError('Не выбрано оборудование для операции');
                        return;
                      }
                      const targetItems = targetInvNos.map((invNo) => ({ invNo, item: findEquipmentByInvNo(invNo) }));
                      const unresolvedInvNos = targetItems.filter((entry) => !entry.item).map((entry) => entry.invNo);
                      if (unresolvedInvNos.length > 0) {
                        setActionError(`Не удалось определить оборудование: ${unresolvedInvNos.slice(0, 5).join(', ')}`);
                        return;
                      }

                      const allPrinter = targetItems.every(({ item }) => getItemCapabilityFlags(item).isPrinterOrMfu);
                      const allPc = targetItems.every(({ item }) => getItemCapabilityFlags(item).isPc);
                      if (!allPrinter && !allPc) {
                        setActionError('Замена комплектующих выполняется отдельно: либо только МФУ/принтеры/плоттеры, либо только системные блоки.');
                        return;
                      }

                      const componentKind = allPc ? 'pc' : 'printer';
                      const validComponentTypes = (
                        componentKind === 'pc' ? PC_COMPONENT_OPTIONS : PRINTER_COMPONENT_OPTIONS
                      ).map((entry) => entry.value);
                      if (!validComponentTypes.includes(componentType)) {
                        setActionError('Выберите тип компонента из доступного списка.');
                        return;
                      }
                      if (!selectedWorkConsumable?.id) {
                        setActionError('Выберите запчасть из таблицы расходников.');
                        return;
                      }

                      const detailedItemsByInv = await loadDetailedItemsByInvNos(targetInvNos);

                      const settled = await runInBatches(targetInvNos, async (invNo) => {
                        const item = await ensureDetailedItem(invNo, detailedItemsByInv);
                        const serialNumber = String(item?.SERIAL_NO || item?.serial_no || '').trim();
                        const employee = String(item?.OWNER_DISPLAY_NAME || item?.employee_name || 'Не указан').trim();
                        const location = String(item?.LOCATION || item?.location || '').trim();
                        const branchName = getItemBranch(item);
                        if (!serialNumber) {
                          throw new Error(`Для оборудования ${invNo} не указан серийный номер`);
                        }
                        if (!branchName) {
                          throw new Error(`Для оборудования ${invNo} не указан филиал`);
                        }
                        if (!location) {
                          throw new Error(`Для оборудования ${invNo} не указана локация`);
                        }
                        const componentName = getComponentLabel(componentKind, componentType);
                        const resolvedComponentModel = String(selectedWorkConsumable?.model_name || '').trim();
                        if (!resolvedComponentModel) {
                          throw new Error('Не удалось определить модель компонента из выбранного расходника');
                        }

                        await equipmentAPI.consumeConsumable({
                          item_id: selectedWorkConsumable.id,
                          qty: 1,
                          reason: 'component',
                        });

                        return jsonAPI.addComponentReplacement({
                          serial_number: serialNumber,
                          employee,
                          component_type: componentType,
                          component_name: componentName,
                          component_model: resolvedComponentModel,
                          equipment_kind: componentKind,
                          branch: branchName,
                          location,
                          inv_no: invNo,
                          db_name: effectiveDbName,
                          equipment_id: item?.ID,
                          current_description: String(item?.DESCRIPTION || item?.description || item?.descr || ''),
                          hw_serial_no: String(item?.HW_SERIAL_NO || item?.hw_serial_no || ''),
                          model_name: String(item?.MODEL_NAME || item?.model_name || ''),
                          manufacturer: String(item?.MANUFACTURER || item?.manufacturer || ''),
                          detection_source: 'sql-consumables',
                          additional_data: {
                            consumable_item_id: selectedWorkConsumable.id,
                            consumable_inv_no: selectedWorkConsumable.inv_no || '',
                            consumable_model: selectedWorkConsumable.model_name || '',
                            consumable_branch: selectedWorkConsumable.branch_name || '',
                            consumable_location: selectedWorkConsumable.location_name || '',
                          },
                        });
                      });

                      const failed = settled.filter((r) => r.status === 'rejected');
                      if (failed.length > 0) {
                        throw failed[0].reason;
                      }
                    } else if (actionModal.type === 'cleaning') {
                      const targetInvNos = normalizeActionTargets(selectedItems, actionModal.invNo);
                      if (targetInvNos.length === 0) {
                        setActionError('Не выбрано оборудование для операции');
                        return;
                      }
                      const invalidInvNos = getInvalidTargets(
                        targetInvNos,
                        (item) => getItemCapabilityFlags(item).isPc
                      );
                      if (invalidInvNos.length > 0) {
                        setActionError(`Чистка доступна только для ПК. Неверные INV: ${invalidInvNos.slice(0, 5).join(', ')}`);
                        return;
                      }

                      const detailedItemsByInv = await loadDetailedItemsByInvNos(targetInvNos);

                      const settled = await runInBatches(targetInvNos, async (invNo) => {
                        const item = await ensureDetailedItem(invNo, detailedItemsByInv);

                        const serialNumber = String(item?.SERIAL_NO || item?.serial_no || '').trim();
                        const employee = String(item?.OWNER_DISPLAY_NAME || item?.employee_name || 'Не указан').trim();
                        const location = String(item?.LOCATION || item?.location || '').trim();
                        const branchName = getItemBranch(item);

                        if (!serialNumber) {
                          throw new Error(`Для оборудования ${invNo} не указан серийный номер`);
                        }
                        if (!branchName) {
                          throw new Error(`Для оборудования ${invNo} не указан филиал`);
                        }
                        if (!location) {
                          throw new Error(`Для оборудования ${invNo} не указана локация`);
                        }

                        const cleaningData = {
                          serial_number: serialNumber,
                          employee,
                          branch: branchName,
                          location,
                          inv_no: String(invNo || ''),
                          db_name: effectiveDbName,
                          equipment_id: item?.ID,
                          current_description: String(item?.DESCRIPTION || item?.description || item?.descr || ''),
                          hw_serial_no: String(item?.HW_SERIAL_NO || item?.hw_serial_no || ''),
                          model_name: String(item?.MODEL_NAME || item?.model_name || ''),
                          manufacturer: String(item?.MANUFACTURER || item?.manufacturer || ''),
                        };

                        return jsonAPI.addPcCleaning(cleaningData);
                      });

                      const failed = settled.filter((r) => r.status === 'rejected');
                      if (failed.length > 0) {
                        throw failed[0].reason;
                      }
                    }

                    if (actionModal.type === 'cartridge' || actionModal.type === 'component') {
                      await fetchAllEquipment({ force: true });
                    }

                    // Close modal and reset state
                    if (actionModal.type !== 'transfer') {
                      setActionModal({ open: false, type: null, invNo: null, componentKind: null });
                      setSelectedItems([]);
                      setActionError('');
                      resetTransferState();
                      setCartridgeModel('');
                      setSelectedWorkConsumable(null);
                      setWorkConsumableOptions([]);
                      setWorkConsumablesLoading(false);
                      setCartridgeHistory(null);
                      setComponentType(PRINTER_COMPONENT_OPTIONS[0].value);
                      setBatteryHistory(null);
                      setComponentHistory(null);
                      setCleaningHistory(null);
                    }
                  } catch (error) {
                    console.error('Action error:', error);
                    console.error('Error response:', error.response?.data);

                    // Handle Pydantic validation errors
                    let errorMessage = error.message || 'Ошибка выполнения операции';
                    if (error.response?.data) {
                      const errorData = error.response.data;
                      if (errorData.detail) {
                        if (typeof errorData.detail === 'string') {
                          errorMessage = errorData.detail;
                        } else if (Array.isArray(errorData.detail)) {
                          // Pydantic validation error format
                          errorMessage = errorData.detail.map(e =>
                            `${e.loc?.join('.')}: ${e.msg}`
                          ).join('; ');
                        } else if (typeof errorData.detail === 'object') {
                          errorMessage = 'Ошибка валидации данных';
                        }
                      }
                    }

                    setActionError(errorMessage);
                  } finally {
                    setActionLoading(false);
                  }
                }}
                variant="contained"
                disabled={actionLoading}
              >
                {actionLoading
                  ? 'Выполнение...'
                  : actionModal.type === 'transfer'
                    ? 'Выполнить перемещение'
                    : 'Подтвердить'}
              </Button>
            )}
          </DialogActions>
        </Dialog>
      </Box>
    </MainLayout>
  );
}

export default Database;

