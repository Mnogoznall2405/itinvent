import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
  Collapse,
  Drawer,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Snackbar,
  Tab,
  Tabs,
  TextField,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DownloadIcon from '@mui/icons-material/Download';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CloseIcon from '@mui/icons-material/Close';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import PlaceIcon from '@mui/icons-material/Place';
import SearchIcon from '@mui/icons-material/Search';
import MainLayout from '../components/layout/MainLayout';
import InteractiveMapCanvas from '../components/networks/InteractiveMapCanvas';
import BranchList from '../components/networks/BranchList';
import EquipmentTab from '../components/networks/EquipmentTab';
import SocketsTab from '../components/networks/SocketsTab';
import AuditTab from '../components/networks/AuditTab';
import DeviceDialog from '../components/networks/DeviceDialog';
import MapDialog from '../components/networks/MapDialog';

import { CreateBranchDialog, EditBranchDialog, DeleteBranchDialog } from '../components/networks/BranchDialogs';

import { networksAPI, apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { buildCacheKey, getOrFetchSWR, invalidateSWRCacheByPrefix } from '../lib/swrCache';

const SWR_STALE_MS = 60_000;

const socketKey = (value) => String(value || '').toLowerCase().replace(/\s+/g, '');

const normalizeMacToken = (value) => {
  const hex = String(value || '').replace(/[^0-9a-fA-F]/g, '').toUpperCase();
  if (hex.length !== 12) return '';
  return hex.match(/.{2}/g).join(':');
};

const extractNormalizedMacs = (rawValue) => {
  const text = String(rawValue || '');
  const matches = text.match(/(?:[0-9A-Fa-f]{2}(?:[:-])){5}[0-9A-Fa-f]{2}|[0-9A-Fa-f]{12}/g) || [];
  const out = [];
  for (const raw of matches) {
    const normalized = normalizeMacToken(raw);
    if (normalized && !out.includes(normalized)) {
      out.push(normalized);
    }
  }
  return out;
};

const normalizeMacField = (rawValue) => {
  const macs = extractNormalizedMacs(rawValue);
  if (macs.length > 0) return macs.join('\n');
  return String(rawValue || '').trim();
};

const pointSortComparator = (a, b) => {
  const aSocket = String(a?.patch_panel_port || '');
  const bSocket = String(b?.patch_panel_port || '');
  const socketCmp = aSocket.localeCompare(bSocket, 'ru', { numeric: true, sensitivity: 'base' });
  if (socketCmp !== 0) return socketCmp;
  const aPort = String(a?.port_name || '');
  const bPort = String(b?.port_name || '');
  const portCmp = aPort.localeCompare(bPort, 'ru', { numeric: true, sensitivity: 'base' });
  if (portCmp !== 0) return portCmp;
  return Number(a?.id || 0) - Number(b?.id || 0);
};

const formatSocketPort = (pointLike) => {
  const socket = String(pointLike?.patch_panel_port || '').trim();
  const port = String(pointLike?.port_name || '').trim();
  if (port && socket) return `PORT ${port} · Розетка ${socket}`;
  if (socket) return `Розетка ${socket}`;
  if (port) return `PORT ${port}`;
  return 'Точка';
};

function Networks() {
  const navigate = useNavigate();
  const { branchId } = useParams();
  const branchIdNum = Number(branchId || 0) || null;
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { hasPermission } = useAuth();
  const canEdit = hasPermission('networks.write');

  // Validate branchId from URL - redirect if invalid
  useEffect(() => {
    if (branchId && (!branchIdNum || isNaN(Number(branchId)) || Number(branchId) <= 0)) {
      console.warn('Invalid branchId in URL:', branchId);
      navigate('/networks', { replace: true });
    }
  }, [branchId, branchIdNum, navigate]);

  const [branches, setBranches] = useState([]);
  const [activeDbId, setActiveDbId] = useState(() => String(localStorage.getItem('selected_database') || '').trim());

  useEffect(() => {
    const handleDbChange = (e) => {
      setActiveDbId(String(e?.detail?.databaseId || localStorage.getItem('selected_database') || '').trim());
    };
    const handleStorageChange = (e) => {
      if (e.key === 'selected_database') {
        setActiveDbId(String(e.newValue || '').trim());
      }
    };
    window.addEventListener('database-changed', handleDbChange);
    window.addEventListener('storage', handleStorageChange);
    return () => {
      window.removeEventListener('database-changed', handleDbChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  const [overview, setOverview] = useState(null);
  const [devices, setDevices] = useState([]);
  const [ports, setPorts] = useState([]);
  const [allBranchPorts, setAllBranchPorts] = useState([]);
  const [maps, setMaps] = useState([]);
  const [audit, setAudit] = useState([]);
  const [mapPoints, setMapPoints] = useState([]);
  const [sockets, setSockets] = useState([]);
  const [socketSearch, setSocketSearch] = useState('');
  const [socketCreateOpen, setSocketCreateOpen] = useState(false);
  const [socketCreateSaving, setSocketCreateSaving] = useState(false);
  const [socketCreateCode, setSocketCreateCode] = useState('');
  const [socketCreateMac, setSocketCreateMac] = useState('');
  const [socketDeleteOpen, setSocketDeleteOpen] = useState(false);
  const [socketDeleteSaving, setSocketDeleteSaving] = useState(false);
  const [socketDeleteTarget, setSocketDeleteTarget] = useState(null);

  const [tab, setTab] = useState('equipment');
  const [branchSearch, setBranchSearch] = useState('');
  const [portSearch, setPortSearch] = useState('');
  const [branchPortResults, setBranchPortResults] = useState([]);
  const [branchPortLoading, setBranchPortLoading] = useState(false);

  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const initialDeviceSelected = useRef(false); // tracks if first auto-select was done
  const [selectedMapId, setSelectedMapId] = useState(null);
  const [selectedPointId, setSelectedPointId] = useState(null);

  const [mapBlobUrl, setMapBlobUrl] = useState('');
  const [mapIsPdf, setMapIsPdf] = useState(false);
  const [mapRenderedFrom, setMapRenderedFrom] = useState('');
  const [addPointPanelOpen, setAddPointPanelOpen] = useState(false);
  const [placingMarker, setPlacingMarker] = useState(false);
  const [pendingPoint, setPendingPoint] = useState(null);
  const [pendingPortId, setPendingPortId] = useState('');
  const [pendingSocketId, setPendingSocketId] = useState('');
  const [pendingSocketInput, setPendingSocketInput] = useState('');
  const [createPointHint, setCreatePointHint] = useState(null);
  const [mapPointSearch, setMapPointSearch] = useState('');
  const [pointDetailsOpen, setPointDetailsOpen] = useState(false);
  const [pointEditMode, setPointEditMode] = useState(false);
  const [selectedPointSocketInput, setSelectedPointSocketInput] = useState('');
  const [mobileMapPanelOpen, setMobileMapPanelOpen] = useState(false);
  const [mobilePortEditorOpen, setMobilePortEditorOpen] = useState(false);

  const [mapDialogOpen, setMapDialogOpen] = useState(false);
  const [focusMapPointId, setFocusMapPointId] = useState(null);
  const [mapEditId, setMapEditId] = useState(null);
  const [mapFile, setMapFile] = useState(null);
  const [mapTitle, setMapTitle] = useState('');
  const [mapFloor, setMapFloor] = useState('');
  const [mapSiteCode, setMapSiteCode] = useState('p19');



  const [createBranchOpen, setCreateBranchOpen] = useState(false);
  const [createBranchCode, setCreateBranchCode] = useState('');
  const [createBranchName, setCreateBranchName] = useState('');
  const [createBranchCity, setCreateBranchCity] = useState('tmn');
  const [createBranchDefaultSiteCode, setCreateBranchDefaultSiteCode] = useState('');
  const [createBranchDbId, setCreateBranchDbId] = useState('');
  const [availableDatabases, setAvailableDatabases] = useState([]);
  const [createPanelMode, setCreatePanelMode] = useState('uniform'); // 'uniform' or 'heterogeneous'
  const [createPanelCount, setCreatePanelCount] = useState('6');
  const [createPortsPerPanel, setCreatePortsPerPanel] = useState('48');
  const [createPanels, setCreatePanels] = useState([{ id: 1, panelIndex: 1, portCount: 48 }]);
  const [createFillMode, setCreateFillMode] = useState('manual');
  const [createTemplateFile, setCreateTemplateFile] = useState(null);
  const [createBranchSaving, setCreateBranchSaving] = useState(false);
  const [fioResolving, setFioResolving] = useState(false);
  const [fioResolveAttemptKey, setFioResolveAttemptKey] = useState('');
  const [branchDbId, setBranchDbId] = useState('');
  const [branchDbInitialId, setBranchDbInitialId] = useState('');
  const [branchDbLoading, setBranchDbLoading] = useState(false);
  const [branchDbReady, setBranchDbReady] = useState(false);
  const [branchDbSaving, setBranchDbSaving] = useState(false);
  const [equipImportLoading, setEquipImportLoading] = useState(false);
  const equipImportRef = useRef(null);

  // Branch edit dialog states
  const [branchEditId, setBranchEditId] = useState(null);
  const [branchEditName, setBranchEditName] = useState('');
  const [branchDefaultSiteCode, setBranchDefaultSiteCode] = useState('');
  const [branchEditDbId, setBranchEditDbId] = useState('');
  const [branchEditDialogOpen, setBranchEditDialogOpen] = useState(false);
  const [branchEditLoading, setBranchEditLoading] = useState(false);
  const [branchEditSaving, setBranchEditSaving] = useState(false);

  // Branch delete dialog states
  const [branchDeleteId, setBranchDeleteId] = useState(null);
  const [branchDeleteName, setBranchDeleteName] = useState('');
  const [branchDeleteDialogOpen, setBranchDeleteDialogOpen] = useState(false);
  const [branchDeleteSaving, setBranchDeleteSaving] = useState(false);

  // Device dialog states
  const [deviceDialogOpen, setDeviceDialogOpen] = useState(false);
  const [deviceEditId, setDeviceEditId] = useState(null);
  const [deviceSaving, setDeviceSaving] = useState(false);
  const [deviceDeleting, setDeviceDeleting] = useState(false);

  // Device form fields
  const [deviceCode, setDeviceCode] = useState('');
  const [deviceType, setDeviceType] = useState('switch');
  const [deviceSiteCode, setDeviceSiteCode] = useState('');
  const [deviceSiteName, setDeviceSiteName] = useState('');
  const [deviceVendor, setDeviceVendor] = useState('');
  const [deviceModel, setDeviceModel] = useState('');
  const [deviceSheetName, setDeviceSheetName] = useState('');
  const [deviceMgmtIp, setDeviceMgmtIp] = useState('');
  const [deviceNotes, setDeviceNotes] = useState('');
  const [devicePortCount, setDevicePortCount] = useState('');

  // Auto-fill sheet_name based on device_code patterns
  useEffect(() => {
    const code = String(deviceCode || '').trim().toUpperCase();
    if (!code) {
      setDeviceSheetName('');
      return;
    }

    // Skip if editing an existing device with an existing sheet_name
    // Only auto-fill when creating a new device (deviceEditId is null)
    if (deviceEditId && deviceSheetName) {
      return;
    }

    // Pattern for determining sheet_name:
    // ASW-P19-1 -> ASW-P19 (for grouping devices)
    // SW-1 -> SW-1
    // Take everything before the last hyphen
    const parts = code.split('-');
    if (parts.length >= 2) {
      // Take prefix for grouping sheets (all but last part)
      setDeviceSheetName(parts.slice(0, -1).join('-'));
    } else if (parts.length === 1) {
      // No hyphens - use entire code as sheet_name
      setDeviceSheetName(code);
    }
  }, [deviceCode, deviceEditId]); // Track deviceCode and whether we're editing

  const [loading, setLoading] = useState(false);
  const [equipmentLoading, setEquipmentLoading] = useState(false);
  const [socketsLoading, setSocketsLoading] = useState(false);
  const [mapsLoading, setMapsLoading] = useState(false);
  const [toastQueue, setToastQueue] = useState([]);
  const [activeToast, setActiveToast] = useState(null);
  const [editingPortId, setEditingPortId] = useState(null);
  const [portDraft, setPortDraft] = useState(null);
  const [portSaving, setPortSaving] = useState(false);
  const [socketAutocompleteOpen, setSocketAutocompleteOpen] = useState(false);
  const [socketAutocompleteOptions, setSocketAutocompleteOptions] = useState([]);
  const [selectedSocketId, setSelectedSocketId] = useState(null);
  const deviceChipRefs = useRef(new Map());
  const branchContextRequestSeq = useRef(0);
  const branchPortsRequestSeq = useRef(0);

  const enqueueToast = useCallback((message, severity = 'info') => {
    const text = String(message || '').trim();
    if (!text) return;
    setToastQueue((prev) => [
      ...prev,
      { id: `${Date.now()}-${Math.random()}`, message: text, severity },
    ]);
  }, []);

  const clearPendingPointDraft = useCallback(() => {
    setPendingPoint(null);
    setPendingPortId('');
    setPendingSocketId('');
    setPendingSocketInput('');
  }, []);

  const addPointDisabledReason = useMemo(() => {
    if (!canEdit) return 'Нет прав на редактирование сети.';
    if (!selectedMapId) return 'Выберите карту для размещения точки.';
    if (mapIsPdf) return 'Для размещения точки нужна карта-изображение (PNG/JPG).';
    return '';
  }, [canEdit, selectedMapId, mapIsPdf]);

  const togglePlacingMarker = useCallback(() => {
    if (addPointDisabledReason) return;
    setAddPointPanelOpen(true);
    if (placingMarker) {
      clearPendingPointDraft();
      setPlacingMarker(false);
      return;
    }
    clearPendingPointDraft();
    setPlacingMarker(true);
  }, [addPointDisabledReason, clearPendingPointDraft, placingMarker]);

  // Helper function to extract error details from API errors
  const getErrorDetail = useCallback((error) => {
    if (!error) return 'Неизвестная ошибка';
    return String(
      error?.response?.data?.detail ||
      error?.message ||
      error?.toString() ||
      'Неизвестная ошибка'
    );
  }, []);

  const notifyError = useCallback((message) => {
    enqueueToast(message, 'error');
  }, [enqueueToast]);

  const notifySuccess = useCallback((message) => {
    enqueueToast(message, 'success');
  }, [enqueueToast]);

  useEffect(() => {
    if (activeToast || toastQueue.length === 0) return;
    const [next, ...rest] = toastQueue;
    setActiveToast(next);
    setToastQueue(rest);
  }, [activeToast, toastQueue]);

  const closeToast = useCallback((_, reason) => {
    if (reason === 'clickaway') return;
    setActiveToast(null);
  }, []);

  const selectedBranch = useMemo(
    () => branches.find((item) => Number(item.id) === Number(branchIdNum)) || null,
    [branches, branchIdNum]
  );

  // Determine site code based on branch name
  const determineSiteCode = useCallback((branchName) => {
    const name = String(branchName || '').toLowerCase();

    // Special cases for existing sites
    if (name.includes('21') || name.includes('2324') || name.includes('c9300')) {
      return 'p21';
    }

    // Full Cyrillic to Latin mapping for transliteration
    const cyrillicToLatin = {
      'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
      'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
      'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
      'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
      'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    };

    // Extract street name and number for auto-generation
    // Pattern: "Street Name Number" → "first_letter + number"
    // Examples:
    //   "Герцена 55" → "g55"
    //   "Ленина 50" → "l50"
    //   "Первомайская 19" → "p19"
    //   "Вокзальная 30" → "v30"

    // Find all numbers in the name
    const numbers = name.match(/\d+/g);
    const streetNumber = numbers ? numbers[numbers.length - 1] : null;

    // Try to extract street name (word before the number)
    let streetLetter = 'p'; // default
    if (streetNumber) {
      const numberIndex = name.lastIndexOf(streetNumber);
      let textBeforeNumber = name.substring(0, numberIndex).trim();
      let lastWordBeforeNumber = textBeforeNumber.split(/\s+/).pop()?.toLowerCase() || '';

      // Transliterate first letter of the word
      if (lastWordBeforeNumber.length > 0) {
        const firstLetter = lastWordBeforeNumber[0];
        streetLetter = cyrillicToLatin[firstLetter] || firstLetter;
        // Take only first letter for multi-letter transliterations (zh, kh, ts, ch, sh, etc.)
        if (streetLetter.length > 1) {
          streetLetter = streetLetter[0];
        }
      }
    }

    return streetLetter + (streetNumber || '19');
  }, []);

  // Auto-generate default_site_code when branch name changes during creation
  useEffect(() => {
    if (createBranchOpen) {
      const generated = createBranchName ? determineSiteCode(createBranchName) : 'p19';
      setCreateBranchDefaultSiteCode(generated);
    }
  }, [createBranchOpen, createBranchName, determineSiteCode]);

  const selectedDevice = useMemo(
    () => devices.find((item) => Number(item.id) === Number(selectedDeviceId)) || null,
    [devices, selectedDeviceId]
  );

  const selectedMap = useMemo(
    () => maps.find((item) => Number(item.id) === Number(selectedMapId)) || null,
    [maps, selectedMapId]
  );

  const selectedMapIsPdfSource = useMemo(() => {
    const fileName = String(selectedMap?.file_name || '').toLowerCase();
    const mimeType = String(selectedMap?.mime_type || '').toLowerCase();
    return fileName.endsWith('.pdf') || mimeType.includes('application/pdf');
  }, [selectedMap]);

  const hasBranchDbChanges = useMemo(
    () => String(branchDbId || '').trim() !== String(branchDbInitialId || '').trim(),
    [branchDbId, branchDbInitialId]
  );

  const selectedPoint = useMemo(
    () => mapPoints.find((item) => Number(item.id) === Number(selectedPointId)) || null,
    [mapPoints, selectedPointId]
  );

  const selectedCluster = useMemo(() => {
    if (!selectedPoint || !selectedMapId || !mapPoints.length) return null;
    const sameCoords = mapPoints.filter((p) =>
      Number(p.map_id) === Number(selectedMapId) &&
      Math.abs(Number(p.x_ratio || 0) - Number(selectedPoint.x_ratio || 0)) < 0.015 &&
      Math.abs(Number(p.y_ratio || 0) - Number(selectedPoint.y_ratio || 0)) < 0.015
    ).sort((a, b) => {
      const aName = String(a.patch_panel_port || a.device_code || a.id);
      const bName = String(b.patch_panel_port || b.device_code || b.id);
      return aName.localeCompare(bName, 'ru', { numeric: true });
    });
    return sameCoords.length > 1 ? sameCoords : null;
  }, [selectedMapId, selectedPoint, mapPoints]);


  const filteredBranches = useMemo(() => {
    let result = branches;
    if (activeDbId) {
      result = result.filter((branch) => {
        const branchDb = String(branch.db_id || '').trim();
        return !branchDb || branchDb === activeDbId;
      });
    }

    const query = String(branchSearch || '').trim().toLowerCase();
    if (!query) return result;
    return result.filter((branch) =>
      [branch.name, branch.branch_code, branch.city_code]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [branches, branchSearch, activeDbId]);

  const makePortDraft = useCallback((port) => ({
    port_name: String(port?.port_name || ''),
    patch_panel_port: String(port?.patch_panel_port || ''),
    location_code: String(port?.location_code || ''),
    vlan_raw: String(port?.vlan_raw || ''),
    endpoint_name_raw: String(port?.endpoint_name_raw || ''),
    endpoint_ip_raw: String(port?.endpoint_ip_raw || ''),
    endpoint_mac_raw: String(port?.endpoint_mac_raw || ''),
  }), []);

  const isBranchWidePortSearch = useMemo(
    () => String(portSearch || '').trim().length > 0,
    [portSearch]
  );

  const displayedPorts = useMemo(
    () => {
      // When searching across the whole branch, use branchPortResults
      // When a specific device is selected, use its ports
      // When "All devices" is selected (selectedDeviceId === null), use allBranchPorts
      const portList = isBranchWidePortSearch
        ? branchPortResults
        : selectedDeviceId
          ? ports
          : allBranchPorts;
      // Sort ports numerically by port_name (1, 2, 10 instead of 1, 10, 2)
      return [...portList].sort((a, b) => {
        const nameA = String(a?.port_name || '');
        const nameB = String(b?.port_name || '');
        // Extract numeric part for comparison
        const numA = parseInt(nameA.replace(/\D/g, '')) || 0;
        const numB = parseInt(nameB.replace(/\D/g, '')) || 0;
        if (numA !== numB) {
          return numA - numB;
        }
        // If numbers are equal, sort lexicographically
        return nameA.localeCompare(nameB, undefined, { numeric: true });
      });
    },
    [isBranchWidePortSearch, branchPortResults, ports, selectedDeviceId, allBranchPorts]
  );
  const editingPort = useMemo(
    () => displayedPorts.find((item) => Number(item.id) === Number(editingPortId)) || null,
    [displayedPorts, editingPortId]
  );
  const matchedDeviceIds = useMemo(() => {
    if (!isBranchWidePortSearch) return new Set();
    const ids = new Set();
    for (const port of displayedPorts) {
      const deviceId = Number(port?.device_id || 0);
      if (deviceId) ids.add(deviceId);
    }
    return ids;
  }, [displayedPorts, isBranchWidePortSearch]);

  const matchedDevicePortCount = useMemo(() => {
    const counter = new Map();
    if (!isBranchWidePortSearch) return counter;
    for (const port of displayedPorts) {
      const deviceId = Number(port?.device_id || 0);
      if (!deviceId) continue;
      counter.set(deviceId, (counter.get(deviceId) || 0) + 1);
    }
    return counter;
  }, [displayedPorts, isBranchWidePortSearch]);

  const pointsForMap = useMemo(() => {
    if (!selectedMapId) return [];
    return mapPoints
      .filter((item) => Number(item.map_id) === Number(selectedMapId))
      .sort(pointSortComparator);
  }, [mapPoints, selectedMapId]);

  const availableSites = useMemo(() => {
    const siteMap = new Map();
    // 1. Дефолтный сайт филиала (ищем в загруженных branches)
    if (branchIdNum && branches && branches.length > 0) {
      const currentBranch = branches.find(b => Number(b.id) === Number(branchIdNum));
      if (currentBranch && currentBranch.default_site_code) {
        siteMap.set(currentBranch.default_site_code, currentBranch.name || currentBranch.default_site_code);
      }
    }
    // 2. Сайты устройств
    (devices || []).forEach((d) => {
      const code = String(d?.site_code || '').trim();
      if (code && !siteMap.has(code)) {
        siteMap.set(code, code);
      }
    });

    if (siteMap.size === 0) {
      siteMap.set('p19', 'Первомайская 19'); // fallback
    }
    return Array.from(siteMap.entries()).map(([code, name]) => ({ site_code: code, name }));
  }, [branches, branchIdNum, devices]);

  const filteredPointsForMap = useMemo(() => {
    const query = String(mapPointSearch || '').trim().toLowerCase();
    if (!query) return pointsForMap;
    return pointsForMap.filter((point) =>
      [
        point.label,
        point.note,
        point.device_code,
        point.device_model,
        point.port_name,
        point.patch_panel_port,
        point.endpoint_name_raw,
        point.endpoint_ip_raw,
        point.endpoint_mac_raw,
        point.port_location_code,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [mapPointSearch, pointsForMap]);

  // All ports with patch_panel_port filled (for backward compatibility)
  const allPortsWithSocket = useMemo(
    () => (allBranchPorts || [])
      .filter((port) => String(port.patch_panel_port || '').trim())
      .sort(pointSortComparator),
    [allBranchPorts]
  );

  // Free sockets - sockets without port_id (not assigned to any port)
  const freeSockets = useMemo(
    () => (sockets || [])
      .filter((socketItem) => !socketItem.port_id && String(socketItem.socket_code || '').trim())
      .sort((a, b) => {
        const aSocket = String(a?.socket_code || '');
        const bSocket = String(b?.socket_code || '');
        return aSocket.localeCompare(bSocket, 'ru', { numeric: true, sensitivity: 'base' });
      }),
    [sockets]
  );

  const devicePortCounts = useMemo(() => {
    const counter = new Map();
    for (const port of allBranchPorts || []) {
      const deviceId = Number(port?.device_id || 0);
      if (!deviceId) continue;
      counter.set(deviceId, (counter.get(deviceId) || 0) + 1);
    }
    return counter;
  }, [allBranchPorts]);

  const filteredSockets = useMemo(() => {
    const query = String(socketSearch || '').trim().toLowerCase();
    if (!query) return sockets;
    return sockets.filter((socketItem) =>
      [
        socketItem.socket_code,
        socketItem.device_code,
        socketItem.port_name,
        socketItem.location_code,
        socketItem.vlan_raw,
        socketItem.endpoint_ip_raw,
        socketItem.endpoint_mac_raw,
        socketItem.mac_address,
        socketItem.fio,
        socketItem.fio_source_db,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [socketSearch, sockets]);

  const pendingPortOptions = useMemo(() => {
    const normalized = socketKey(pendingSocketInput);
    if (!normalized) return [];
    return allPortsWithSocket.filter((port) => socketKey(port.patch_panel_port).includes(normalized));
  }, [allPortsWithSocket, pendingSocketInput]);

  const pendingSocketOptions = useMemo(() => {
    const normalized = socketKey(pendingSocketInput);
    const source = Array.isArray(sockets) ? sockets : [];
    if (!normalized) return source.slice(0, 500);
    return source
      .filter((socketItem) => socketKey(socketItem.socket_code).includes(normalized))
      .slice(0, 500);
  }, [pendingSocketInput, sockets]);

  const selectedPendingPort = useMemo(
    () => pendingPortOptions.find((port) => Number(port.id) === Number(pendingPortId)) || null,
    [pendingPortOptions, pendingPortId]
  );

  const selectedPendingSocket = useMemo(
    () => pendingSocketOptions.find((socketItem) => Number(socketItem.id) === Number(pendingSocketId)) || null,
    [pendingSocketOptions, pendingSocketId]
  );

  const pendingPortValue = useMemo(() => {
    const value = String(pendingPortId || '');
    if (!value) return '';
    return pendingPortOptions.some((port) => String(port.id) === value) ? value : '';
  }, [pendingPortId, pendingPortOptions]);

  const pendingSocketValue = useMemo(() => {
    const value = String(pendingSocketId || '');
    if (!value) return '';
    return pendingSocketOptions.some((socketItem) => String(socketItem.id) === value) ? value : '';
  }, [pendingSocketId, pendingSocketOptions]);

  const pendingSocketMatches = useMemo(() => {
    const normalized = socketKey(pendingSocketInput);
    if (!normalized) return [];
    return allPortsWithSocket.filter((port) => socketKey(port.patch_panel_port) === normalized);
  }, [allPortsWithSocket, pendingSocketInput]);

  const selectedPointPortOptions = useMemo(() => {
    if (!selectedPoint) return [];
    const normalized = socketKey(selectedPointSocketInput);
    const currentId = Number(selectedPoint.port_id || 0);
    let options = normalized
      ? allPortsWithSocket.filter((port) => socketKey(port.patch_panel_port).includes(normalized))
      : [];

    if (!normalized && currentId) {
      const currentPort = allPortsWithSocket.find((port) => Number(port.id) === currentId);
      if (currentPort) {
        return [currentPort];
      }
      return [{
        id: currentId,
        port_name: selectedPoint.port_name || '',
        patch_panel_port: selectedPoint.patch_panel_port || '',
        location_code: selectedPoint.port_location_code || '',
        endpoint_ip_raw: selectedPoint.endpoint_ip_raw || '',
        endpoint_mac_raw: selectedPoint.endpoint_mac_raw || '',
      }];
    }

    if (currentId && !options.some((port) => Number(port.id) === currentId)) {
      options = [
        {
          id: currentId,
          port_name: selectedPoint.port_name || '',
          patch_panel_port: selectedPoint.patch_panel_port || '',
          location_code: selectedPoint.port_location_code || '',
          endpoint_ip_raw: selectedPoint.endpoint_ip_raw || '',
          endpoint_mac_raw: selectedPoint.endpoint_mac_raw || '',
        },
        ...options,
      ];
    }
    return options;
  }, [allPortsWithSocket, selectedPoint, selectedPointSocketInput]);

  const selectedPointPortValue = useMemo(() => {
    if (!selectedPoint) return '';
    const value = String(selectedPoint.port_id || '');
    if (!value) return '';
    return selectedPointPortOptions.some((port) => String(port.id) === value) ? value : '';
  }, [selectedPoint, selectedPointPortOptions]);

  const selectedPointSocketMatches = useMemo(() => {
    const normalized = socketKey(selectedPointSocketInput);
    if (!normalized) return [];
    return allPortsWithSocket.filter((port) => socketKey(port.patch_panel_port) === normalized);
  }, [allPortsWithSocket, selectedPointSocketInput]);

  const focusPointId = useMemo(() => {
    if (selectedPointId && pointsForMap.some((item) => Number(item.id) === Number(selectedPointId))) {
      return selectedPointId;
    }
    if (filteredPointsForMap.length > 0 && String(mapPointSearch || '').trim()) {
      return filteredPointsForMap[0].id;
    }
    if (!selectedDeviceId || !selectedMapId) return null;
    return pointsForMap.find((item) => Number(item.device_id) === Number(selectedDeviceId))?.id || null;
  }, [filteredPointsForMap, mapPointSearch, pointsForMap, selectedDeviceId, selectedMapId, selectedPointId]);

  const loadBranches = useCallback(async () => {
    const { data } = await getOrFetchSWR(
      buildCacheKey('networks', 'branches', 'tmn'),
      async () => (await networksAPI.getBranches('tmn')).branches || [],
      { staleTimeMs: SWR_STALE_MS }
    );
    setBranches(Array.isArray(data) ? data : []);
  }, []);

  const loadBranchContext = useCallback(async (id, force = false) => {
    if (!id) return;
    const requestSeq = ++branchContextRequestSeq.current;
    const { data } = await getOrFetchSWR(
      buildCacheKey('networks', 'branch-context', id),
      async () => {
        const results = await Promise.allSettled([
          networksAPI.getBranchOverview(id),
          networksAPI.getDevices(id),
          networksAPI.getMaps(id),
          networksAPI.getMapPoints(id),
          networksAPI.getAudit({ branch_id: id, limit: 100 }),
          networksAPI.getBranchSockets(id, { limit: 10000 }),
        ]);

        const [ovResult, dvResult, mpResult, ptResult, auResult, skResult] = results;

        // Log errors for debugging
        if (ovResult.status === 'rejected') console.error('Failed to load branch overview:', ovResult.reason);
        if (dvResult.status === 'rejected') console.error('Failed to load devices:', dvResult.reason);
        if (mpResult.status === 'rejected') console.error('Failed to load maps:', mpResult.reason);
        if (ptResult.status === 'rejected') console.error('Failed to load map points:', ptResult.reason);
        if (auResult.status === 'rejected') console.error('Failed to load audit:', auResult.reason);
        if (skResult.status === 'rejected') console.error('Failed to load sockets:', skResult.reason);

        return {
          overview: ovResult.status === 'fulfilled' ? (ovResult.value || null) : null,
          devices: Array.isArray(dvResult.value?.devices) ? dvResult.value.devices : [],
          maps: Array.isArray(mpResult.value?.maps) ? mpResult.value.maps : [],
          points: Array.isArray(ptResult.value?.points) ? ptResult.value.points : [],
          audit: Array.isArray(auResult.value?.items) ? auResult.value.items : [],
          sockets: Array.isArray(skResult.value?.sockets) ? skResult.value.sockets : [],
          errors: {
            overview: ovResult.status === 'rejected' ? String(ovResult.reason?.response?.data?.detail || ovResult.reason?.message || 'Unknown error') : null,
            devices: dvResult.status === 'rejected' ? String(dvResult.reason?.response?.data?.detail || dvResult.reason?.message || 'Unknown error') : null,
            maps: mpResult.status === 'rejected' ? String(mpResult.reason?.response?.data?.detail || mpResult.reason?.message || 'Unknown error') : null,
            points: ptResult.status === 'rejected' ? String(ptResult.reason?.response?.data?.detail || ptResult.reason?.message || 'Unknown error') : null,
            audit: auResult.status === 'rejected' ? String(auResult.reason?.response?.data?.detail || auResult.reason?.message || 'Unknown error') : null,
            sockets: skResult.status === 'rejected' ? String(skResult.reason?.response?.data?.detail || skResult.reason?.message || 'Unknown error') : null,
          },
        };
      },
      { staleTimeMs: SWR_STALE_MS, force }
    );
    if (requestSeq !== branchContextRequestSeq.current) {
      return;
    }
    setOverview(data?.overview || null);
    setDevices(data?.devices || []);
    setMaps(data?.maps || []);
    setMapPoints(data?.points || []);
    setAudit(data?.audit || []);
    setSockets(data?.sockets || []);

    // Store errors for user notification
    if (data?.errors) {
      const criticalErrors = Object.entries(data.errors)
        .filter(([_, error]) => error !== null)
        .map(([key, error]) => `${key}: ${error}`);

      if (criticalErrors.length > 0) {
        console.error('Branch context loading errors:', criticalErrors);
        // Notify user about critical errors (overview/devices are critical)
        if (data.errors.overview || data.errors.devices) {
          notifyError(`Критическая ошибка: ${data.errors.overview || data.errors.devices}`);
        }
      }
    }

    // Set selected device/map only if data exists
    // After initial auto-select, preserve user's choice (including null = "Все устройства")
    if (data?.devices && data.devices.length > 0) {
      setSelectedDeviceId((prev) => {
        if (initialDeviceSelected.current && prev === null) return null; // user chose "Все устройства"
        if (!initialDeviceSelected.current || !data.devices.some((d) => Number(d.id) === Number(prev))) {
          initialDeviceSelected.current = true;
          return data.devices[0].id;
        }
        return prev;
      });
    } else {
      setSelectedDeviceId(null);
    }

    if (data?.maps && data.maps.length > 0) {
      setSelectedMapId((prev) =>
        data.maps.some((m) => Number(m.id) === Number(prev)) ? prev : data.maps[0].id
      );
    } else {
      setSelectedMapId(null);
    }
  }, [notifyError]);

  const loadPorts = useCallback(async (deviceId, force = false) => {
    if (!deviceId) {
      setPorts([]);
      return;
    }
    const { data } = await getOrFetchSWR(
      buildCacheKey('networks', 'ports', deviceId),
      async () => (await networksAPI.getPorts(deviceId)).ports || [],
      { staleTimeMs: SWR_STALE_MS, force }
    );
    setPorts(Array.isArray(data) ? data : []);
  }, []);

  const loadAllBranchPorts = useCallback(async (id, force = false) => {
    if (!id) {
      setAllBranchPorts([]);
      return;
    }
    const requestSeq = ++branchPortsRequestSeq.current;
    const { data } = await getOrFetchSWR(
      buildCacheKey('networks', 'branch-ports-all', id),
      async () => (await networksAPI.getBranchPorts(id, { limit: 10000 })).ports || [],
      { staleTimeMs: SWR_STALE_MS, force }
    );
    if (requestSeq !== branchPortsRequestSeq.current) {
      return;
    }
    setAllBranchPorts(Array.isArray(data) ? data : []);
  }, []);

  const refreshBranchContext = useCallback(async () => {
    if (!branchIdNum) return;
    invalidateSWRCacheByPrefix('networks', 'branch-context', branchIdNum);
    invalidateSWRCacheByPrefix('networks', 'branch-ports-all', branchIdNum);
    await Promise.all([
      loadBranchContext(branchIdNum, true),
      loadAllBranchPorts(branchIdNum, true),
    ]);
  }, [branchIdNum, loadAllBranchPorts, loadBranchContext]);

  useEffect(() => {
    void (async () => {
      try {
        setLoading(true);
        await loadBranches();
      } catch (requestError) {
        console.error('Failed to load branches:', requestError);
        notifyError(`Не удалось загрузить филиалы: ${getErrorDetail(requestError)}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [loadBranches, notifyError, getErrorDetail]);

  useEffect(() => {
    const fetchDatabases = async () => {
      try {
        const response = await apiClient.get('/database/list');
        setAvailableDatabases(Array.isArray(response.data) ? response.data : []);
      } catch (err) {
        console.error('Failed to fetch databases:', err);
        setAvailableDatabases([]);
      }
    };
    fetchDatabases();
  }, []);

  useEffect(() => {
    if (!branchIdNum) {
      setBranchDbId('');
      setBranchDbInitialId('');
      setBranchDbLoading(false);
      setBranchDbReady(false);
      setFioResolveAttemptKey('');
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        setBranchDbLoading(true);
        setBranchDbReady(false);
        const mapping = await networksAPI.getBranchDbMapping(branchIdNum);
        if (cancelled) return;
        const nextDbId = String(mapping?.db_id || '').trim();
        setBranchDbId(nextDbId);
        setBranchDbInitialId(nextDbId);
        setBranchDbReady(true);
        setFioResolveAttemptKey('');
      } catch (requestError) {
        if (cancelled) return;
        console.error('Failed to load branch DB mapping:', requestError);
        setBranchDbId('');
        setBranchDbInitialId('');
        setBranchDbReady(true);
        setFioResolveAttemptKey('');
      } finally {
        if (!cancelled) setBranchDbLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [branchIdNum]);

  useEffect(() => {
    if (!branchIdNum) return;
    let aborted = false;

    void (async () => {
      try {
        setLoading(true);
        await loadBranchContext(branchIdNum);
      } catch (requestError) {
        if (!aborted) {
          console.error('Failed to load branch context:', requestError);
          notifyError(`Не удалось загрузить данные филиала: ${getErrorDetail(requestError)}`);
        }
      } finally {
        if (!aborted) setLoading(false);
      }
    })();

    return () => {
      aborted = true;
    };
  }, [branchIdNum, loadBranchContext, notifyError, getErrorDetail]);


  useEffect(() => {
    if (!branchIdNum) {
      setAllBranchPorts([]);
      return;
    }
    let aborted = false;

    void (async () => {
      try {
        await loadAllBranchPorts(branchIdNum);
      } catch (requestError) {
        if (!aborted) {
          console.error('Failed to load all branch ports:', requestError);
          notifyError(`Не удалось загрузить порты филиала: ${getErrorDetail(requestError)}`);
        }
      }
    })();

    return () => {
      aborted = true;
    };
  }, [branchIdNum, loadAllBranchPorts, notifyError, getErrorDetail]);

  useEffect(() => {
    if (!selectedDeviceId || !branchIdNum) {
      setPorts([]);
      return;
    }
    void loadPorts(selectedDeviceId);
  }, [branchIdNum, selectedDeviceId, loadPorts]);
  useEffect(() => {
    if (!isBranchWidePortSearch || displayedPorts.length === 0) return;
    const currentId = Number(selectedDeviceId || 0);
    if (currentId && matchedDeviceIds.has(currentId)) return;
    const firstDeviceId = Number(displayedPorts.find((item) => Number(item?.device_id || 0))?.device_id || 0);
    if (firstDeviceId) {
      setSelectedDeviceId(firstDeviceId);
    }
  }, [displayedPorts, isBranchWidePortSearch, matchedDeviceIds, selectedDeviceId]);

  useEffect(() => {
    const selectedId = Number(selectedDeviceId || 0);
    if (!selectedId) return;
    const node = deviceChipRefs.current.get(selectedId);
    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    const branchId = Number(branchIdNum || 0);
    const searchValue = String(portSearch || '').trim();
    if (!branchId || !searchValue) {
      setBranchPortResults([]);
      setBranchPortLoading(false);
      return undefined;
    }

    let active = true;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          setBranchPortLoading(true);
          const response = await networksAPI.getBranchPorts(branchId, { search: searchValue, limit: 5000 });
          if (!active) return;
          setBranchPortResults(Array.isArray(response?.ports) ? response.ports : []);
        } catch (requestError) {
          if (!active) return;
          console.error('Failed to search branch ports:', requestError);
          setBranchPortResults([]);
          notifyError(`Не удалось выполнить поиск портов: ${getErrorDetail(requestError)}`);
        } finally {
          if (active) setBranchPortLoading(false);
        }
      })();
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [branchIdNum, notifyError, portSearch, getErrorDetail]);

  useEffect(() => {
    let currentUrl = '';
    let aborted = false;

    if (!selectedMapId) {
      setMapBlobUrl('');
      setMapIsPdf(false);
      setMapRenderedFrom('');
      return undefined;
    }
    void (async () => {
      try {
        const response = await networksAPI.downloadMapFile(selectedMapId, { render: 'auto' });
        if (aborted) return;

        const contentType = response?.headers?.['content-type'] || 'application/octet-stream';
        const renderedFrom = String(response?.headers?.['x-map-rendered-from'] || '').toLowerCase();
        const url = URL.createObjectURL(new Blob([response.data], { type: contentType }));
        currentUrl = url;
        setMapBlobUrl(url);
        setMapIsPdf(String(contentType).toLowerCase().includes('pdf'));
        setMapRenderedFrom(renderedFrom);
      } catch (requestError) {
        if (!aborted) {
          console.error('Failed to download map file:', requestError);
          notifyError(`Не удалось открыть карту: ${getErrorDetail(requestError)}`);
        }
      }
    })();
    return () => {
      aborted = true;
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [selectedMapId, notifyError, getErrorDetail]);

  useEffect(() => {
    clearPendingPointDraft();
    setPlacingMarker(false);
    setAddPointPanelOpen(false);
  }, [selectedMapId, clearPendingPointDraft]);

  useEffect(() => {
    if (!placingMarker) return;
    const normalized = socketKey(pendingSocketInput);
    if (!normalized) return;
    if (pendingSocketMatches.length !== 1) return;
    const nextPortId = String(pendingSocketMatches[0].id || '');
    if (nextPortId && String(pendingPortId) !== nextPortId) {
      setPendingPortId(nextPortId);
    }
  }, [pendingPortId, pendingSocketInput, pendingSocketMatches, placingMarker]);

  useEffect(() => {
    if (!pointEditMode || !selectedPoint) return;
    setSelectedPointSocketInput(String(selectedPoint.patch_panel_port || ''));
  }, [pointEditMode, selectedPointId]);

  useEffect(() => {
    if (!pointEditMode || !selectedPoint) return;
    const normalized = socketKey(selectedPointSocketInput);
    if (!normalized) return;
    if (selectedPointSocketMatches.length !== 1) return;
    const matchedPort = selectedPointSocketMatches[0];
    if (Number(selectedPoint.port_id || 0) === Number(matchedPort.id || 0)) return;
    setMapPoints((prev) =>
      prev.map((point) => (point.id === selectedPoint.id
        ? {
          ...point,
          port_id: matchedPort.id,
          port_name: matchedPort.port_name || '',
          patch_panel_port: matchedPort.patch_panel_port || '',
          port_location_code: matchedPort.location_code || '',
          endpoint_ip_raw: matchedPort.endpoint_ip_raw || '',
          endpoint_mac_raw: matchedPort.endpoint_mac_raw || '',
        }
        : point))
    );
  }, [pointEditMode, selectedPoint, selectedPointSocketInput, selectedPointSocketMatches]);

  useEffect(() => {
    if (!isMobile) {
      setMobileMapPanelOpen(false);
      setMobilePortEditorOpen(false);
      return;
    }
    if (tab !== 'maps') {
      setMobileMapPanelOpen(false);
    }
    if (tab !== 'equipment') {
      setMobilePortEditorOpen(false);
    }
  }, [isMobile, tab]);

  useEffect(() => {
    if (!String(mapPointSearch || '').trim()) return;
    if (filteredPointsForMap.length === 0) return;
    const nextId = Number(filteredPointsForMap[0]?.id || 0) || null;
    if (nextId && Number(selectedPointId) !== nextId) {
      setSelectedPointId(nextId);
    }
  }, [filteredPointsForMap, mapPointSearch, selectedPointId]);

  useEffect(() => {
    if (!mapPointSearch) {
      setFocusMapPointId(null);
      return;
    }
    if (filteredPointsForMap.length === 1) {
      setFocusMapPointId(filteredPointsForMap[0].id);
    } else if (filteredPointsForMap.length > 1) {
      setFocusMapPointId(null);
    }
  }, [filteredPointsForMap, mapPointSearch]);

  const openMapDialogCreate = () => {
    setMapEditId(null);
    setMapFile(null);
    setMapTitle('');
    setMapFloor('');
    setMapSiteCode('p19');
    setMapDialogOpen(true);
  };

  const openMapDialogEdit = (map) => {
    setMapEditId(map.id);
    setMapFile(null);
    setMapTitle(String(map.title || map.file_name || ''));
    setMapFloor(String(map.floor_label || ''));
    setMapSiteCode(String(map.site_code || 'p19'));
    setMapDialogOpen(true);
  };

  const openOriginalMapFile = async () => {
    if (!selectedMapId) return;
    try {
      const response = await networksAPI.downloadMapFile(selectedMapId, { render: 'original' });
      const contentType = response?.headers?.['content-type'] || 'application/octet-stream';
      const url = URL.createObjectURL(new Blob([response.data], { type: contentType }));
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (requestError) {
      console.error(requestError);
      notifyError('Не удалось открыть оригинальный файл карты.');
    }
  };

  const saveMap = async () => {
    if (!branchIdNum) return;
    try {
      if (mapEditId) {
        await networksAPI.updateMap(mapEditId, {
          title: mapTitle.trim() || null,
          floor_label: mapFloor.trim() || null,
          site_code: mapSiteCode,
          site_name: mapSiteCode === 'p21' ? 'Первомайская 21' : 'Первомайская 19',
        });
      } else {
        if (!mapFile) {
          notifyError('Выберите файл карты.');
          return;
        }
        const formData = new FormData();
        formData.append('branch_id', String(branchIdNum));
        formData.append('file', mapFile);
        formData.append('site_code', mapSiteCode);
        formData.append('site_name', mapSiteCode === 'p21' ? 'Первомайская 21' : 'Первомайская 19');
        if (mapTitle.trim()) formData.append('title', mapTitle.trim());
        if (mapFloor.trim()) formData.append('floor_label', mapFloor.trim());
        await networksAPI.uploadMap(formData);
      }
      setMapDialogOpen(false);
      await refreshBranchContext();
      notifySuccess(mapEditId ? 'Карта обновлена.' : 'Карта добавлена.');
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка сохранения карты.');
    }
  };

  const removeMap = async (map) => {
    const mapId = Number(map?.id || 0);
    if (!mapId) return;
    const mapTitle = String(map?.title || map?.file_name || `#${mapId}`).trim();
    const confirmed = window.confirm(`Удалить карту "${mapTitle}"? Это действие нельзя отменить.`);
    if (!confirmed) return;
    try {
      await networksAPI.deleteMap(mapId);
      await refreshBranchContext();
      notifySuccess('Карта удалена.');
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка удаления карты.');
    }
  };

  const onMapClickAddPoint = ({ xRatio, yRatio }) => {
    if (!placingMarker || !selectedMapId || !branchIdNum) {
      setSelectedPointId(null);
      setFocusMapPointId(null);
      return;
    }
    setPendingPoint({ xRatio, yRatio });
    enqueueToast('Позиция на карте выбрана. Выберите розетку или PORT P/P и сохраните.', 'info');
  };

  const onMapPointDrop = useCallback(async (pointIdOrIds, newX, newY) => {
    try {
      if (Array.isArray(pointIdOrIds)) {
        await Promise.all(pointIdOrIds.map(id => networksAPI.updateMapPoint(id, { x_ratio: newX, y_ratio: newY })));
      } else {
        await networksAPI.updateMapPoint(pointIdOrIds, { x_ratio: newX, y_ratio: newY });
      }
      await refreshBranchContext();
      enqueueToast('Позиция маркера сохранена.', 'success');
    } catch (error) {
      notifyError('Ошибка перемещения маркера.');
    }
  }, [refreshBranchContext]);

  const applySocketPointDraft = useCallback((socketLike) => {
    const socketCode = String(socketLike?.socket_code || socketLike?.patch_panel_port || '').trim();
    clearPendingPointDraft();
    setPlacingMarker(true);
    setPendingPortId(String(socketLike?.port_id || ''));
    setPendingSocketId(String(socketLike?.socket_id || socketLike?.id || ''));
    setPendingSocketInput(socketCode);
    setAddPointPanelOpen(true);
    setPointDetailsOpen(false);
    if (isMobile) {
      setMobileMapPanelOpen(true);
    }
  }, [clearPendingPointDraft, isMobile]);

  const commitPendingPoint = async () => {
    if (!pendingPoint || !selectedMapId || !branchIdNum) {
      notifyError('Сначала выберите позицию на карте.');
      return;
    }
    const autoMatchedPortId = pendingSocketMatches.length === 1 ? Number(pendingSocketMatches[0]?.id || 0) : 0;
    const effectivePendingPortId = Number(pendingPortId || autoMatchedPortId || 0) || null;
    const effectivePendingSocketId = Number(pendingSocketId || 0) || null;
    if (!effectivePendingPortId && !effectivePendingSocketId) {
      notifyError('Выберите розетку или порт с заполненным PORT P/P.');
      return;
    }
    const effectivePort = effectivePendingPortId
      ? (pendingPortOptions.find((port) => Number(port.id) === Number(effectivePendingPortId))
        || allPortsWithSocket.find((port) => Number(port.id) === Number(effectivePendingPortId))
        || null)
      : null;
    const effectiveSocket = effectivePendingSocketId
      ? (pendingSocketOptions.find((socketItem) => Number(socketItem.id) === Number(effectivePendingSocketId))
        || sockets.find((socketItem) => Number(socketItem.id) === Number(effectivePendingSocketId))
        || null)
      : null;
    const resolvedPortId = Number(effectivePort?.id || effectiveSocket?.port_id || 0) || null;
    const resolvedSocketId = Number(effectiveSocket?.id || effectivePort?.socket_id || 0) || null;
    const resolvedDeviceId = Number(effectivePort?.device_id || effectiveSocket?.device_id || 0) || undefined;
    if (!resolvedPortId && !resolvedSocketId) {
      notifyError('Не удалось определить порт или розетку для привязки.');
      return;
    }
    try {
      await networksAPI.createMapPoint({
        branch_id: branchIdNum,
        map_id: selectedMapId,
        device_id: resolvedDeviceId,
        port_id: resolvedPortId || undefined,
        socket_id: resolvedSocketId || undefined,
        x_ratio: pendingPoint.xRatio,
        y_ratio: pendingPoint.yRatio,
        label: null,
      });
      clearPendingPointDraft();
      setPlacingMarker(false);
      setCreatePointHint(null);
      await refreshBranchContext();
      notifySuccess('Розетка привязана к карте.');
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка привязки розетки.');
    }
  };

  const selectPoint = (point) => {
    setSelectedPointId(point.id);
    setPointEditMode(false);
    setCreatePointHint(null);
    if (point.device_id) {
      setSelectedDeviceId(point.device_id);
    }
  };

  const onMapPointSelect = (point) => {
    selectPoint(point);
    if (isMobile) {
      setMobileMapPanelOpen(false);
    }
    setPointDetailsOpen(true);
  };

  const onPointRowSelect = (point) => {
    selectPoint(point);
  };

  const saveSelectedPoint = async () => {
    if (!selectedPoint) return;
    const nextPortId = Number(selectedPoint.port_id || 0);
    if (!nextPortId) {
      notifyError('Для точки необходимо выбрать порт с заполненным PORT P/P.');
      return;
    }
    try {
      await networksAPI.updateMapPoint(selectedPoint.id, {
        port_id: nextPortId,
        label: selectedPoint.label || null,
        note: selectedPoint.note || null,
        color: selectedPoint.color || null,
      });
      await refreshBranchContext();
      setPointEditMode(false);
      notifySuccess('Точка обновлена.');
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка обновления точки.');
    }
  };

  const removeSelectedPoint = async () => {
    if (!selectedPoint) return;
    try {
      await networksAPI.deleteMapPoint(selectedPoint.id);
      setSelectedPointId(null);
      setPointEditMode(false);
      await refreshBranchContext();
      notifySuccess('Точка удалена.');
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка удаления точки.');
    }
  };



  const startSocketPointCreation = (socketLike) => {
    const socketCode = String(socketLike?.socket_code || socketLike?.patch_panel_port || '').trim();
    const mapIdCandidate = Number(socketLike?.map_id || selectedMapId || maps?.[0]?.id || 0) || null;
    setTab('maps');
    if (!mapIdCandidate) {
      setCreatePointHint(null);
      notifyError('Для филиала не добавлена карта. Сначала загрузите карту.');
      return;
    }
    const socketDraft = {
      map_id: mapIdCandidate,
      socket_code: socketCode,
      socket_id: socketLike?.socket_id || socketLike?.id || '',
      port_id: socketLike?.port_id || '',
    };
    setCreatePointHint(socketDraft);
    setSelectedMapId(mapIdCandidate);
    if (Number(selectedMapId || 0) !== Number(mapIdCandidate || 0)) {
      window.setTimeout(() => applySocketPointDraft(socketDraft), 0);
    } else {
      applySocketPointDraft(socketDraft);
    }
    enqueueToast(
      `Для розетки ${socketCode || '-'} точка не найдена. Нажмите на карту, чтобы создать точку и привязать розетку.`,
      'warning'
    );
  };

  const handleSocketRowClick = (socketItem, event) => {
    const target = event?.target;
    if (target instanceof Element && target.closest('button, input, textarea, [role="button"], .MuiInputBase-root, .MuiIconButton-root, a, svg')) {
      return;
    }
    if (!socketItem?.map_point_id) {
      startSocketPointCreation(socketItem);
      return;
    }
    setTab('maps');
    if (socketItem?.map_id) setSelectedMapId(Number(socketItem.map_id));
    if (socketItem?.device_id) setSelectedDeviceId(Number(socketItem.device_id));
    setSelectedPointId(Number(socketItem.map_point_id));
    setFocusMapPointId(Number(socketItem.map_point_id));
    setPointDetailsOpen(false);
  };

  const openCreateSocketDialog = useCallback(() => {
    setSocketCreateCode('');
    setSocketCreateMac('');
    setSocketCreateOpen(true);
  }, []);

  const closeCreateSocketDialog = useCallback(() => {
    if (socketCreateSaving) return;
    setSocketCreateOpen(false);
  }, [socketCreateSaving]);

  const createSocket = useCallback(async () => {
    if (!branchIdNum) {
      notifyError('Филиал не выбран.');
      return;
    }
    const socketCode = String(socketCreateCode || '').trim();
    if (!socketCode) {
      notifyError('Укажите код розетки.');
      return;
    }
    try {
      setSocketCreateSaving(true);
      await networksAPI.createSocket(branchIdNum, {
        socket_code: socketCode,
        mac_address: String(socketCreateMac || '').trim() || null,
      });
      setSocketCreateOpen(false);
      await refreshBranchContext();
      notifySuccess(`Розетка ${socketCode} добавлена.`);
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка добавления розетки.');
    } finally {
      setSocketCreateSaving(false);
    }
  }, [branchIdNum, socketCreateCode, socketCreateMac, notifyError, refreshBranchContext, notifySuccess]);

  const requestDeleteSocket = useCallback((socketItem, event) => {
    event?.stopPropagation?.();
    if (!socketItem?.id) return;
    setSocketDeleteTarget(socketItem);
    setSocketDeleteOpen(true);
  }, []);

  const closeDeleteSocketDialog = useCallback(() => {
    if (socketDeleteSaving) return;
    setSocketDeleteOpen(false);
    setSocketDeleteTarget(null);
  }, [socketDeleteSaving]);

  const confirmDeleteSocket = useCallback(async () => {
    if (!socketDeleteTarget?.id) return;
    try {
      setSocketDeleteSaving(true);
      await networksAPI.deleteSocket(socketDeleteTarget.id);
      setSocketDeleteOpen(false);
      setSocketDeleteTarget(null);
      await refreshBranchContext();
      notifySuccess(`Розетка ${socketDeleteTarget.socket_code || '-'} удалена.`);
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка удаления розетки.');
    } finally {
      setSocketDeleteSaving(false);
    }
  }, [socketDeleteTarget, refreshBranchContext, notifySuccess, notifyError]);

  useEffect(() => {
    const normalizedBranchId = Number(branchIdNum || 0);
    if (!normalizedBranchId || fioResolving || branchDbLoading || !branchDbReady) return;
    const normalizedDbId = String(branchDbId || '').trim();
    const attemptKey = `${normalizedBranchId}:${normalizedDbId || '-'}`;
    if (attemptKey === fioResolveAttemptKey) return;
    setFioResolveAttemptKey(attemptKey);

    const resolveSilently = async () => {
      if (!normalizedDbId) {
        enqueueToast('Для филиала не настроена БД для синхронизации по MAC. Выберите БД и сохраните.', 'warning');
        return;
      }
      try {
        setFioResolving(true);
        const res = await networksAPI.syncSocketHostContext(normalizedBranchId);
        if (Number(res?.updated || res?.resolved || 0) > 0) {
          enqueueToast(`Синхронизированы IP/MAC/ФИО по MAC для ${Number(res?.updated || res?.resolved || 0)} розеток/портов.`, 'success');
          await refreshBranchContext();
        }
      } catch (err) {
        console.error('Silent MAC sync error:', err);
        enqueueToast(err?.response?.data?.detail || 'Ошибка синхронизации по MAC.', 'warning');
      } finally {
        setFioResolving(false);
      }
    };
    resolveSilently();
  }, [branchIdNum, branchDbId, branchDbLoading, branchDbReady, fioResolveAttemptKey, fioResolving, enqueueToast, refreshBranchContext]);

  const handleEquipImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !branchIdNum) return;
    e.target.value = '';
    try {
      setEquipImportLoading(true);
      const form = new FormData();
      form.append('excel_file', file);
      const result = await networksAPI.importEquipment(branchIdNum, form);
      const s = result?.summary || {};
      notifySuccess(
        `мпорт завершён: устройств создано ${s.devices_created || 0}, обновлено ${s.devices_updated || 0}; портов ${s.ports_created || 0}`,
      );
      // Invalidate all caches so fresh data is loaded
      invalidateSWRCacheByPrefix('networks', 'branch-context', branchIdNum);
      invalidateSWRCacheByPrefix('networks', 'branch-ports-all', branchIdNum);
      // Also invalidate per-device port caches (all devices in this branch)
      invalidateSWRCacheByPrefix('networks', 'ports');
      // Reset the current ports list so table shows correct state
      setPorts([]);
      setSelectedDeviceId(null);
      // Reload branch context and all ports
      await Promise.all([loadBranchContext(branchIdNum, true), loadAllBranchPorts(branchIdNum, true)]);
    } catch (err) {
      console.error(err);
      notifyError(err?.response?.data?.detail || 'Ошибка импорта оборудования.');
    } finally {
      setEquipImportLoading(false);
    }
  };

  const createBranchWithProfile = async () => {
    const branchName = String(createBranchName || '').trim();
    if (!branchName) {
      notifyError('Заполните название филиала.');
      return;
    }

    let payload = {
      city_code: createBranchCity || 'tmn',
      branch_name: branchName,
      default_site_code: createBranchDefaultSiteCode || null,
      db_id: createBranchDbId || null,
    };

    if (createFillMode !== 'template') {
      if (createPanelMode === 'uniform') {
        const panelCount = Number(createPanelCount || 0);
        const portsPerPanel = Number(createPortsPerPanel || 0);
        if (!panelCount || !portsPerPanel) {
          notifyError('Укажите профиль патч-панелей.');
          return;
        }
        payload.panel_count = panelCount;
        payload.ports_per_panel = portsPerPanel;
      } else {
        // heterogeneous mode
        if (!createPanels || createPanels.length === 0) {
          notifyError('Добавьте хотя бы одну патч-панель.');
          return;
        }
        payload.panels = createPanels.map(p => ({
          panel_index: Number(p.panelIndex),
          port_count: Number(p.portCount),
        }));
      }
    }

    if (createFillMode === 'template' && !createTemplateFile) {
      notifyError('Выберите файл шаблона.');
      return;
    }

    try {
      setCreateBranchSaving(true);
      const created = await networksAPI.createBranch(payload);
      const createdBranchId = Number(created?.branch?.id || 0) || null;
      const normalizedCreateDbId = String(createBranchDbId || '').trim();
      if (createdBranchId && normalizedCreateDbId) {
        try {
          await networksAPI.updateBranchDbMapping(createdBranchId, { db_id: normalizedCreateDbId });
        } catch (mappingError) {
          console.error('Failed to save branch DB mapping after create:', mappingError);
          notifyError(
            mappingError?.response?.data?.detail
            || 'Филиал создан, но БД для синхронизации по MAC не сохранена. Сохраните ее в параметрах филиала.',
          );
        }
      }
      if (createdBranchId && createFillMode === 'template' && createTemplateFile) {
        const form = new FormData();
        form.append('excel_file', createTemplateFile);
        await networksAPI.importEquipment(createdBranchId, form);
      }
      setCreateBranchOpen(false);
      setCreateBranchName('');
      setCreateBranchDefaultSiteCode('');
      setCreateBranchDbId('');
      setCreatePanelMode('uniform');
      setCreatePanelCount('6');
      setCreatePortsPerPanel('48');
      setCreatePanels([{ id: 1, panelIndex: 1, portCount: 48 }]);
      setCreateFillMode('manual');
      setCreateTemplateFile(null);
      invalidateSWRCacheByPrefix('networks', 'branches', 'tmn');
      await loadBranches();
      notifySuccess('Филиал создан.');
      if (createdBranchId) navigate(`/networks/${createdBranchId}`);
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка создания филиала.');
    } finally {
      setCreateBranchSaving(false);
    }
  };

  const saveBranchDbMapping = async () => {
    const normalizedBranchId = Number(branchIdNum || 0);
    const normalizedDbId = String(branchDbId || '').trim();
    if (!normalizedBranchId) return;
    if (!normalizedDbId) {
      notifyError('Выберите базу для синхронизации по MAC.');
      return;
    }
    try {
      setBranchDbSaving(true);
      await networksAPI.updateBranchDbMapping(normalizedBranchId, { db_id: normalizedDbId });
      setBranchDbInitialId(normalizedDbId);
      setFioResolveAttemptKey('');
      await loadBranches();
      notifySuccess('База для синхронизации по MAC сохранена.');
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка сохранения базы для синхронизации по MAC.');
    } finally {
      setBranchDbSaving(false);
    }
  };

  const openEditBranchDialog = async (branch) => {
    setBranchEditId(branch.id);
    setBranchEditName(String(branch.name || ''));
    setBranchDefaultSiteCode(branch.default_site_code || '');
    setBranchEditDbId('');
    setBranchEditDialogOpen(true);
    try {
      setBranchEditLoading(true);
      const mapping = await networksAPI.getBranchDbMapping(branch.id);
      setBranchEditDbId(String(mapping?.db_id || ''));
    } catch (err) {
      console.error('Failed to load branch DB mapping for edit:', err);
      setBranchEditDbId('');
    } finally {
      setBranchEditLoading(false);
    }
  };

  const saveBranchEdit = async () => {
    if (!branchEditId) return;
    const normalizedName = String(branchEditName || '').trim();
    if (!normalizedName) {
      notifyError('Название филиала не может быть пустым.');
      return;
    }
    try {
      setBranchEditSaving(true);
      await networksAPI.updateBranch(branchEditId, {
        branch_name: normalizedName,
        default_site_code: String(branchDefaultSiteCode || '').trim(),
        db_id: String(branchEditDbId || '').trim(),
      });
      notifySuccess('Филиал обновлён');
      if (Number(branchIdNum || 0) === Number(branchEditId || 0)) {
        const currentDb = String(branchEditDbId || '').trim();
        setBranchDbId(currentDb);
        setBranchDbInitialId(currentDb);
        setFioResolveAttemptKey('');
        await refreshBranchContext();
      }
      invalidateSWRCacheByPrefix('networks', 'branches', 'tmn');
      await loadBranches();
      setBranchEditDialogOpen(false);
    } catch (err) {
      console.error(err);
      notifyError(err?.response?.data?.detail || 'Ошибка обновления филиала.');
    } finally {
      setBranchEditSaving(false);
    }
  };

  const openDeleteBranchDialog = (branch) => {
    setBranchDeleteId(branch.id);
    setBranchDeleteName(branch.name);
    setBranchDeleteDialogOpen(true);
  };

  const confirmDeleteBranch = async () => {
    if (!branchDeleteId) return;
    try {
      setBranchDeleteSaving(true);
      await networksAPI.deleteBranch(branchDeleteId);
      notifySuccess('Филиал удалён');
      invalidateSWRCacheByPrefix('networks', 'branches', 'tmn');
      await loadBranches();
      setBranchDeleteDialogOpen(false);
      // Navigate away if we deleted the current branch
      if (branchIdNum === branchDeleteId) {
        navigate('/networks');
      }
    } catch (err) {
      console.error(err);
      notifyError(err?.response?.data?.detail || 'Ошибка удаления филиала.');
    } finally {
      setBranchDeleteSaving(false);
    }
  };

  const addPanel = () => {
    const nextIndex = createPanels.length > 0
      ? Math.max(...createPanels.map(p => Number(p.panelIndex) || 0)) + 1
      : 1;
    setCreatePanels([...createPanels, { id: Date.now(), panelIndex: nextIndex, portCount: 48 }]);
  };

  const removePanel = (id) => {
    setCreatePanels(createPanels.filter(p => p.id !== id));
  };

  const updatePanel = (id, field, value) => {
    setCreatePanels(createPanels.map(p =>
      p.id === id ? { ...p, [field]: value } : p
    ));
  };

  const updatePanelPortCount = (id, value) => {
    updatePanel(id, 'portCount', value);
  };

  const updatePanelIndex = (id, value) => {
    updatePanel(id, 'panelIndex', value);
  };

  const startEditPort = (port, event) => {
    event?.stopPropagation?.();
    setEditingPortId(port.id);
    setPortDraft(makePortDraft(port));
    setSelectedSocketId(null); // Reset selected socket

    // Load FREE socket options for autocomplete when editing starts
    const currentSocketValue = String(port.patch_panel_port || '').trim();
    const filteredFreeSockets = freeSockets.filter((socketItem) => {
      if (!currentSocketValue) return true;
      const socketKeyValue = socketKey(socketItem.socket_code);
      const currentSocketKeyValue = socketKey(currentSocketValue);
      return socketKeyValue.includes(currentSocketKeyValue) || currentSocketKeyValue.includes(socketKeyValue);
    });

    setSocketAutocompleteOptions(filteredFreeSockets);

    if (isMobile) {
      setMobilePortEditorOpen(true);
    }
  };

  const cancelEditPort = (event) => {
    event?.stopPropagation?.();
    setEditingPortId(null);
    setPortDraft(null);
    setSelectedSocketId(null);
    setSocketAutocompleteOpen(false);
    setMobilePortEditorOpen(false);
  };

  const updatePortDraftField = (field, value) => {
    setPortDraft((prev) => ({
      ...(prev || {}),
      [field]: value,
    }));

    // Update socket autocomplete options when patch_panel_port changes
    if (field === 'patch_panel_port') {
      const searchValue = String(value || '').trim();
      if (!searchValue) {
        setSocketAutocompleteOptions(freeSockets);
      } else {
        const filteredFreeSockets = freeSockets.filter((socketItem) => {
          const socketKeyValue = socketKey(socketItem.socket_code);
          const searchKeyValue = socketKey(searchValue);
          return socketKeyValue.includes(searchKeyValue) || searchKeyValue.includes(socketKeyValue);
        });
        setSocketAutocompleteOptions(filteredFreeSockets);
      }
    }
  };

  // Device dialog handlers
  const openCreateDeviceDialog = () => {
    const defaultSiteCode = selectedBranch?.default_site_code || determineSiteCode(selectedBranch?.name);
    setDeviceEditId(null);
    setDeviceCode('');
    setDeviceType('switch');           // Default: switch
    setDeviceSiteCode(defaultSiteCode); // Smart default from branch name
    setDeviceSiteName('');             // Not used - auto on backend
    setDeviceVendor('');
    setDeviceModel('');
    setDeviceSheetName('');            // Will be auto from device_code
    setDeviceMgmtIp('');
    setDeviceNotes('');
    setDevicePortCount('');            // Port count - only for new devices
    setDeviceDialogOpen(true);
  };

  const openEditDeviceDialog = (device) => {
    setDeviceEditId(device.id);
    setDeviceCode(device.device_code || '');
    setDeviceType(device.device_type || 'switch');
    setDeviceSiteCode(device.site_code || '');
    setDeviceSiteName(device.site_name || '');
    setDeviceVendor(device.vendor || '');
    setDeviceModel(device.model || '');
    setDeviceSheetName(device.sheet_name || '');
    setDeviceMgmtIp(device.mgmt_ip || '');
    setDeviceNotes(device.notes || '');
    setDevicePortCount('');          // Not used when editing
    setDeviceDialogOpen(true);
  };

  const saveDevice = async () => {
    const code = String(deviceCode || '').trim();
    if (!code) {
      notifyError('Код устройства обязателен.');
      return;
    }
    if (!branchIdNum) {
      notifyError('Филиал не выбран.');
      return;
    }
    try {
      setDeviceSaving(true);
      const payload = {
        branch_id: branchIdNum,
        device_code: code,
        device_type: deviceType || 'switch',
        site_code: String(deviceSiteCode || '').trim() || null,
        // site_name is auto-generated on backend via _ensure_site
        vendor: String(deviceVendor || '').trim() || null,
        model: String(deviceModel || '').trim() || null,
        sheet_name: String(deviceSheetName || '').trim() || null,
        mgmt_ip: String(deviceMgmtIp || '').trim() || null,
        notes: String(deviceNotes || '').trim() || null,
      };

      if (deviceEditId) {
        await networksAPI.updateDevice(deviceEditId, payload);
        notifySuccess(`Устройство ${code} обновлено.`);
        await refreshBranchContext();
      } else {
        const created = await networksAPI.createDevice(payload);
        const deviceId = created?.id;
        notifySuccess(`Устройство ${code} создано.`);

        // Bootstrap ports if port count is specified
        const portCount = Number(devicePortCount || 0);
        if (deviceId && portCount > 0) {
          try {
            await networksAPI.bootstrapDevicePorts(deviceId, { port_count: portCount });
            notifySuccess(`Создано ${portCount} портов.`);
          } catch (portError) {
            console.error('Failed to bootstrap ports:', portError);
            notifyError('Не удалось создать порты.');
          }
        }

        // Refresh branch context FIRST to update devices list
        await refreshBranchContext();

        // THEN select the newly created device so ports are loaded
        if (deviceId) {
          setSelectedDeviceId(deviceId);
        }
      }

      setDeviceDialogOpen(false);
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка сохранения устройства.');
    } finally {
      setDeviceSaving(false);
    }
  };

  const deleteDevice = async () => {
    if (!deviceEditId) {
      notifyError('Устройство не выбрано.');
      return;
    }
    try {
      setDeviceDeleting(true);
      await networksAPI.deleteDevice(deviceEditId);
      notifySuccess('Устройство удалено.');
      if (Number(selectedDeviceId) === Number(deviceEditId)) {
        setSelectedDeviceId(null);
      }
      await refreshBranchContext();
      setDeviceDialogOpen(false);
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка удаления устройства.');
    } finally {
      setDeviceDeleting(false);
    }
  };

  const savePortEdit = async (port, event) => {
    event?.stopPropagation?.();
    if (!editingPortId || !portDraft) return;
    try {
      setPortSaving(true);

      // If a socket was selected, add socket_id to the payload
      const payload = { ...portDraft };
      payload.endpoint_mac_raw = normalizeMacField(payload.endpoint_mac_raw);
      if (selectedSocketId) {
        payload.socket_id = selectedSocketId;
      }

      const updatedPort = await networksAPI.updatePort(port.id, payload);
      if (selectedDeviceId) {
        invalidateSWRCacheByPrefix('networks', 'ports', selectedDeviceId);
        await loadPorts(selectedDeviceId, true);
      }
      if (isBranchWidePortSearch && branchIdNum) {
        const response = await networksAPI.getBranchPorts(branchIdNum, { search: String(portSearch || '').trim(), limit: 5000 });
        setBranchPortResults(Array.isArray(response?.ports) ? response.ports : []);
      }
      await refreshBranchContext();
      notifySuccess(`Порт ${portDraft.port_name || port.port_name} обновлён.`);
      setEditingPortId(null);
      setPortDraft(null);
      setSelectedSocketId(null);
      setMobilePortEditorOpen(false);
      if (updatedPort?.requires_point_creation) {
        startSocketPointCreation({
          socket_id: updatedPort.socket_id,
          socket_code: updatedPort.socket_code || updatedPort.patch_panel_port || portDraft.patch_panel_port,
          port_id: updatedPort.id || port.id,
          map_id: updatedPort.map_id || selectedMapId,
        });
      }
    } catch (requestError) {
      console.error(requestError);
      notifyError(requestError?.response?.data?.detail || 'Ошибка сохранения порта.');
    } finally {
      setPortSaving(false);
    }
  };


  useEffect(() => {
    const handleKeyDown = (e) => {
      // Escape key
      if (e.key === 'Escape') {
        if (editingPortId) cancelEditPort(e);
      }

      // Ctrl + S or Meta + S
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        if (editingPortId) {
          e.preventDefault();
          const portObj = displayedPorts.find(p => Number(p.id) === Number(editingPortId)) || { id: editingPortId };
          savePortEdit(portObj, e);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [editingPortId, displayedPorts, cancelEditPort, savePortEdit]);

  const setDeviceChipRef = useCallback((deviceId, node) => {
    const key = Number(deviceId || 0);
    if (!key) return;
    if (node) {
      deviceChipRefs.current.set(key, node);
    } else {
      deviceChipRefs.current.delete(key);
    }
  }, []);
  const handlePortRowClick = (port, event) => {
    const target = event?.target;
    if (target instanceof Element) {
      if (target.closest('button, input, textarea, [role="button"], .MuiInputBase-root, .MuiIconButton-root, a, svg')) {
        return;
      }
    }
    if (!port?.id) return;
    if (port.device_id) setSelectedDeviceId(Number(port.device_id));

    const linkedPoint = mapPoints.find((point) => Number(point.socket_id) === Number(port.socket_id))
      || mapPoints.find((point) => Number(point.port_id) === Number(port.id));
    if (!linkedPoint) {
      startSocketPointCreation({
        socket_id: port.socket_id,
        socket_code: port.socket_code || port.patch_panel_port,
        port_id: port.id,
        map_id: selectedMapId,
      });
      return;
    }

    setTab('maps');
    if (linkedPoint.map_id) setSelectedMapId(Number(linkedPoint.map_id));
    if (linkedPoint.device_id) setSelectedDeviceId(Number(linkedPoint.device_id));
    setSelectedPointId(Number(linkedPoint.id));
    setFocusMapPointId(Number(linkedPoint.id));
    setPointDetailsOpen(false);
  };

  const mapSidePanelContent = (
    <Stack spacing={0.8}>
      {isMobile && (
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 0.4 }}>
          <Typography variant="subtitle2">Панель карты</Typography>
          <IconButton size="small" onClick={() => setMobileMapPanelOpen(false)}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      )}

      {/* ═══ Выбор карты ═══ */}
      <Paper variant="outlined" sx={{ p: 1.2 }}>
        <TextField select size="small" fullWidth label="Карта" value={selectedMapId || ''} onChange={(event) => setSelectedMapId(Number(event.target.value) || null)}>
          {maps.map((map) => (
            <MenuItem key={map.id} value={map.id}>{map.title || map.file_name}</MenuItem>
          ))}
        </TextField>
        {canEdit && (
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Button size="small" onClick={() => selectedMap && openMapDialogEdit(selectedMap)} disabled={!selectedMap}>Правка</Button>
            <Button size="small" color="error" onClick={() => selectedMap && void removeMap(selectedMap)} disabled={!selectedMap}>Удалить</Button>
          </Stack>
        )}
        {selectedMapIsPdfSource && (
          <Button size="small" startIcon={<DownloadIcon />} onClick={() => void openOriginalMapFile()} sx={{ mt: 0.5 }}>
            Открыть оригинал PDF
          </Button>
        )}
      </Paper>

      {/* ═══ 1. Поиск и обзор ═══ */}
      <Accordion
        defaultExpanded
        disableGutters
        elevation={0}
        sx={{
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: '8px !important',
          '&:before': { display: 'none' },
          overflow: 'hidden',
        }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 0.5 } }}>
          <Stack direction="row" spacing={0.8} alignItems="center">
            <SearchIcon sx={{ fontSize: 18, color: 'primary.main' }} />
            <Typography variant="subtitle2">Поиск и обзор</Typography>
            <Chip size="small" label={filteredPointsForMap.length} sx={{ height: 20, fontSize: '0.7rem' }} />
          </Stack>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0, px: 1.2, pb: 1.2 }}>
          <Stack spacing={1}>
            <TextField
              size="small"
              label="Поиск на карте"
              placeholder="PORT, розетка, IP, MAC"
              value={mapPointSearch}
              onChange={(event) => setMapPointSearch(event.target.value)}
              InputProps={{ startAdornment: <SearchIcon sx={{ fontSize: 16, mr: 0.5, color: 'text.disabled' }} /> }}
            />
            {createPointHint && (
              <Alert
                severity="warning"
                action={(
                  <Stack direction="row" spacing={0.5}>
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => startSocketPointCreation(createPointHint)}
                    >
                      Создать точку
                    </Button>
                    <IconButton size="small" onClick={() => setCreatePointHint(null)}>
                      <CloseIcon fontSize="inherit" />
                    </IconButton>
                  </Stack>
                )}
              >
                Точка для розетки {createPointHint.socket_code || '-'} не найдена.
              </Alert>
            )}
            <TableContainer sx={{ maxHeight: isMobile ? 200 : 260 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ py: 0.3, fontSize: '0.72rem', fontWeight: 700 }}>PORT P/P</TableCell>
                    <TableCell sx={{ py: 0.3, fontSize: '0.72rem', fontWeight: 700 }}>PORT</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredPointsForMap.map((point) => (
                    <TableRow
                      key={point.id}
                      hover
                      selected={Number(point.id) === Number(selectedPointId)}
                      onClick={() => onPointRowSelect(point)}
                      sx={{ cursor: 'pointer', '& td': { py: 0.3, fontSize: '0.75rem' } }}
                    >
                      <TableCell>{point.patch_panel_port || '-'}</TableCell>
                      <TableCell>{point.port_name || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Stack>
        </AccordionDetails>
      </Accordion>

      {/* ═══ 2. Добавление точки ═══ */}
      <Accordion
        disableGutters
        elevation={0}
        expanded={addPointPanelOpen}
        onChange={(_, expanded) => setAddPointPanelOpen(Boolean(expanded))}
        sx={{
          border: '1px solid',
          borderColor: placingMarker ? 'primary.main' : 'divider',
          borderRadius: '8px !important',
          '&:before': { display: 'none' },
          overflow: 'hidden',
          transition: 'border-color 0.2s',
        }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 0.5 } }}>
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" sx={{ width: '100%' }}>
            <Stack direction="row" spacing={0.8} alignItems="center">
              <PlaceIcon sx={{ fontSize: 18, color: placingMarker ? 'warning.main' : 'text.secondary' }} />
              <Typography variant="subtitle2" color={placingMarker ? 'warning.main' : 'text.primary'}>
                {placingMarker ? 'Размещение точки…' : 'Добавить точку'}
              </Typography>
            </Stack>
            <Button
              variant={placingMarker ? 'outlined' : 'contained'}
              color={placingMarker ? 'warning' : 'primary'}
              size="small"
              disabled={Boolean(addPointDisabledReason)}
              startIcon={placingMarker ? <CloseIcon /> : <PlaceIcon />}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                togglePlacingMarker();
              }}
            >
              {placingMarker ? 'Отменить размещение' : 'Выбрать место на карте'}
            </Button>
          </Stack>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0, px: 1.2, pb: 1.2 }}>
          <Stack spacing={1}>
            {addPointDisabledReason ? (
              <Alert severity={!canEdit ? 'warning' : 'info'}>
                {addPointDisabledReason}
              </Alert>
            ) : null}

            {placingMarker && (
              <Paper variant="outlined" sx={{ p: 1, bgcolor: 'background.default' }}>
                <Stack spacing={1}>
                  <Typography variant="caption" color="text.secondary">
                    1. Нажмите на место розетки на карте.
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    2. Выберите розетку (или порт с заполненным PORT P/P).
                  </Typography>
                  {pendingPoint ? (
                    <Chip
                      size="small"
                      color="success"
                      icon={<PlaceIcon />}
                      label={`X ${pendingPoint.xRatio.toFixed(3)} · Y ${pendingPoint.yRatio.toFixed(3)}`}
                    />
                  ) : (
                    <Chip size="small" color="warning" variant="outlined" label="Координаты не выбраны" />
                  )}
                  <TextField
                    size="small"
                    label="PORT P/P"
                    placeholder="Напр. 6/46"
                    value={pendingSocketInput}
                    onChange={(event) => setPendingSocketInput(event.target.value)}
                    helperText={pendingSocketInput
                      ? (pendingSocketMatches.length === 1
                        ? 'Найден 1 порт, подставится автоматически'
                        : pendingSocketMatches.length > 1
                          ? `Найдено ${pendingSocketMatches.length} портов`
                          : 'Совпадений не найдено')
                      : 'Введите розетку для автопоиска'}
                  />
                  <TextField
                    select
                    size="small"
                    label="Розетка для привязки"
                    value={pendingSocketValue}
                    onChange={(event) => {
                      const nextSocketId = String(event.target.value || '');
                      const nextSocket = pendingSocketOptions.find((socketItem) => String(socketItem.id) === nextSocketId) || null;
                      setPendingSocketId(nextSocketId);
                      if (nextSocket?.socket_code) {
                        setPendingSocketInput(String(nextSocket.socket_code));
                      }
                      if (nextSocket?.port_id) {
                        setPendingPortId(String(nextSocket.port_id));
                      }
                    }}
                    helperText={pendingSocketOptions.length ? `${pendingSocketOptions.length} доступных розеток` : 'Розетки по фильтру не найдены'}
                  >
                    {pendingSocketOptions.map((socketItem) => (
                      <MenuItem key={socketItem.id} value={String(socketItem.id)}>
                        {socketItem.socket_code || '-'}{socketItem.device_code ? ` · ${socketItem.device_code}` : ''}{socketItem.port_name ? ` · PORT ${socketItem.port_name}` : ''}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    select
                    size="small"
                    label="PORT P/P для привязки"
                    value={pendingPortValue}
                    onChange={(event) => {
                      const nextPortId = String(event.target.value || '');
                      const nextPort = pendingPortOptions.find((port) => String(port.id) === nextPortId) || null;
                      setPendingPortId(nextPortId);
                      if (nextPort?.socket_id) {
                        setPendingSocketId(String(nextPort.socket_id));
                      }
                      if (nextPort?.patch_panel_port) {
                        setPendingSocketInput(String(nextPort.patch_panel_port));
                      }
                    }}
                    helperText={pendingPortOptions.length ? `${pendingPortOptions.length} доступных портов` : 'По вашему PORT P/P порты не найдены'}
                  >
                    {pendingPortOptions.map((port) => (
                      <MenuItem key={port.id} value={String(port.id)}>
                        {formatSocketPort(port)}
                      </MenuItem>
                    ))}
                  </TextField>
                  {selectedPendingPort && (
                    <Typography variant="caption" color="text.secondary">
                      {selectedPendingPort.location_code ? `Локация: ${selectedPendingPort.location_code} · ` : ''}
                      {selectedPendingPort.endpoint_ip_raw ? `IP: ${selectedPendingPort.endpoint_ip_raw}` : 'IP не указан'}
                    </Typography>
                  )}
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<PlaceIcon />}
                    onClick={() => void commitPendingPoint()}
                    disabled={!pendingPoint || (!pendingPortId && !pendingSocketId)}
                  >
                    Привязать розетку
                  </Button>
                </Stack>
              </Paper>
            )}
          </Stack>
        </AccordionDetails>
      </Accordion>

      {/* ═══ 3. Детали точки ═══ */}
      {selectedPoint && (
        <Accordion
          defaultExpanded
          disableGutters
          elevation={0}
          sx={{
            border: '1px solid',
            borderColor: 'primary.main',
            borderRadius: '8px !important',
            '&:before': { display: 'none' },
            overflow: 'hidden',
          }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 0.5 } }}>
            <Stack direction="row" spacing={0.8} alignItems="center">
              <PlaceIcon sx={{ fontSize: 18, color: 'primary.main' }} />
              <Typography variant="subtitle2">Детали точки</Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0, px: 1.2, pb: 1.2 }}>
            <Stack spacing={0.8}>
              {selectedCluster && selectedCluster.length > 1 && (
                <Stack direction="row" spacing={0.5} sx={{ mb: 0.5, flexWrap: 'wrap', gap: 0.5 }}>
                  {selectedCluster.map((p) => {
                    const isSelf = Number(p.id) === Number(selectedPoint.id);
                    const label = String(p.patch_panel_port || p.device_code || p.id);
                    return (
                      <Chip
                        key={p.id}
                        label={label}
                        size="small"
                        color={isSelf ? 'primary' : 'default'}
                        onClick={() => setSelectedPointId(Number(p.id))}
                        sx={{ cursor: 'pointer', height: 24, fontSize: '0.75rem' }}
                      />
                    );
                  })}
                </Stack>
              )}
              <Typography variant="caption" color="text.secondary">
                {formatSocketPort(selectedPoint)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                📡 {selectedPoint.device_code || '-'}{selectedPoint.device_model ? ` · ${selectedPoint.device_model}` : ''}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                📍 {selectedPoint.port_location_code || '-'} · 🌐 {selectedPoint.endpoint_ip_raw || '-'} · 💻 {selectedPoint.endpoint_mac_raw || '-'}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem', lineHeight: 1.2 }}>
                👤 {(() => {
                  const pId = Number(selectedPoint.port_id || 0);
                  const sId = Number(selectedPoint.socket_id || 0);
                  let foundFio = selectedPoint.fio;
                  if (!foundFio && pId) {
                    const port = allPortsWithSocket?.find(p => Number(p.id) === pId);
                    if (port?.fio) foundFio = port.fio;
                  }
                  if (!foundFio && sId) {
                    const sock = sockets?.find(s => Number(s.id) === sId);
                    if (sock?.fio) foundFio = sock.fio;
                  }
                  return foundFio || '-';
                })()}
              </Typography>

              <Divider sx={{ my: 0.5 }} />

              {pointEditMode ? (
                <>
                  <TextField
                    size="small"
                    label="PORT P/P"
                    placeholder="Введите розетку, чтобы найти PORT"
                    value={selectedPointSocketInput}
                    onChange={(event) => setSelectedPointSocketInput(event.target.value)}
                    helperText={selectedPointSocketInput
                      ? (selectedPointSocketMatches.length === 1
                        ? 'Найден 1 PORT и подставлен автоматически'
                        : selectedPointSocketMatches.length > 1
                          ? `Найдено ${selectedPointSocketMatches.length} портов, выберите нужный PORT`
                          : 'Совпадений не найдено')
                      : 'дентичность точки определяется PORT P/P'}
                  />
                  <TextField
                    select
                    size="small"
                    label="PORT для точки"
                    value={selectedPointPortValue}
                    onChange={(event) => {
                      const nextPortId = Number(event.target.value) || null;
                      const nextPort = selectedPointPortOptions.find((port) => Number(port.id) === Number(nextPortId)) || null;
                      setMapPoints((prev) =>
                        prev.map((p) => (p.id === selectedPoint.id
                          ? {
                            ...p,
                            port_id: nextPortId,
                            port_name: nextPort?.port_name || '',
                            patch_panel_port: nextPort?.patch_panel_port || '',
                            port_location_code: nextPort?.location_code || '',
                            endpoint_ip_raw: nextPort?.endpoint_ip_raw || '',
                            endpoint_mac_raw: nextPort?.endpoint_mac_raw || '',
                          }
                          : p))
                      );
                      if (nextPort?.patch_panel_port) {
                        setSelectedPointSocketInput(String(nextPort.patch_panel_port));
                      }
                    }}
                    helperText="дентичность точки задается PORT P/P выбранного порта"
                  >
                    {selectedPointPortOptions.map((port) => (
                      <MenuItem key={port.id} value={String(port.id)}>
                        {formatSocketPort(port)}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField size="small" label="Название точки" value={selectedPoint.label || ''} onChange={(event) => setMapPoints((prev) => prev.map((p) => (p.id === selectedPoint.id ? { ...p, label: event.target.value } : p)))} />
                  <TextField size="small" label="Примечание" value={selectedPoint.note || ''} onChange={(event) => setMapPoints((prev) => prev.map((p) => (p.id === selectedPoint.id ? { ...p, note: event.target.value } : p)))} />
                  <TextField size="small" type="color" label="Цвет" value={selectedPoint.color || '#1976d2'} onChange={(event) => setMapPoints((prev) => prev.map((p) => (p.id === selectedPoint.id ? { ...p, color: event.target.value } : p)))} sx={{ width: 140 }} />
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="contained" onClick={() => void saveSelectedPoint()}>Сохранить</Button>
                    <Button size="small" onClick={() => setPointEditMode(false)}>Отмена</Button>
                    <Button size="small" color="error" onClick={() => void removeSelectedPoint()}>Удалить</Button>
                  </Stack>
                </>
              ) : (
                <Stack direction="row" spacing={1}>
                  <Button size="small" variant="outlined" startIcon={<EditIcon />} onClick={() => setPointEditMode(true)}>зменить</Button>
                  <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => void removeSelectedPoint()}>Удалить</Button>
                </Stack>
              )}
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}
    </Stack>
  );

  return (
    <MainLayout>
      <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 110px)' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5} sx={{ mb: 2, flexShrink: 0 }}>
          <Box>
            <Typography variant="h4">Сети</Typography>
            <Typography variant="body2" color="text.secondary">Филиалы, оборудование и карты сети</Typography>
          </Box>
          {canEdit && (
            <Stack direction="row" spacing={1}>
              {!branchIdNum && (
                <Button variant="contained" onClick={() => { setCreateBranchDefaultSiteCode(''); setCreateBranchOpen(true); }}>
                  Создать филиал
                </Button>
              )}

              {branchIdNum && <Button variant="contained" onClick={openMapDialogCreate}>Добавить карту</Button>}
            </Stack>
          )}
        </Stack>

        {!branchIdNum && (
          <>
            <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
              <TextField
                fullWidth
                size="small"
                label="Поиск филиала"
                value={branchSearch}
                onChange={(event) => setBranchSearch(event.target.value)}
              />
            </Paper>

            <BranchList
              branches={filteredBranches}
              canEdit={canEdit}
              onBranchClick={(branch) => navigate(`/networks/${branch.id}`)}
              onEditClick={openEditBranchDialog}
              onDeleteClick={openDeleteBranchDialog}
            />
          </>
        )}

        {branchIdNum && (
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.2} sx={{ mb: 1.5, flexShrink: 0 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <IconButton onClick={() => navigate('/networks')}><ArrowBackIcon /></IconButton>
                <Box>
                  <Typography variant="h6">{selectedBranch?.name || overview?.branch?.name || 'Филиал'}</Typography>
                  <Typography variant="body2" color="text.secondary">{selectedBranch?.branch_code || overview?.branch?.branch_code || '-'}</Typography>
                </Box>
              </Stack>
              <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap" alignItems="center">
                <Chip size="small" label={`Устройства: ${overview?.metrics?.devices_count || 0}`} />
                <Chip size="small" label={`Порты: ${overview?.metrics?.ports_count || 0}`} />
                <Chip size="small" label={`Розетки: ${overview?.metrics?.sockets_count || 0}`} />
                <Chip size="small" label={`Занято: ${overview?.metrics?.occupied_ports || 0}`} />
                <Chip size="small" label={`Карты: ${overview?.metrics?.maps_count || 0}`} />
                {canEdit && (
                  <>
                    <input
                      hidden
                      type="file"
                      accept=".xlsx,.xlsm"
                      ref={equipImportRef}
                      onChange={handleEquipImport}
                    />
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={equipImportLoading}
                      onClick={() => setTimeout(() => equipImportRef.current?.click(), 0)}
                    >
                      {equipImportLoading ? 'мпорт...' : 'мпорт xlsx'}
                    </Button>
                  </>
                )}
              </Stack>
            </Stack>

            <Tabs
              value={tab}
              onChange={(_, value) => setTab(value)}
              sx={{ mb: 1.5, flexShrink: 0 }}
              variant={isMobile ? 'scrollable' : 'standard'}
              allowScrollButtonsMobile
            >
              <Tab value="equipment" label="Оборудование" />
              <Tab value="sockets" label="Розетки" />
              <Tab value="maps" label="Карта" />
              <Tab value="history" label="стория" />
            </Tabs>

            {tab === 'equipment' && (
              <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0 }}>
                <EquipmentTab
                  isMobile={isMobile}
                  canEdit={canEdit}
                  isBranchWidePortSearch={isBranchWidePortSearch}
                  selectedBranch={selectedBranch}
                  devices={devices}
                  devicePortCounts={devicePortCounts}
                  selectedDeviceId={selectedDeviceId}
                  selectedDevice={selectedDevice}
                  matchedDeviceIds={matchedDeviceIds}
                  matchedDevicePortCount={matchedDevicePortCount}
                  portSearch={portSearch}
                  setPortSearch={setPortSearch}
                  displayedPorts={displayedPorts}
                  branchPortLoading={branchPortLoading}
                  editingPortId={editingPortId}
                  portDraft={portDraft}
                  portSaving={portSaving}
                  socketAutocompleteOpen={socketAutocompleteOpen}
                  setSocketAutocompleteOpen={setSocketAutocompleteOpen}
                  socketAutocompleteOptions={socketAutocompleteOptions}
                  socketKey={socketKey}
                  openCreateDeviceDialog={openCreateDeviceDialog}
                  openEditDeviceDialog={openEditDeviceDialog}
                  setSelectedDeviceId={setSelectedDeviceId}
                  setDeviceChipRef={setDeviceChipRef}
                  handlePortRowClick={handlePortRowClick}
                  startEditPort={startEditPort}
                  cancelEditPort={cancelEditPort}
                  updatePortDraftField={updatePortDraftField}
                  savePortEdit={savePortEdit}
                  setSelectedSocketId={setSelectedSocketId}
                />
              </Box>
            )}

            {tab === 'sockets' && (
              <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0 }}>
                <SocketsTab
                  canEdit={canEdit}
                  socketSearch={socketSearch}
                  setSocketSearch={setSocketSearch}
                  filteredSockets={filteredSockets}
                  handleSocketRowClick={handleSocketRowClick}
                  onCreateSocket={openCreateSocketDialog}
                  onDeleteSocket={requestDeleteSocket}
                  deletingSocketId={socketDeleteSaving ? Number(socketDeleteTarget?.id || 0) : null}
                  pointEditMode={pointEditMode}
                />
              </Box>
            )}

            {tab === 'maps' && (
              <>
                <Grid container spacing={1.5}>
                  <Grid item xs={12} lg={9}>
                    {mapIsPdf ? (
                      <Paper variant="outlined" sx={{ p: 2, minHeight: 360 }}>
                        <Typography variant="subtitle1" sx={{ mb: 0.6 }}>Выбрана PDF карта</Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.2 }}>
                          Для интерактивной работы выберите карту-изображение (PNG/JPG).
                        </Typography>
                        <Button variant="contained" startIcon={<DownloadIcon />} onClick={() => mapBlobUrl && window.open(mapBlobUrl, '_blank', 'noopener,noreferrer')}>
                          Открыть PDF
                        </Button>
                      </Paper>
                    ) : (
                      <Stack spacing={1}>
                        {mapRenderedFrom === 'pdf' && (
                          <Alert severity="info">
                            PDF-карта автоматически конвертирована в изображение. нтерактивная разметка включена.
                          </Alert>
                        )}
                        <InteractiveMapCanvas
                          imageUrl={mapBlobUrl}
                          points={pointsForMap}
                          selectedPointId={selectedPointId}
                          focusPointId={focusMapPointId}
                          onPointSelect={onMapPointSelect}
                          onPointDrop={onMapPointDrop}
                          onCanvasClick={onMapClickAddPoint}
                          disabled={!selectedMapId}
                          mobile={isMobile}
                          height={{ xs: isMobile ? 430 : 500, md: 780, lg: 860 }}
                        />
                      </Stack>
                    )}
                    {isMobile && (
                      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                        <Button variant="contained" onClick={() => setMobileMapPanelOpen(true)} fullWidth>
                          Панель карты
                        </Button>
                        <Button variant="outlined" onClick={() => setPointDetailsOpen(true)} disabled={!selectedPoint}>
                          Точка
                        </Button>
                      </Stack>
                    )}
                  </Grid>

                  {!isMobile && (
                    <Grid item xs={12} lg={3}>
                      {mapSidePanelContent}
                    </Grid>
                  )}
                </Grid>
                {isMobile && (
                  <Drawer
                    anchor="bottom"
                    open={mobileMapPanelOpen}
                    onClose={() => setMobileMapPanelOpen(false)}
                    PaperProps={{
                      sx: {
                        borderTopLeftRadius: 16,
                        borderTopRightRadius: 16,
                        maxHeight: '82vh',
                        p: 1.2,
                        overflowY: 'auto',
                      },
                    }}
                  >
                    {mapSidePanelContent}
                  </Drawer>
                )}
              </>
            )}

            {tab === 'history' && (
              <AuditTab audit={audit} />
            )}
          </Paper>
        )}

        {isMobile && (
          <Drawer
            anchor="bottom"
            open={mobilePortEditorOpen && Boolean(editingPort)}
            onClose={cancelEditPort}
            PaperProps={{
              sx: {
                borderTopLeftRadius: 16,
                borderTopRightRadius: 16,
                maxHeight: '80vh',
              },
            }}
          >
            <Stack spacing={1.1} sx={{ p: 2 }}>
              <Typography variant="subtitle1">Редактирование порта</Typography>
              <Typography variant="caption" color="text.secondary">
                {editingPort?.device_code || '-'} · {editingPort?.port_name || '-'}
              </Typography>
              <TextField size="small" label="PORT" value={portDraft?.port_name || ''} onChange={(event) => updatePortDraftField('port_name', event.target.value)} />
              <TextField size="small" label="PORT P/P" value={portDraft?.patch_panel_port || ''} onChange={(event) => updatePortDraftField('patch_panel_port', event.target.value)} />
              <TextField size="small" label="LOCATION" value={portDraft?.location_code || ''} onChange={(event) => updatePortDraftField('location_code', event.target.value)} />
              <TextField size="small" label="VLAN" value={portDraft?.vlan_raw || ''} onChange={(event) => updatePortDraftField('vlan_raw', event.target.value)} />
              <TextField size="small" multiline maxRows={3} label="NAME" value={portDraft?.endpoint_name_raw || ''} onChange={(event) => updatePortDraftField('endpoint_name_raw', event.target.value)} />
              <TextField size="small" multiline minRows={2} maxRows={6} label="IP ADDRESS" value={portDraft?.endpoint_ip_raw || ''} onChange={(event) => updatePortDraftField('endpoint_ip_raw', event.target.value)} />
              <TextField size="small" multiline minRows={2} maxRows={6} label="MAC ADDRESS" helperText="По одному MAC на строку. Допустимы ':' и '-'." value={portDraft?.endpoint_mac_raw || ''} onChange={(event) => updatePortDraftField('endpoint_mac_raw', event.target.value)} />
              <Stack direction="row" spacing={1}>
                <Button
                  variant="contained"
                  disabled={portSaving || !editingPort || !portDraft}
                  onClick={() => {
                    if (!editingPort) return;
                    void savePortEdit(editingPort);
                  }}
                >
                  Сохранить
                </Button>
                <Button variant="outlined" onClick={cancelEditPort}>Отмена</Button>
              </Stack>
            </Stack>
          </Drawer>
        )}

        <MapDialog
          open={mapDialogOpen}
          onClose={() => setMapDialogOpen(false)}
          mapEditId={mapEditId}
          mapFile={mapFile}
          setMapFile={setMapFile}
          mapTitle={mapTitle}
          setMapTitle={setMapTitle}
          mapFloor={mapFloor}
          setMapFloor={setMapFloor}
          mapSiteCode={mapSiteCode}
          setMapSiteCode={setMapSiteCode}
          saveMap={saveMap}
          sites={availableSites}
        />



        <CreateBranchDialog
          open={createBranchOpen}
          onClose={() => setCreateBranchOpen(false)}
          createBranchDbId={createBranchDbId}
          setCreateBranchDbId={setCreateBranchDbId}
          availableDatabases={availableDatabases}
          createBranchName={createBranchName}
          setCreateBranchName={setCreateBranchName}
          createBranchDefaultSiteCode={createBranchDefaultSiteCode}
          createPanelMode={createPanelMode}
          setCreatePanelMode={setCreatePanelMode}
          createPanelCount={createPanelCount}
          setCreatePanelCount={setCreatePanelCount}
          createPortsPerPanel={createPortsPerPanel}
          setCreatePortsPerPanel={setCreatePortsPerPanel}
          createPanels={createPanels}
          addPanel={addPanel}
          removePanel={removePanel}
          updatePanelIndex={updatePanelIndex}
          updatePanelPortCount={updatePanelPortCount}
          createFillMode={createFillMode}
          setCreateFillMode={setCreateFillMode}
          createTemplateFile={createTemplateFile}
          setCreateTemplateFile={setCreateTemplateFile}
          createBranchSaving={createBranchSaving}
          createBranchWithProfile={createBranchWithProfile}
        />

        <EditBranchDialog
          open={branchEditDialogOpen}
          onClose={() => setBranchEditDialogOpen(false)}
          branchEditName={branchEditName}
          setBranchEditName={setBranchEditName}
          branchDefaultSiteCode={branchDefaultSiteCode}
          setBranchDefaultSiteCode={setBranchDefaultSiteCode}
          branchEditDbId={branchEditDbId}
          setBranchEditDbId={setBranchEditDbId}
          branchEditLoading={branchEditLoading}
          availableDatabases={availableDatabases}
          branchEditSaving={branchEditSaving}
          saveBranchEdit={saveBranchEdit}
        />

        <DeleteBranchDialog
          open={branchDeleteDialogOpen}
          onClose={() => setBranchDeleteDialogOpen(false)}
          branchDeleteName={branchDeleteName}
          branchDeleteSaving={branchDeleteSaving}
          confirmDeleteBranch={confirmDeleteBranch}
        />

        <Dialog open={pointDetailsOpen} onClose={() => setPointDetailsOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle>Детали точки карты</DialogTitle>
          <DialogContent>
            {selectedPoint ? (
              <Stack spacing={1} sx={{ mt: 0.5 }}>
                {selectedCluster && selectedCluster.length > 1 && (
                  <Stack direction="row" spacing={0.5} sx={{ mb: 1, flexWrap: 'wrap', gap: 0.5 }}>
                    {selectedCluster.map((p) => {
                      const isSelf = Number(p.id) === Number(selectedPoint.id);
                      const label = String(p.patch_panel_port || p.device_code || p.id);
                      return (
                        <Chip
                          key={p.id}
                          label={label}
                          size="small"
                          color={isSelf ? 'primary' : 'default'}
                          onClick={() => setSelectedPointId(Number(p.id))}
                          sx={{ cursor: 'pointer', height: 24, fontSize: '0.75rem' }}
                        />
                      );
                    })}
                  </Stack>
                )}
                <Typography variant="caption" color="text.secondary">
                  {formatSocketPort(selectedPoint)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  📡 {selectedPoint.device_code || '-'}{selectedPoint.device_model ? ` · ${selectedPoint.device_model}` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  📍 {selectedPoint.port_location_code || '-'} · 🌐 {selectedPoint.endpoint_ip_raw || '-'} · 💻 {selectedPoint.endpoint_mac_raw || '-'}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem', lineHeight: 1.2 }}>
                  👤 {(() => {
                    const pId = Number(selectedPoint.port_id || 0);
                    const sId = Number(selectedPoint.socket_id || 0);
                    let foundFio = selectedPoint.fio;
                    if (!foundFio && pId) {
                      const port = allPortsWithSocket?.find(p => Number(p.id) === pId);
                      if (port?.fio) foundFio = port.fio;
                    }
                    if (!foundFio && sId) {
                      const sock = sockets?.find(s => Number(s.id) === sId);
                      if (sock?.fio) foundFio = sock.fio;
                    }
                    return foundFio || '-';
                  })()}
                </Typography>

                <Divider sx={{ my: 0.5 }} />

                {pointEditMode ? (
                  <>
                    <TextField
                      size="small"
                      label="PORT P/P"
                      placeholder="Введите розетку, чтобы найти PORT"
                      value={selectedPointSocketInput}
                      onChange={(event) => setSelectedPointSocketInput(event.target.value)}
                      helperText={selectedPointSocketInput
                        ? (selectedPointSocketMatches.length === 1
                          ? 'Найден 1 PORT и подставлен автоматически'
                          : selectedPointSocketMatches.length > 1
                            ? `Найдено ${selectedPointSocketMatches.length} портов, выберите нужный PORT`
                            : 'Совпадений не найдено')
                        : 'дентичность точки определяется PORT P/P'}
                    />
                    <TextField
                      select
                      size="small"
                      label="PORT для точки"
                      value={selectedPointPortValue}
                      onChange={(event) => {
                        const nextPortId = Number(event.target.value) || null;
                        const nextPort = selectedPointPortOptions.find((port) => Number(port.id) === Number(nextPortId)) || null;
                        setMapPoints((prev) =>
                          prev.map((p) => (p.id === selectedPoint.id
                            ? {
                              ...p,
                              port_id: nextPortId,
                              port_name: nextPort?.port_name || '',
                              patch_panel_port: nextPort?.patch_panel_port || '',
                              port_location_code: nextPort?.location_code || '',
                              endpoint_ip_raw: nextPort?.endpoint_ip_raw || '',
                              endpoint_mac_raw: nextPort?.endpoint_mac_raw || '',
                            }
                            : p))
                        );
                        if (nextPort?.patch_panel_port) {
                          setSelectedPointSocketInput(String(nextPort.patch_panel_port));
                        }
                      }}
                      helperText="дентичность точки задается PORT P/P выбранного порта"
                    >
                      {selectedPointPortOptions.map((port) => (
                        <MenuItem key={port.id} value={String(port.id)}>
                          {formatSocketPort(port)}
                        </MenuItem>
                      ))}
                    </TextField>
                    <TextField size="small" label="Название точки" value={selectedPoint.label || ''} onChange={(event) => setMapPoints((prev) => prev.map((p) => (p.id === selectedPoint.id ? { ...p, label: event.target.value } : p)))} />
                    <TextField size="small" label="Примечание" value={selectedPoint.note || ''} onChange={(event) => setMapPoints((prev) => prev.map((p) => (p.id === selectedPoint.id ? { ...p, note: event.target.value } : p)))} />
                    <TextField size="small" type="color" label="Цвет" value={selectedPoint.color || '#1976d2'} onChange={(event) => setMapPoints((prev) => prev.map((p) => (p.id === selectedPoint.id ? { ...p, color: event.target.value } : p)))} sx={{ width: 140 }} />
                    <Stack direction="row" spacing={1}>
                      <Button size="small" variant="contained" onClick={() => void saveSelectedPoint()}>Сохранить</Button>
                      <Button size="small" onClick={() => setPointEditMode(false)}>Отмена</Button>
                      <Button size="small" color="error" onClick={() => void removeSelectedPoint()}>Удалить</Button>
                    </Stack>
                  </>
                ) : (
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" startIcon={<EditIcon />} onClick={() => setPointEditMode(true)}>зменить</Button>
                    <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => void removeSelectedPoint()}>Удалить</Button>
                  </Stack>
                )}
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Выберите точку на карте, чтобы увидеть информацию.
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPointDetailsOpen(false)}>Закрыть</Button>
          </DialogActions>
        </Dialog>

        <Dialog open={socketCreateOpen} onClose={closeCreateSocketDialog} maxWidth="sm" fullWidth>
          <DialogTitle>Добавить розетку</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={1.2} sx={{ mt: 0.5 }}>
              <TextField
                size="small"
                label="Код розетки (PORT P/P)"
                placeholder="Например: 4-204"
                required
                value={socketCreateCode}
                onChange={(event) => setSocketCreateCode(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    if (!socketCreateSaving) void createSocket();
                  }
                }}
              />
              <TextField
                size="small"
                label="MAC (опционально)"
                value={socketCreateMac}
                onChange={(event) => setSocketCreateMac(event.target.value)}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={closeCreateSocketDialog} disabled={socketCreateSaving}>Отмена</Button>
            <Button
              variant="contained"
              onClick={() => void createSocket()}
              disabled={socketCreateSaving || !String(socketCreateCode || '').trim()}
            >
              Добавить
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog open={socketDeleteOpen} onClose={closeDeleteSocketDialog} maxWidth="xs" fullWidth>
          <DialogTitle>Удалить розетку</DialogTitle>
          <DialogContent dividers>
            <Typography variant="body2">
              Удалить розетку <strong>{socketDeleteTarget?.socket_code || '-'}</strong>?
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.7, display: 'block' }}>
              Связи с портом и точкой карты будут сняты автоматически.
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={closeDeleteSocketDialog} disabled={socketDeleteSaving}>Отмена</Button>
            <Button color="error" variant="contained" onClick={() => void confirmDeleteSocket()} disabled={socketDeleteSaving}>
              Удалить
            </Button>
          </DialogActions>
        </Dialog>

        <DeviceDialog
          open={deviceDialogOpen}
          onClose={() => setDeviceDialogOpen(false)}
          deviceEditId={deviceEditId}
          deviceCode={deviceCode}
          setDeviceCode={setDeviceCode}
          deviceType={deviceType}
          setDeviceType={setDeviceType}
          deviceSiteCode={deviceSiteCode}
          setDeviceSiteCode={setDeviceSiteCode}
          deviceVendor={deviceVendor}
          setDeviceVendor={setDeviceVendor}
          deviceModel={deviceModel}
          setDeviceModel={setDeviceModel}
          deviceMgmtIp={deviceMgmtIp}
          setDeviceMgmtIp={setDeviceMgmtIp}
          deviceSheetName={deviceSheetName}
          setDeviceSheetName={setDeviceSheetName}
          deviceNotes={deviceNotes}
          setDeviceNotes={setDeviceNotes}
          devicePortCount={devicePortCount}
          setDevicePortCount={setDevicePortCount}
          deviceSaving={deviceSaving}
          saveDevice={saveDevice}
          deviceDeleting={deviceDeleting}
          deleteDevice={deleteDevice}
        />

        {loading && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Загрузка...</Typography>}

        <Snackbar
          open={Boolean(activeToast)}
          autoHideDuration={4500}
          onClose={closeToast}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        >
          <Alert
            onClose={closeToast}
            severity={activeToast?.severity || 'info'}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {activeToast?.message || ''}
          </Alert>
        </Snackbar>
      </Box>
    </MainLayout>
  );
}

export default Networks;

