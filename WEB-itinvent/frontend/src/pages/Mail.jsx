import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  InputLabel,
  List,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Skeleton,
  Snackbar,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
  Autocomplete,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import RefreshIcon from '@mui/icons-material/Refresh';
import EmailIcon from '@mui/icons-material/Email';
import DraftsIcon from '@mui/icons-material/Drafts';
import AssignmentIcon from '@mui/icons-material/Assignment';
import SettingsSuggestIcon from '@mui/icons-material/SettingsSuggest';
import SearchIcon from '@mui/icons-material/Search';
import InboxIcon from '@mui/icons-material/Inbox';
import SendIcon from '@mui/icons-material/Send';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import FolderIcon from '@mui/icons-material/Folder';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import DeleteIcon from '@mui/icons-material/Delete';
import DownloadIcon from '@mui/icons-material/Download';
import PersonIcon from '@mui/icons-material/Person';
import ReactQuill from 'react-quill';
import DOMPurify from 'dompurify';
import { useTheme } from '@mui/material/styles';
import 'react-quill/dist/quill.snow.css';
import MainLayout from '../components/layout/MainLayout';
import { mailAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import useDebounce from '../hooks/useDebounce';

const POLL_INTERVAL_MS = 15_000;
const MAX_PREVIEW_FILE_BYTES = 25 * 1024 * 1024;
const COMPOSE_DRAFT_STORAGE_KEY = 'mail_compose_draft_v1';
const IT_DRAFT_STORAGE_KEY = 'mail_it_request_draft_v1';

const FOLDER_ICONS = {
  inbox: <InboxIcon fontSize="small" />,
  sent: <SendIcon fontSize="small" />,
  drafts: <FolderIcon fontSize="small" />,
  trash: <DeleteOutlineIcon fontSize="small" />,
};

const FOLDER_LABELS = {
  inbox: 'Входящие',
  sent: 'Отправленные',
  drafts: 'Черновики',
  trash: 'Удалённые',
};

const replaceTemplateVars = (text, values) => {
  const source = String(text || '');
  return source.replace(/\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}/g, (_, key) => String(values?.[key] || ''));
};

const TEMPLATE_FIELD_TYPES = [
  { value: 'text', label: 'Текст' },
  { value: 'textarea', label: 'Многострочный текст' },
  { value: 'select', label: 'Список (один вариант)' },
  { value: 'multiselect', label: 'Список (несколько вариантов)' },
  { value: 'date', label: 'Дата' },
  { value: 'checkbox', label: 'Флажок' },
  { value: 'email', label: 'Email' },
  { value: 'tel', label: 'Телефон' },
];

const DEFAULT_TEMPLATE_FIELD = {
  key: '',
  label: '',
  type: 'text',
  required: true,
  placeholder: '',
  help_text: '',
  default_value: '',
  options: [],
  order: 0,
};

const normalizeFieldKey = (value, fallback = '') => {
  const raw = String(value || fallback || '').trim().toLowerCase();
  return raw
    .replace(/[^a-z0-9_.-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
};

const normalizeFieldOptions = (value) => {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === 'object') return String(item.value || item.label || '').trim();
        return String(item || '').trim();
      })
      .filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(/[\n;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
};

const createTemplateField = (index = 0) => ({
  ...DEFAULT_TEMPLATE_FIELD,
  key: `field_${index + 1}`,
  label: `Поле ${index + 1}`,
  order: index,
});

const normalizeTemplateFields = (rawFields) => {
  if (!Array.isArray(rawFields)) return [];
  const allowed = new Set(TEMPLATE_FIELD_TYPES.map((item) => item.value));
  return rawFields
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => {
      const field = { ...DEFAULT_TEMPLATE_FIELD, ...item };
      const type = allowed.has(String(field.type || '').trim()) ? String(field.type).trim() : 'text';
      const options = normalizeFieldOptions(field.options);
      let defaultValue = field.default_value ?? '';
      if (type === 'checkbox') {
        defaultValue = Boolean(defaultValue);
      } else if (type === 'multiselect') {
        defaultValue = Array.isArray(defaultValue) ? defaultValue.map((opt) => String(opt || '').trim()).filter(Boolean) : [];
      } else {
        defaultValue = String(defaultValue || '').trim();
      }
      return {
        key: normalizeFieldKey(field.key, `field_${index + 1}`),
        label: String(field.label || '').trim() || `Поле ${index + 1}`,
        type,
        required: Boolean(field.required ?? true),
        placeholder: String(field.placeholder || '').trim(),
        help_text: String(field.help_text || '').trim(),
        default_value: defaultValue,
        options: ['select', 'multiselect'].includes(type) ? options : [],
        order: Number.isFinite(Number(field.order)) ? Number(field.order) : index,
      };
    })
    .sort((a, b) => a.order - b.order)
    .map((item, index) => ({ ...item, order: index }));
};

const buildInitialFieldValues = (template) => {
  const fields = normalizeTemplateFields(template?.fields);
  const values = {};
  fields.forEach((field) => {
    if (field.type === 'checkbox') {
      values[field.key] = Boolean(field.default_value);
      return;
    }
    if (field.type === 'multiselect') {
      values[field.key] = Array.isArray(field.default_value) ? field.default_value : [];
      return;
    }
    values[field.key] = String(field.default_value || '');
  });
  return values;
};

const toPreviewText = (value) => {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  return String(value || '');
};

const getInitials = (email) => {
  if (!email) return '?';
  const name = email.split('@')[0] || '';
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.substring(0, 2).toUpperCase();
};

const getAvatarColor = (email) => {
  const colors = [
    '#1976d2', '#388e3c', '#d32f2f', '#7b1fa2',
    '#f57c00', '#0097a7', '#5d4037', '#455a64',
    '#c2185b', '#00796b', '#e64a19', '#512da8',
  ];
  let hash = 0;
  for (let i = 0; i < (email || '').length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};

const formatTime = (isoStr) => {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  if (isToday) return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return 'Вчера';
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
};

const formatFullDate = (isoStr) => {
  if (!isoStr) return '-';
  return new Date(isoStr).toLocaleString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
};

const formatFileSize = (bytes) => {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return '0 Б';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  if (unitIndex === 0) {
    return `${Math.round(size)} ${units[unitIndex]}`;
  }
  const fractionDigits = size >= 10 ? 0 : 1;
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: fractionDigits }).format(size)} ${units[unitIndex]}`;
};

const sumFilesSize = (files) => {
  if (!Array.isArray(files)) return 0;
  return files.reduce((acc, file) => acc + Number(file?.size || 0), 0);
};

const sumAttachmentSize = (attachments) => {
  if (!Array.isArray(attachments)) return 0;
  return attachments.reduce((acc, attachment) => acc + Number(attachment?.size || 0), 0);
};

const MAX_TEXT_PREVIEW_BYTES = 1024 * 1024;

const getFileExtension = (filename) => {
  const value = String(filename || '').toLowerCase();
  const index = value.lastIndexOf('.');
  if (index < 0) return '';
  return value.slice(index + 1);
};

const resolveAttachmentPreviewKind = ({ contentType, filename }) => {
  const type = String(contentType || '').toLowerCase();
  const ext = getFileExtension(filename);
  const imageExt = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']);
  const textExt = new Set(['txt', 'log', 'csv', 'json', 'xml', 'md', 'ini', 'conf', 'yml', 'yaml', 'ps1', 'js', 'ts', 'py', 'java', 'c', 'cpp', 'cs', 'sql']);

  if (type.includes('pdf') || ext === 'pdf') return 'pdf';
  if (type.startsWith('image/') || imageExt.has(ext)) return 'image';
  if (type.startsWith('text/') || type.includes('json') || type.includes('xml') || textExt.has(ext)) return 'text';
  return 'unsupported';
};

const downloadBlobFile = (blob, filename) => {
  if (!blob) return;
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = String(filename || 'attachment.bin');
  document.body.appendChild(link);
  link.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(link);
};

const extractRequestErrorDetail = async (requestError, fallbackText) => {
  let detail = String(fallbackText || 'Ошибка запроса.');
  const payload = requestError?.response?.data;
  if (payload instanceof Blob) {
    try {
      const rawText = (await payload.text()).trim();
      if (rawText) {
        try {
          const parsed = JSON.parse(rawText);
          detail = parsed?.detail ? String(parsed.detail) : rawText;
        } catch {
          detail = rawText;
        }
      }
    } catch {
      // Keep fallback text.
    }
    return detail;
  }
  if (payload?.detail) return String(payload.detail);
  return detail;
};

const createEmptyAttachmentPreview = () => ({
  open: false,
  loading: false,
  error: '',
  filename: '',
  contentType: '',
  kind: 'unsupported',
  objectUrl: '',
  textContent: '',
  textTruncated: false,
  tooLargeForPreview: false,
  blob: null,
});

const escapeHtml = (value) => String(value || '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const isUnsafeUri = (rawValue) => {
  const value = String(rawValue || '').trim().replace(/\s+/g, '');
  if (!value) return false;
  if (/^javascript:/i.test(value)) return true;
  if (/^data:(?!image\/)/i.test(value)) return true;
  return false;
};

const sanitizeIncomingMailHtml = (html) => {
  const source = String(html || '');
  if (!source) return '';
  try {
    const sanitized = DOMPurify.sanitize(source, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'link', 'meta', 'base'],
      FORBID_ATTR: ['style'],
      ALLOW_DATA_ATTR: false,
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|cid):|data:image\/(?:bmp|gif|jpeg|jpg|png|svg\+xml|webp);base64,|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
    });
    if (typeof DOMParser === 'undefined') return sanitized;
    const parser = new DOMParser();
    const doc = parser.parseFromString(String(sanitized || ''), 'text/html');
    const elements = Array.from(doc.body.querySelectorAll('*'));
    elements.forEach((element) => {
      const href = element.getAttribute('href');
      const src = element.getAttribute('src');
      const xlinkHref = element.getAttribute('xlink:href');
      if (isUnsafeUri(href)) element.removeAttribute('href');
      if (isUnsafeUri(src)) element.removeAttribute('src');
      if (isUnsafeUri(xlinkHref)) element.removeAttribute('xlink:href');
    });
    return doc.body.innerHTML || '';
  } catch {
    return `<pre>${escapeHtml(source)}</pre>`;
  }
};

const parseDownloadFilename = (contentDisposition, fallbackName = 'attachment.bin') => {
  const fallback = String(fallbackName || 'attachment.bin');
  const raw = String(contentDisposition || '');
  if (!raw) return fallback;

  const starMatch = raw.match(/filename\*\s*=\s*([^;]+)/i);
  if (starMatch?.[1]) {
    let value = starMatch[1].trim().replace(/^"(.*)"$/, '$1');
    value = value.replace(/^UTF-8''/i, '');
    try {
      const decoded = decodeURIComponent(value);
      if (decoded) return decoded;
    } catch {
      // Fallback to simple filename parsing below.
    }
  }

  const simpleMatch = raw.match(/filename\s*=\s*"([^"]+)"/i) || raw.match(/filename\s*=\s*([^;]+)/i);
  if (simpleMatch?.[1]) {
    const value = simpleMatch[1].trim().replace(/^"(.*)"$/, '$1');
    if (value) return value;
  }

  return fallback;
};

const NAMED_COLORS = {
  black: { r: 0, g: 0, b: 0 },
  white: { r: 255, g: 255, b: 255 },
};

const parseCssColorToRgb = (colorStr) => {
  const value = String(colorStr || '').trim().toLowerCase();
  if (!value || value === 'inherit' || value === 'transparent') return null;
  if (NAMED_COLORS[value]) return NAMED_COLORS[value];

  const hexMatch = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = hexMatch[1];
    if (hex.length === 3) {
      return {
        r: parseInt(hex[0] + hex[0], 16),
        g: parseInt(hex[1] + hex[1], 16),
        b: parseInt(hex[2] + hex[2], 16),
      };
    }
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
    };
  }

  const rgbMatch = value.match(/^rgba?\(\s*([0-9.]+)\s*[, ]\s*([0-9.]+)\s*[, ]\s*([0-9.]+)/i);
  if (rgbMatch) {
    return {
      r: Math.max(0, Math.min(255, Number(rgbMatch[1]))),
      g: Math.max(0, Math.min(255, Number(rgbMatch[2]))),
      b: Math.max(0, Math.min(255, Number(rgbMatch[3]))),
    };
  }

  return null;
};

const relativeLuminance = (rgb) => {
  if (!rgb) return null;
  const channels = [rgb.r, rgb.g, rgb.b].map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
};

const isDarkColor = (rgb, threshold = 0.42) => {
  const luminance = relativeLuminance(rgb);
  if (luminance === null) return false;
  return luminance < threshold;
};

const isLightColor = (rgb, threshold = 0.72) => {
  const luminance = relativeLuminance(rgb);
  if (luminance === null) return false;
  return luminance > threshold;
};

const extractElementTextColor = (element) => {
  if (!element) return null;
  const inlineColor = element.style?.color;
  const attrColor = element.getAttribute?.('color');
  return parseCssColorToRgb(inlineColor || attrColor || '');
};

const extractElementBgColor = (element) => {
  if (!element) return null;
  const inlineBg = element.style?.backgroundColor;
  const attrBg = element.getAttribute?.('bgcolor');
  return parseCssColorToRgb(inlineBg || attrBg || '');
};

const getContextBackgroundColor = (element) => {
  let current = element;
  while (current && current.nodeType === 1) {
    const bg = extractElementBgColor(current);
    if (bg) return bg;
    current = current.parentElement;
  }
  return null;
};

const normalizeIncomingMailHtmlForDarkMode = (html, palette) => {
  const source = String(html || '');
  if (!source) return source;
  if (typeof DOMParser === 'undefined') return source;

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(source, 'text/html');
    const contrastText = String(palette?.text?.primary || '#e6edf3');
    const contrastLink = String(palette?.primary?.light || '#90caf9');
    const elements = Array.from(doc.body.querySelectorAll('*'));

    elements.forEach((element) => {
      const tag = String(element.tagName || '').toUpperCase();
      if (tag === 'SCRIPT' || tag === 'STYLE') return;

      const bgColor = getContextBackgroundColor(element);
      const bgIsLight = bgColor ? isLightColor(bgColor) : false;
      const textColor = extractElementTextColor(element);

      if (textColor && isDarkColor(textColor) && !bgIsLight) {
        element.style.color = contrastText;
      }

      if (tag === 'A') {
        const linkColor = extractElementTextColor(element);
        if (linkColor && isDarkColor(linkColor) && !bgIsLight) {
          element.style.color = contrastLink;
        }
      }
    });

    return doc.body.innerHTML || source;
  } catch {
    return source;
  }
};

/* ──────────────────── styles ──────────────────── */

const sidebarSx = {
  height: 'calc(100vh - 220px)',
  minHeight: 500,
  display: 'flex',
  flexDirection: 'column',
  borderRadius: '12px',
  overflow: 'hidden',
  border: '1px solid',
  borderColor: 'divider',
  bgcolor: 'background.paper',
};

const previewPaneSx = {
  height: 'calc(100vh - 220px)',
  minHeight: 500,
  display: 'flex',
  flexDirection: 'column',
  borderRadius: '12px',
  overflow: 'hidden',
  border: '1px solid',
  borderColor: 'divider',
  bgcolor: 'background.paper',
};

const htmlBodySx = {
  flex: 1,
  overflow: 'auto',
  px: 3,
  py: 2,
  '& p': { margin: '0 !important' },
  '& p:last-child': { marginBottom: '0 !important' },
  '& div': { margin: '0 !important' },
  '& ul, & ol': { margin: '0.35em 0 0.35em 1.2em', padding: 0 },
  '& li': { margin: 0 },
  '& img': { maxWidth: '100%', height: 'auto' },
  '& table': { borderCollapse: 'collapse', maxWidth: '100%' },
  '& td, & th': { padding: '4px 8px' },
  '& a': { color: 'primary.main', wordBreak: 'break-all' },
  '& pre, & code': {
    bgcolor: 'action.hover',
    borderRadius: 1,
    p: 0.5,
    fontSize: '0.85em',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  fontSize: '0.9rem',
  lineHeight: 1.35,
  fontFamily: '"Segoe UI", Roboto, Arial, sans-serif',
  color: 'text.primary',
};

/* ──────────────────── component ──────────────────── */

function Mail() {
  const theme = useTheme();
  const { hasPermission } = useAuth();
  const canManageUsers = hasPermission('settings.users.manage');

  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [folder, setFolder] = useState('inbox');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 600);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [mailboxInfo, setMailboxInfo] = useState(null);

  const [listData, setListData] = useState({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
    search_limited: false,
    searched_window: 0,
  });
  const [selectedId, setSelectedId] = useState('');
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [attachmentPreview, setAttachmentPreview] = useState(createEmptyAttachmentPreview);

  const [composeOpen, setComposeOpen] = useState(false);
  const [composeSending, setComposeSending] = useState(false);
  const [signatureOpen, setSignatureOpen] = useState(false);
  const [signatureSaving, setSignatureSaving] = useState(false);
  const [signatureHtml, setSignatureHtml] = useState('');
  const [composeToOptions, setComposeToOptions] = useState([]);
  const [composeToValues, setComposeToValues] = useState([]);
  const [composeToSearch, setComposeToSearch] = useState('');
  const [composeToLoading, setComposeToLoading] = useState(false);
  const debouncedComposeToSearch = useDebounce(composeToSearch, 500);
  const [composeSubject, setComposeSubject] = useState('');
  const [composeBody, setComposeBody] = useState('');
  const [composeFiles, setComposeFiles] = useState([]);
  const [composeUploadProgress, setComposeUploadProgress] = useState(0);

  const [templates, setTemplates] = useState([]);
  const [itOpen, setItOpen] = useState(false);
  const [itSending, setItSending] = useState(false);
  const [itTemplateId, setItTemplateId] = useState('');
  const [itFieldValues, setItFieldValues] = useState({});
  const [itFieldErrors, setItFieldErrors] = useState({});
  const [itFiles, setItFiles] = useState([]);
  const [itUploadProgress, setItUploadProgress] = useState(0);

  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [templateDeleting, setTemplateDeleting] = useState(false);
  const [templateEditId, setTemplateEditId] = useState('');
  const [templateCode, setTemplateCode] = useState('');
  const [templateTitle, setTemplateTitle] = useState('');
  const [templateCategory, setTemplateCategory] = useState('');
  const [templateSubject, setTemplateSubject] = useState('');
  const [templateBody, setTemplateBody] = useState('');
  const [templateFields, setTemplateFields] = useState([createTemplateField(0)]);
  const composeUploadAbortRef = useRef(null);
  const itUploadAbortRef = useRef(null);

  const activeTemplate = useMemo(() => {
    if (!itTemplateId) return null;
    return templates.find((item) => String(item.id) === String(itTemplateId)) || null;
  }, [templates, itTemplateId]);
  const composeDraftKey = useMemo(() => {
    const mailbox = String(mailboxInfo?.mailbox_email || 'default').toLowerCase();
    return `${COMPOSE_DRAFT_STORAGE_KEY}:${mailbox}`;
  }, [mailboxInfo?.mailbox_email]);
  const itDraftKey = useMemo(() => {
    const mailbox = String(mailboxInfo?.mailbox_email || 'default').toLowerCase();
    return `${IT_DRAFT_STORAGE_KEY}:${mailbox}`;
  }, [mailboxInfo?.mailbox_email]);

  const refreshConfig = useCallback(async () => {
    try {
      const data = await mailAPI.getMyConfig();
      setMailboxInfo(data || null);
    } catch (requestError) {
      setMailboxInfo(null);
      setError(requestError?.response?.data?.detail || 'Не удалось загрузить почтовую конфигурацию.');
    }
  }, []);

  const refreshTemplates = useCallback(async () => {
    try {
      const data = await mailAPI.getTemplates();
      const items = Array.isArray(data?.items) ? data.items : [];
      setTemplates(
        items.map((item) => ({
          ...item,
          fields: normalizeTemplateFields(item?.fields),
        }))
      );
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Не удалось загрузить шаблоны IT-заявок.');
    }
  }, []);

  const refreshInbox = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError('');
    }
    try {
      const data = await mailAPI.getInbox({
        folder,
        q: debouncedSearch || undefined,
        unread_only: unreadOnly || undefined,
        limit: 50,
        offset: 0,
      });
      const items = Array.isArray(data?.items) ? data.items : [];
      setListData({
        items,
        total: Number(data?.total || items.length || 0),
        limit: Number(data?.limit || 50),
        offset: Number(data?.offset || 0),
        search_limited: Boolean(data?.search_limited),
        searched_window: Number(data?.searched_window || 0),
      });
      if (items.length === 0) {
        setSelectedId('');
        setSelectedMessage(null);
      }
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось загрузить список писем.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [folder, debouncedSearch, unreadOnly]);

  useEffect(() => {
    refreshConfig();
    refreshTemplates();
  }, [refreshConfig, refreshTemplates]);

  // Эффект для вызова поиска GAL при вводе в автодополнение
  useEffect(() => {
    const query = (debouncedComposeToSearch || '').trim();
    if (query.length < 2) {
      setComposeToOptions([]);
      return;
    }

    let active = true;
    setComposeToLoading(true);

    mailAPI.searchContacts(query).then((items) => {
      if (active) {
        setComposeToOptions(items || []);
      }
    }).catch(console.error).finally(() => {
      if (active) setComposeToLoading(false);
    });

    return () => { active = false; };
  }, [debouncedComposeToSearch]);

  useEffect(() => {
    refreshInbox();

    const handleMailRefresh = () => {
      refreshInbox({ silent: true });
    };

    window.addEventListener('mail-needs-refresh', handleMailRefresh);

    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') {
        refreshInbox({ silent: true });
      }
    }, POLL_INTERVAL_MS);

    return () => {
      window.removeEventListener('mail-needs-refresh', handleMailRefresh);
      clearInterval(timer);
    };
  }, [refreshInbox]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    const loadDetails = async () => {
      setDetailLoading(true);
      try {
        const data = await mailAPI.getMessage(selectedId);
        if (!cancelled) {
          setSelectedMessage(data || null);

          // Автоматическая отметка прочитанным
          if (data && !data.is_read) {
            try {
              await mailAPI.markAsRead(selectedId);
              setListData(prev => ({
                ...prev,
                items: prev.items.map(item => String(item.id) === String(selectedId) ? { ...item, is_read: true } : item)
              }));
              setSelectedMessage(prev => prev ? { ...prev, is_read: true } : prev);

              // Обновляем событие, чтобы MainLayout тоже узнал об этом (через CustomEvent)
              window.dispatchEvent(new Event('mail-read'));
            } catch (err) {
              console.error('Failed to mark as read:', err);
            }
          }
        }
      } catch (requestError) {
        if (!cancelled) {
          setSelectedMessage(null);
          setError(requestError?.response?.data?.detail || 'Не удалось загрузить письмо.');
        }
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };
    loadDetails();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    return () => {
      if (attachmentPreview?.objectUrl) {
        window.URL.revokeObjectURL(attachmentPreview.objectUrl);
      }
      if (composeUploadAbortRef.current) {
        composeUploadAbortRef.current.abort();
      }
      if (itUploadAbortRef.current) {
        itUploadAbortRef.current.abort();
      }
    };
  }, [attachmentPreview?.objectUrl]);

  useEffect(() => {
    if (!composeOpen) return;
    try {
      const raw = window.localStorage.getItem(composeDraftKey);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      const draftTo = Array.isArray(parsed?.to) ? parsed.to.map((item) => String(item || '').trim()).filter(Boolean) : [];
      setComposeToValues(draftTo);
      setComposeSubject(String(parsed?.subject || ''));
      setComposeBody(String(parsed?.body || ''));
    } catch {
      // Ignore broken draft payload.
    }
  }, [composeOpen, composeDraftKey]);

  useEffect(() => {
    if (!composeOpen) return;
    const payload = {
      to: composeToValues.map((item) => {
        if (typeof item === 'string') return item;
        return String(item?.email || item?.name || '').trim();
      }).filter(Boolean),
      subject: String(composeSubject || ''),
      body: String(composeBody || ''),
      updated_at: Date.now(),
    };
    try {
      window.localStorage.setItem(composeDraftKey, JSON.stringify(payload));
    } catch {
      // Ignore storage errors.
    }
  }, [composeOpen, composeToValues, composeSubject, composeBody, composeDraftKey]);

  useEffect(() => {
    if (!itOpen) return;
    try {
      const raw = window.localStorage.getItem(itDraftKey);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      const nextTemplateId = String(parsed?.template_id || '');
      if (nextTemplateId) {
        const hasTemplate = templates.some((item) => String(item.id) === nextTemplateId);
        if (hasTemplate) {
          setItTemplateId(nextTemplateId);
        }
      }
      if (parsed?.fields && typeof parsed.fields === 'object') {
        setItFieldValues(parsed.fields);
      }
    } catch {
      // Ignore broken draft payload.
    }
  }, [itOpen, itDraftKey, templates]);

  useEffect(() => {
    if (!itOpen || !itTemplateId) return;
    const payload = {
      template_id: itTemplateId,
      fields: itFieldValues || {},
      updated_at: Date.now(),
    };
    try {
      window.localStorage.setItem(itDraftKey, JSON.stringify(payload));
    } catch {
      // Ignore storage errors.
    }
  }, [itOpen, itTemplateId, itFieldValues, itDraftKey]);

  const openCompose = useCallback(() => {
    setComposeToValues([]);
    setComposeSubject('');
    setComposeBody('');
    setComposeFiles([]);
    setComposeUploadProgress(0);
    setComposeOpen(true);
  }, []);

  const openSignatureEditor = useCallback(() => {
    setSignatureHtml(String(mailboxInfo?.mail_signature_html || ''));
    setSignatureOpen(true);
  }, [mailboxInfo?.mail_signature_html]);

  const handleSaveSignature = useCallback(async () => {
    setSignatureSaving(true);
    setError('');
    try {
      const payload = { mail_signature_html: String(signatureHtml || '') };
      const data = await mailAPI.updateMyConfig(payload);
      setMailboxInfo(data || null);
      setSignatureOpen(false);
      setMessage('Подпись сохранена.');
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Не удалось сохранить подпись.');
    } finally {
      setSignatureSaving(false);
    }
  }, [signatureHtml]);

  const handleFileChange = useCallback((e) => {
    if (e.target.files && e.target.files.length > 0) {
      setComposeFiles((prev) => [...prev, ...Array.from(e.target.files)]);
    }
    e.target.value = '';
  }, []);

  const removeComposeFile = useCallback((indexToRemove) => {
    setComposeFiles((prev) => prev.filter((_, idx) => idx !== indexToRemove));
  }, []);

  const handleDownloadAttachment = useCallback(async (e, attachment) => {
    e.stopPropagation();
    if (!selectedMessage?.id) return;
    const attachmentRef = attachment?.download_token || attachment?.id;
    if (!attachmentRef) {
      setError('Не удалось скачать файл: идентификатор вложения отсутствует.');
      return;
    }
    try {
      setDetailLoading(true);
      const response = await mailAPI.downloadAttachment(selectedMessage.id, attachmentRef);

      const contentDisposition = response.headers['content-disposition'];
      const filename = parseDownloadFilename(contentDisposition, attachment.name || 'attachment.bin');

      const blob = new Blob([response.data], { type: response.headers['content-type'] });
      downloadBlobFile(blob, filename);
    } catch (requestError) {
      setError(await extractRequestErrorDetail(requestError, 'Не удалось скачать файл.'));
    } finally {
      setDetailLoading(false);
    }
  }, [selectedMessage]);

  const openAttachmentPreview = useCallback(async (e, attachment) => {
    e.stopPropagation();
    if (!selectedMessage?.id) return;
    const attachmentRef = attachment?.download_token || attachment?.id;
    if (!attachmentRef) {
      setError('Не удалось открыть предпросмотр: идентификатор вложения отсутствует.');
      return;
    }

    setAttachmentPreview({
      ...createEmptyAttachmentPreview(),
      open: true,
      loading: true,
      filename: String(attachment?.name || 'attachment.bin'),
    });

    try {
      const response = await mailAPI.downloadAttachment(selectedMessage.id, attachmentRef);
      const contentDisposition = response.headers['content-disposition'];
      const filename = parseDownloadFilename(contentDisposition, attachment.name || 'attachment.bin');
      const contentType = String(response.headers['content-type'] || attachment?.content_type || 'application/octet-stream');
      const blob = new Blob([response.data], { type: contentType });
      const kind = resolveAttachmentPreviewKind({ contentType, filename });
      const tooLargeForPreview = blob.size > MAX_PREVIEW_FILE_BYTES;

      let objectUrl = '';
      let textContent = '';
      let textTruncated = false;

      if (!tooLargeForPreview && (kind === 'pdf' || kind === 'image')) {
        objectUrl = window.URL.createObjectURL(blob);
      } else if (!tooLargeForPreview && kind === 'text') {
        const textChunk = blob.slice(0, MAX_TEXT_PREVIEW_BYTES);
        textContent = await textChunk.text();
        textTruncated = blob.size > MAX_TEXT_PREVIEW_BYTES;
      }

      setAttachmentPreview({
        open: true,
        loading: false,
        error: '',
        filename,
        contentType,
        kind,
        objectUrl,
        textContent,
        textTruncated,
        tooLargeForPreview,
        blob,
      });
    } catch (requestError) {
      const detail = await extractRequestErrorDetail(requestError, 'Не удалось открыть предпросмотр вложения.');
      setAttachmentPreview((prev) => ({
        ...prev,
        loading: false,
        error: detail,
      }));
    }
  }, [selectedMessage]);

  const closeAttachmentPreview = useCallback(() => {
    setAttachmentPreview(createEmptyAttachmentPreview());
  }, []);

  const downloadFromPreview = useCallback(() => {
    if (!attachmentPreview?.blob) return;
    downloadBlobFile(attachmentPreview.blob, attachmentPreview.filename || 'attachment.bin');
  }, [attachmentPreview]);

  const cancelComposeUpload = useCallback(() => {
    if (composeUploadAbortRef.current) {
      composeUploadAbortRef.current.abort();
    }
  }, []);

  const cancelItUpload = useCallback(() => {
    if (itUploadAbortRef.current) {
      itUploadAbortRef.current.abort();
    }
  }, []);

  const clearComposeDraft = useCallback(() => {
    setComposeToValues([]);
    setComposeSubject('');
    setComposeBody('');
    setComposeFiles([]);
    setComposeUploadProgress(0);
    try {
      window.localStorage.removeItem(composeDraftKey);
    } catch {
      // Ignore storage errors.
    }
  }, [composeDraftKey]);

  const clearItDraft = useCallback(() => {
    setItTemplateId('');
    setItFieldValues({});
    setItFieldErrors({});
    setItFiles([]);
    setItUploadProgress(0);
    try {
      window.localStorage.removeItem(itDraftKey);
    } catch {
      // Ignore storage errors.
    }
  }, [itDraftKey]);

  const handleSendCompose = useCallback(async () => {
    const recipients = composeToValues.map(v => typeof v === 'string' ? v : v.email).filter(Boolean);
    if (recipients.length === 0) {
      setError('Укажите хотя бы одного получателя.');
      return;
    }
    setComposeSending(true);
    setComposeUploadProgress(0);
    setError('');
    try {
      if (composeFiles.length > 0) {
        const controller = new AbortController();
        composeUploadAbortRef.current = controller;
        await mailAPI.sendMessageMultipart({
          to: recipients,
          subject: composeSubject,
          body: composeBody,
          isHtml: true,
          files: composeFiles,
          signal: controller.signal,
          onUploadProgress: (event) => {
            const total = Number(event?.total || 0);
            const loaded = Number(event?.loaded || 0);
            if (total > 0) {
              setComposeUploadProgress(Math.max(0, Math.min(100, Math.round((loaded / total) * 100))));
            }
          },
        });
      } else {
        await mailAPI.sendMessage({
          to: recipients,
          subject: composeSubject,
          body: composeBody,
          is_html: true,
        });
      }
      try {
        window.localStorage.removeItem(composeDraftKey);
      } catch {
        // Ignore storage errors.
      }
      setComposeOpen(false);
      setComposeFiles([]);
      setMessage('Письмо отправлено.');
      await refreshInbox({ silent: true });
    } catch (requestError) {
      if (requestError?.code === 'ERR_CANCELED') {
        setError('Отправка письма отменена.');
      } else {
        setError(requestError?.response?.data?.detail || 'Не удалось отправить письмо.');
      }
    } finally {
      composeUploadAbortRef.current = null;
      setComposeUploadProgress(0);
      setComposeSending(false);
    }
  }, [composeToValues, composeSubject, composeBody, composeFiles, composeDraftKey, refreshInbox]);

  const openItRequest = useCallback(() => {
    setItTemplateId('');
    setItFieldValues({});
    setItFieldErrors({});
    setItFiles([]);
    setItUploadProgress(0);
    setItOpen(true);
  }, []);

  const handleItFilesChange = useCallback((event) => {
    if (event.target.files && event.target.files.length > 0) {
      setItFiles((prev) => [...prev, ...Array.from(event.target.files)]);
    }
    event.target.value = '';
  }, []);

  const removeItFile = useCallback((indexToRemove) => {
    setItFiles((prev) => prev.filter((_, idx) => idx !== indexToRemove));
  }, []);

  const handleSendItRequest = useCallback(async () => {
    if (!itTemplateId) {
      setError('Выберите шаблон заявки.');
      return;
    }
    const template = templates.find((item) => String(item.id) === String(itTemplateId));
    if (!template) {
      setError('Шаблон заявки не найден.');
      return;
    }
    const fieldsSchema = normalizeTemplateFields(template?.fields);
    const nextValues = {};
    const nextErrors = {};
    for (const field of fieldsSchema) {
      const key = String(field.key || '');
      if (!key) continue;
      const type = String(field.type || 'text');
      const rawValue = itFieldValues[key] ?? field.default_value;
      let value = rawValue;

      if (type === 'checkbox') {
        value = Boolean(rawValue);
      } else if (type === 'multiselect') {
        value = Array.isArray(rawValue) ? rawValue.map((item) => String(item || '').trim()).filter(Boolean) : [];
        if (Array.isArray(field.options) && field.options.length > 0) {
          value = value.filter((item) => field.options.includes(item));
        }
      } else {
        value = String(rawValue || '').trim();
      }

      const required = Boolean(field.required ?? true);
      if (required) {
        const isMissing = (
          (type === 'checkbox' && value !== true)
          || (type === 'multiselect' && (!Array.isArray(value) || value.length === 0))
          || (!['checkbox', 'multiselect'].includes(type) && !String(value || '').trim())
        );
        if (isMissing) {
          nextErrors[key] = 'Обязательное поле';
        }
      }

      if (!nextErrors[key] && type === 'email' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value))) {
        nextErrors[key] = 'Введите корректный email';
      }
      if (!nextErrors[key] && type === 'tel' && value && !/^[0-9+\-() ]{5,}$/.test(String(value))) {
        nextErrors[key] = 'Введите корректный телефон';
      }
      if (!nextErrors[key] && type === 'date' && value && !/^\d{4}-\d{2}-\d{2}$/.test(String(value))) {
        nextErrors[key] = 'Используйте формат ГГГГ-ММ-ДД';
      }
      if (!nextErrors[key] && type === 'select' && value && Array.isArray(field.options) && field.options.length > 0 && !field.options.includes(value)) {
        nextErrors[key] = 'Выберите значение из списка';
      }

      nextValues[key] = value;
    }

    if (Object.keys(nextErrors).length > 0) {
      setItFieldErrors(nextErrors);
      setError('Заполните обязательные поля заявки корректно.');
      return;
    }

    setItFieldErrors({});
    setItFieldValues(nextValues);
    setItSending(true);
    setItUploadProgress(0);
    setError('');
    try {
      const controller = new AbortController();
      itUploadAbortRef.current = controller;
      await mailAPI.sendItRequestMultipart({
        templateId: itTemplateId,
        fields: nextValues,
        files: itFiles,
        signal: controller.signal,
        onUploadProgress: (event) => {
          const total = Number(event?.total || 0);
          const loaded = Number(event?.loaded || 0);
          if (total > 0) {
            setItUploadProgress(Math.max(0, Math.min(100, Math.round((loaded / total) * 100))));
          }
        },
      });
      try {
        window.localStorage.removeItem(itDraftKey);
      } catch {
        // Ignore storage errors.
      }
      setItOpen(false);
      setItFiles([]);
      setMessage('IT-заявка отправлена.');
      await refreshInbox({ silent: true });
    } catch (requestError) {
      if (requestError?.code === 'ERR_CANCELED') {
        setError('Отправка IT-заявки отменена.');
      } else {
        setError(requestError?.response?.data?.detail || 'Не удалось отправить IT-заявку.');
      }
    } finally {
      itUploadAbortRef.current = null;
      setItUploadProgress(0);
      setItSending(false);
    }
  }, [itTemplateId, itFieldValues, itFiles, templates, itDraftKey, refreshInbox]);

  const startCreateTemplate = useCallback(() => {
    setTemplateEditId('');
    setTemplateCode('');
    setTemplateTitle('');
    setTemplateCategory('');
    setTemplateSubject('');
    setTemplateBody('');
    setTemplateFields([
      {
        key: 'issue',
        label: 'Описание проблемы',
        type: 'textarea',
        required: true,
        placeholder: 'Опишите проблему подробно',
        help_text: '',
        default_value: '',
        options: [],
        order: 0,
      },
    ]);
  }, []);

  const startEditTemplate = useCallback((item) => {
    setTemplateEditId(String(item?.id || ''));
    setTemplateCode(String(item?.code || ''));
    setTemplateTitle(String(item?.title || ''));
    setTemplateCategory(String(item?.category || ''));
    setTemplateSubject(String(item?.subject_template || ''));
    setTemplateBody(String(item?.body_template_md || ''));
    const fields = normalizeTemplateFields(item?.fields);
    setTemplateFields(fields.length > 0 ? fields : [createTemplateField(0)]);
  }, []);

  const addTemplateField = useCallback(() => {
    setTemplateFields((prev) => [...prev, createTemplateField(prev.length)]);
  }, []);

  const updateTemplateField = useCallback((index, patch) => {
    setTemplateFields((prev) => prev.map((item, idx) => (idx === index ? { ...item, ...patch } : item)));
  }, []);

  const removeTemplateField = useCallback((indexToRemove) => {
    setTemplateFields((prev) => prev.filter((_, idx) => idx !== indexToRemove).map((item, idx) => ({ ...item, order: idx })));
  }, []);

  const moveTemplateField = useCallback((index, direction) => {
    setTemplateFields((prev) => {
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      const copy = [...prev];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy.map((item, idx) => ({ ...item, order: idx }));
    });
  }, []);

  const saveTemplate = useCallback(async () => {
    const code = String(templateCode || '').trim().toLowerCase();
    const title = String(templateTitle || '').trim();
    const subjectTemplate = String(templateSubject || '').trim();
    if (!code || !title || !subjectTemplate) {
      setError('Код, название и тема шаблона обязательны.');
      return;
    }

    const normalizedFields = normalizeTemplateFields(templateFields);
    if (normalizedFields.length === 0) {
      setError('Добавьте хотя бы одно поле шаблона.');
      return;
    }
    const seen = new Set();
    for (const field of normalizedFields) {
      if (!field.key) {
        setError('У каждого поля должен быть уникальный ключ.');
        return;
      }
      if (seen.has(field.key)) {
        setError(`Ключ поля '${field.key}' используется несколько раз.`);
        return;
      }
      seen.add(field.key);
      if (!field.label) {
        setError(`Поле '${field.key}' должно иметь название.`);
        return;
      }
      if (['select', 'multiselect'].includes(field.type) && (!Array.isArray(field.options) || field.options.length === 0)) {
        setError(`Поле '${field.key}' должно содержать варианты выбора.`);
        return;
      }
    }

    setTemplateSaving(true);
    setError('');
    try {
      const payload = {
        code,
        title,
        category: templateCategory,
        subject_template: subjectTemplate,
        body_template_md: templateBody,
        fields: normalizedFields,
      };
      if (templateEditId) {
        await mailAPI.updateTemplate(templateEditId, payload);
        setMessage('Шаблон обновлен.');
      } else {
        await mailAPI.createTemplate(payload);
        setMessage('Шаблон создан.');
      }
      await refreshTemplates();
      startCreateTemplate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Не удалось сохранить шаблон.');
    } finally {
      setTemplateSaving(false);
    }
  }, [templateCode, templateTitle, templateSubject, templateCategory, templateBody, templateFields, templateEditId, refreshTemplates, startCreateTemplate]);

  const deleteTemplate = useCallback(async () => {
    if (!templateEditId) return;
    setTemplateDeleting(true);
    setError('');
    try {
      await mailAPI.deleteTemplate(templateEditId);
      setMessage('Шаблон отключен.');
      await refreshTemplates();
      startCreateTemplate();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Не удалось удалить шаблон.');
    } finally {
      setTemplateDeleting(false);
    }
  }, [templateEditId, refreshTemplates, startCreateTemplate]);

  const templatePreview = useMemo(() => {
    if (!activeTemplate) return { subject: '', body: '' };
    const currentFields = normalizeTemplateFields(activeTemplate.fields);
    const defaults = {};
    currentFields.forEach((field) => {
      defaults[field.key] = itFieldValues[field.key] ?? field.default_value ?? (field.type === 'checkbox' ? false : '');
    });
    const valuesForPreview = {
      full_name: 'Иван Иванов',
      username: 'iivanov',
      mailbox_email: 'ivanov@example.com',
      date: new Date().toISOString().slice(0, 10),
      ...Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, toPreviewText(value)])),
    };
    return {
      subject: replaceTemplateVars(activeTemplate.subject_template, valuesForPreview),
      body: replaceTemplateVars(activeTemplate.body_template_md, valuesForPreview),
    };
  }, [activeTemplate, itFieldValues]);

  const templateEditorPreview = useMemo(() => {
    const values = {
      full_name: 'Иван Иванов',
      username: 'iivanov',
      mailbox_email: 'ivanov@example.com',
      date: new Date().toISOString().slice(0, 10),
    };
    normalizeTemplateFields(templateFields).forEach((field, index) => {
      const fallback = ['select', 'multiselect'].includes(field.type)
        ? (field.options[0] || `Вариант ${index + 1}`)
        : field.type === 'checkbox'
          ? 'Да'
          : (field.default_value || `Пример ${index + 1}`);
      values[field.key] = toPreviewText(fallback);
    });
    return {
      subject: replaceTemplateVars(templateSubject, values),
      body: replaceTemplateVars(templateBody, values),
    };
  }, [templateFields, templateSubject, templateBody]);

  const templateVariableHints = useMemo(() => {
    const builtins = ['full_name', 'username', 'mailbox_email', 'date'];
    const dynamic = normalizeTemplateFields(templateFields).map((field) => field.key).filter(Boolean);
    return [...builtins, ...dynamic];
  }, [templateFields]);

  const clearListFilters = useCallback(() => {
    setSearch('');
    setUnreadOnly(false);
  }, []);
  const hasActiveFilters = Boolean(String(search || '').trim() || unreadOnly);
  const isSearchQueryActive = Boolean(String(debouncedSearch || '').trim());
  const searchedWindow = Number(listData?.searched_window || 0);
  const noResultsHint = useMemo(() => {
    if (!isSearchQueryActive && !unreadOnly) return 'Нет писем';
    if (isSearchQueryActive && listData.search_limited && searchedWindow > 0) {
      return `Ничего не найдено в последних ${searchedWindow} письмах`;
    }
    return 'Ничего не найдено. Измените или снимите фильтры';
  }, [isSearchQueryActive, unreadOnly, listData.search_limited, searchedWindow]);

  const sanitizedPreviewHtml = useMemo(
    () => sanitizeIncomingMailHtml(selectedMessage?.body_html),
    [selectedMessage?.body_html]
  );

  const normalizedPreviewHtml = useMemo(() => {
    const fallback = '<p style="color:#999">Нет содержимого</p>';
    if (!sanitizedPreviewHtml) return fallback;

    const messageFolder = String(selectedMessage?.folder || '').toLowerCase();
    const shouldNormalize = theme.palette.mode === 'dark' && messageFolder === 'inbox';
    if (!shouldNormalize) return sanitizedPreviewHtml;

    return normalizeIncomingMailHtmlForDarkMode(sanitizedPreviewHtml, theme.palette);
  }, [sanitizedPreviewHtml, selectedMessage?.folder, theme.palette]);
  const selectedMessageAttachments = useMemo(
    () => (Array.isArray(selectedMessage?.attachments) ? selectedMessage.attachments : []),
    [selectedMessage?.attachments]
  );
  const selectedMessageAttachmentCount = selectedMessageAttachments.length;
  const selectedMessageAttachmentTotalSize = useMemo(
    () => formatFileSize(sumAttachmentSize(selectedMessageAttachments)),
    [selectedMessageAttachments]
  );

  /* ──────────────────── JSX ──────────────────── */

  return (
    <MainLayout>
      <Box>
        {/* Header */}
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5 }}>
          <MailOutlineIcon sx={{ fontSize: 32, color: 'primary.main' }} />
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Почта</Typography>
          {mailboxInfo?.mailbox_email ? (
            <Chip
              size="small"
              label={mailboxInfo.mailbox_email}
              variant="outlined"
              sx={{ ml: 1, fontWeight: 500, fontSize: '0.78rem' }}
            />
          ) : null}
        </Stack>

        <Snackbar
          open={!!error}
          autoHideDuration={4000}
          onClose={() => setError('')}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        >
          <Alert severity="error" onClose={() => setError('')} sx={{ borderRadius: '10px', boxShadow: 3 }}>
            {error}
          </Alert>
        </Snackbar>

        <Snackbar
          open={!!message}
          autoHideDuration={4000}
          onClose={() => setMessage('')}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        >
          <Alert severity="success" onClose={() => setMessage('')} sx={{ borderRadius: '10px', boxShadow: 3 }}>
            {message}
          </Alert>
        </Snackbar>

        {!mailboxInfo?.mail_is_configured ? (
          <Alert severity="warning" sx={{ mb: 1.5, borderRadius: '10px' }}>
            Почтовая учётная запись не настроена. Обратитесь к администратору для настройки.
          </Alert>
        ) : null}

        {/* Toolbar */}
        <Paper
          elevation={0}
          sx={{
            p: 1.2,
            mb: 1.5,
            borderRadius: '12px',
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ xs: 'stretch', md: 'center' }}>
              <Stack direction="row" spacing={0.5}>
              {Object.entries(FOLDER_LABELS).map(([key, label]) => (
                <Chip
                  key={key}
                  icon={FOLDER_ICONS[key]}
                  label={label}
                  size="small"
                  variant={folder === key ? 'filled' : 'outlined'}
                  color={folder === key ? 'primary' : 'default'}
                  onClick={() => {
                    setFolder(key);
                    setSelectedId('');
                    setSelectedMessage(null);
                  }}
                  sx={{
                    fontWeight: folder === key ? 700 : 500,
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                />
              ))}
            </Stack>

            <TextField
              size="small"
              placeholder="Поиск по теме, отправителю..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              sx={{ flex: 1, minWidth: 180 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" sx={{ color: 'text.disabled' }} />
                  </InputAdornment>
                ),
                sx: { borderRadius: '8px', fontSize: '0.85rem' },
              }}
            />

              <FormControlLabel
                control={<Switch size="small" checked={unreadOnly} onChange={(event) => setUnreadOnly(event.target.checked)} />}
                label={<Typography variant="body2" sx={{ fontSize: '0.8rem' }}>Непрочитанные</Typography>}
                sx={{ mx: 0 }}
              />
              {hasActiveFilters ? (
                <Chip
                  size="small"
                  label="Снять фильтры"
                  onClick={clearListFilters}
                  variant="outlined"
                  sx={{ alignSelf: { xs: 'flex-start', md: 'center' } }}
                />
              ) : null}

            <Stack direction="row" spacing={0.5}>
              <Tooltip title="Обновить">
                <IconButton size="small" onClick={() => refreshInbox()} disabled={loading}>
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Button variant="contained" size="small" startIcon={<AddIcon />} onClick={openCompose}
                sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600, px: 2 }}
              >
                Написать
              </Button>
              <Button variant="outlined" size="small" startIcon={<AssignmentIcon />} onClick={openItRequest}
                sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600, px: 2 }}
              >
                Заявка в IT
              </Button>
              <Button variant="outlined" size="small" startIcon={<EmailIcon />} onClick={openSignatureEditor}
                sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600, px: 2 }}
              >
                Подпись
              </Button>
              {canManageUsers ? (
                <Tooltip title="Управление шаблонами">
                  <IconButton size="small" onClick={() => setTemplatesOpen(true)}>
                    <SettingsSuggestIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              ) : null}
            </Stack>
          </Stack>
        </Paper>
        {isSearchQueryActive && listData.search_limited && searchedWindow > 0 ? (
          <Alert severity="info" sx={{ mb: 1.5, borderRadius: '10px' }}>
            {`Поиск выполняется по последним ${searchedWindow} письмам.`}
          </Alert>
        ) : null}

        {/* Main content: list + preview */}
        <Grid container spacing={1.5}>
          {/* ─── Message list ─── */}
          <Grid item xs={12} md={4}>
            <Box sx={sidebarSx}>
              <Box sx={{ px: 2, py: 1.2, borderBottom: '1px solid', borderColor: 'divider', bgcolor: 'action.hover' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: '0.82rem' }}>
                    {FOLDER_LABELS[folder] || 'Письма'}
                  </Typography>
                  <Chip size="small" label={listData.total} sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700 }} />
                </Stack>
              </Box>
              <List dense sx={{ overflowY: 'auto', p: 0, flex: 1 }}>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <Box key={i} sx={{ px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
                      <Skeleton variant="text" width="70%" />
                      <Skeleton variant="text" width="50%" />
                      <Skeleton variant="text" width="90%" />
                    </Box>
                  ))
                ) : listData.items.length === 0 ? (
                  <Box sx={{ p: 4, textAlign: 'center' }}>
                    <InboxIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                    <Typography variant="body2" color="text.secondary">{noResultsHint}</Typography>
                    {hasActiveFilters ? (
                      <Button size="small" onClick={clearListFilters} sx={{ textTransform: 'none', mt: 0.8 }}>
                        Снять фильтры
                      </Button>
                    ) : null}
                  </Box>
                ) : (
                  listData.items.map((item) => {
                    const selected = String(selectedId) === String(item.id);
                    const unread = !item.is_read;
                    const rawAttachmentCount = Number(item.attachments_count || 0);
                    const showAttachmentIndicator = Boolean(item.has_attachments);
                    const attachmentCountLabel = rawAttachmentCount > 0 ? String(rawAttachmentCount) : '1+';
                    return (
                      <ListItemButton
                        key={item.id}
                        selected={selected}
                        onClick={() => setSelectedId(String(item.id))}
                        sx={{
                          py: 1.2,
                          px: 1.5,
                          alignItems: 'flex-start',
                          borderBottom: '1px solid',
                          borderColor: 'divider',
                          borderLeft: selected ? '3px solid' : '3px solid transparent',
                          borderLeftColor: selected ? 'primary.main' : 'transparent',
                          bgcolor: selected ? 'action.selected' : unread ? 'rgba(25,118,210,0.04)' : 'transparent',
                          transition: 'all 0.12s',
                          '&:hover': { bgcolor: selected ? 'action.selected' : 'action.hover' },
                        }}
                      >
                        <ListItemAvatar sx={{ minWidth: 40 }}>
                          <Avatar
                            sx={{
                              width: 32, height: 32, fontSize: '0.7rem', fontWeight: 700,
                              bgcolor: getAvatarColor(item.sender),
                            }}
                          >
                            {getInitials(item.sender)}
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={(
                            <Typography
                              variant="body2"
                              noWrap
                              sx={{ fontWeight: unread ? 700 : 500, fontSize: '0.82rem', pr: 0.5 }}
                            >
                              {item.subject || '(без темы)'}
                            </Typography>
                          )}
                          secondary={(
                            <>
                              <Typography variant="caption" noWrap sx={{ display: 'block', color: unread ? 'text.primary' : 'text.secondary', fontWeight: unread ? 600 : 400, fontSize: '0.72rem' }}>
                                {item.sender || '-'}
                              </Typography>
                              {item.body_preview ? (
                                <Typography variant="caption" noWrap sx={{ display: 'block', color: 'text.disabled', fontSize: '0.7rem', mt: 0.2 }}>
                                  {item.body_preview}
                                </Typography>
                              ) : null}
                            </>
                          )}
                          sx={{ minWidth: 0, mr: 0.5 }}
                        />
                        <Stack
                          spacing={0.35}
                          sx={{
                            width: 44,
                            minWidth: 44,
                            alignItems: 'flex-end',
                            flexShrink: 0,
                            pt: 0.05,
                          }}
                        >
                          <Typography
                            variant="caption"
                            sx={{
                              color: 'text.disabled',
                              fontSize: '0.68rem',
                              lineHeight: 1.1,
                              whiteSpace: 'nowrap',
                              textAlign: 'right',
                            }}
                          >
                            {formatTime(item.received_at)}
                          </Typography>
                          {showAttachmentIndicator ? (
                            <Tooltip title={`Вложений: ${attachmentCountLabel}`}>
                              <Stack direction="row" spacing={0.2} alignItems="center" sx={{ color: 'text.secondary', justifyContent: 'flex-end' }}>
                                <AttachFileIcon sx={{ fontSize: 13 }} />
                                <Typography variant="caption" sx={{ fontSize: '0.68rem', fontWeight: 600 }}>
                                  {attachmentCountLabel}
                                </Typography>
                              </Stack>
                            </Tooltip>
                          ) : null}
                          {unread ? (
                            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: 'primary.main' }} />
                          ) : null}
                        </Stack>
                      </ListItemButton>
                    );
                  })
                )}
              </List>
            </Box>
          </Grid>

          {/* ─── Message preview ─── */}
          <Grid item xs={12} md={8}>
            <Box sx={previewPaneSx}>
              {detailLoading ? (
                <Box sx={{ p: 3 }}>
                  <Skeleton variant="text" width="60%" height={32} />
                  <Skeleton variant="text" width="40%" sx={{ mt: 1 }} />
                  <Skeleton variant="rectangular" height={300} sx={{ mt: 2, borderRadius: '8px' }} />
                </Box>
              ) : !selectedMessage ? (
                <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                  <MailOutlineIcon sx={{ fontSize: 64, color: 'text.disabled', mb: 1.5 }} />
                  <Typography variant="body1" color="text.secondary">Выберите письмо для просмотра</Typography>
                </Box>
              ) : (
                <>
                  {/* Message header */}
                  <Box sx={{ px: 3, py: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem', mb: 1.5, lineHeight: 1.3 }}>
                      {selectedMessage.subject || '(без темы)'}
                    </Typography>

                    <Stack direction="row" spacing={1.5} alignItems="center">
                      <Avatar sx={{ width: 36, height: 36, bgcolor: getAvatarColor(selectedMessage.sender), fontSize: '0.8rem', fontWeight: 700 }}>
                        {getInitials(selectedMessage.sender)}
                      </Avatar>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.85rem' }}>
                          {selectedMessage.sender || '-'}
                        </Typography>
                        <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
                            Кому: {(selectedMessage.to || []).join(', ') || '-'}
                          </Typography>
                          {selectedMessage.cc?.length > 0 ? (
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
                              • Копия: {selectedMessage.cc.join(', ')}
                            </Typography>
                          ) : null}
                        </Stack>
                      </Box>
                      <Stack alignItems="flex-end" spacing={0.3}>
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <AccessTimeIcon sx={{ fontSize: 14, color: 'text.disabled' }} />
                          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
                            {formatFullDate(selectedMessage.received_at)}
                          </Typography>
                        </Stack>
                        {selectedMessageAttachmentCount > 0 ? (
                          <Stack spacing={0.5} sx={{ mt: 0.5, alignItems: 'flex-end' }}>
                            <Stack direction="row" spacing={0.4} alignItems="center" sx={{ color: 'text.secondary' }}>
                              <AttachFileIcon sx={{ fontSize: 14 }} />
                              <Typography variant="caption" sx={{ fontSize: '0.72rem' }}>
                                {`${selectedMessageAttachmentCount} файл(ов), ${selectedMessageAttachmentTotalSize}`}
                              </Typography>
                            </Stack>
                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ justifyContent: 'flex-end' }}>
                              {selectedMessageAttachments.map((att, idx) => (
                                <Chip
                                  key={idx}
                                  icon={<AttachFileIcon sx={{ fontSize: '14px !important' }} />}
                                  label={att.name || 'attachment'}
                                  size="small"
                                  variant="outlined"
                                  onClick={(e) => openAttachmentPreview(e, att)}
                                  onDelete={(e) => handleDownloadAttachment(e, att)}
                                  deleteIcon={<DownloadIcon sx={{ fontSize: '16px !important' }} />}
                                  sx={{
                                    height: 24,
                                    fontSize: '0.7rem',
                                    cursor: 'pointer',
                                    maxWidth: { xs: 220, sm: 300 },
                                    '& .MuiChip-label': {
                                      display: 'block',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      whiteSpace: 'nowrap',
                                    },
                                    '&:hover': { bgcolor: 'action.hover' },
                                  }}
                                />
                              ))}
                            </Stack>
                          </Stack>
                        ) : null}
                      </Stack>
                    </Stack>
                  </Box>

                  {/* Message body — rendered HTML */}
                  <Box
                    sx={htmlBodySx}
                    dangerouslySetInnerHTML={{ __html: normalizedPreviewHtml }}
                  />
                </>
              )}
            </Box>
          </Grid>
        </Grid>
        <Dialog
          open={attachmentPreview.open}
          onClose={closeAttachmentPreview}
          maxWidth="lg"
          fullWidth
          PaperProps={{ sx: { borderRadius: '12px' } }}
        >
          <DialogTitle sx={{ fontWeight: 700 }}>
            {`Предпросмотр: ${attachmentPreview.filename || 'вложение'}`}
          </DialogTitle>
          <DialogContent dividers sx={{ minHeight: 420 }}>
            {attachmentPreview.loading ? (
              <Stack spacing={1}>
                <Skeleton variant="text" width="35%" />
                <Skeleton variant="rectangular" height={320} sx={{ borderRadius: '8px' }} />
              </Stack>
            ) : attachmentPreview.error ? (
              <Alert severity="error">{attachmentPreview.error}</Alert>
            ) : attachmentPreview.kind === 'image' && attachmentPreview.objectUrl ? (
              <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                <Box
                  component="img"
                  src={attachmentPreview.objectUrl}
                  alt={attachmentPreview.filename || 'preview'}
                  sx={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: '8px' }}
                />
              </Box>
            ) : attachmentPreview.kind === 'pdf' && attachmentPreview.objectUrl ? (
              <Box
                component="iframe"
                title={attachmentPreview.filename || 'pdf-preview'}
                src={attachmentPreview.objectUrl}
                sx={{ width: '100%', height: '70vh', border: 'none', borderRadius: '8px' }}
              />
            ) : attachmentPreview.kind === 'text' ? (
            <Stack spacing={0.8}>
              <Paper variant="outlined" sx={{ p: 1, borderRadius: '8px', bgcolor: 'action.hover' }}>
                <Typography variant="caption" color="text.secondary">
                  {attachmentPreview.contentType || 'text/plain'}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '8px', maxHeight: '65vh', overflow: 'auto' }}>
                <Box component="pre" sx={{ m: 0, fontFamily: 'Consolas, "Courier New", monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {attachmentPreview.textContent || '(пустой файл)'}
                </Box>
              </Paper>
              {attachmentPreview.textTruncated ? (
                <Alert severity="info">Показана только часть файла (до 1 МБ).</Alert>
              ) : null}
            </Stack>
          ) : attachmentPreview.tooLargeForPreview ? (
            <Alert severity="warning">
              {`Файл слишком большой для предпросмотра (>${formatFileSize(MAX_PREVIEW_FILE_BYTES)}). Используйте кнопку «Скачать».`}
            </Alert>
          ) : (
            <Alert severity="info">
              Предпросмотр недоступен для этого типа файла. Используйте кнопку «Скачать».
            </Alert>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={closeAttachmentPreview} sx={{ textTransform: 'none' }}>
            Закрыть
          </Button>
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            onClick={downloadFromPreview}
            disabled={attachmentPreview.loading || !attachmentPreview.blob}
            sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600 }}
          >
            Скачать
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={signatureOpen} onClose={() => setSignatureOpen(false)} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: '12px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Подпись</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.2} sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              Подпись автоматически добавляется в конце каждого отправленного письма.
            </Typography>
            <Box sx={{
              flex: 1,
              minHeight: 260,
              display: 'flex',
              flexDirection: 'column',
              '& .ql-toolbar': {
                borderColor: 'divider',
                bgcolor: 'action.hover',
                borderTopLeftRadius: '8px',
                borderTopRightRadius: '8px',
                '& .ql-stroke': { stroke: 'text.primary' },
                '& .ql-fill': { fill: 'text.primary' },
                '& .ql-picker': { color: 'text.primary' },
              },
              '& .ql-container': {
                borderColor: 'divider',
                borderBottomLeftRadius: '8px',
                borderBottomRightRadius: '8px',
                color: 'text.primary',
                bgcolor: 'background.paper',
                fontFamily: 'inherit',
                fontSize: '0.95rem',
              },
              '& .ql-editor': {
                minHeight: '220px',
              },
            }}>
              <ReactQuill
                theme="snow"
                value={signatureHtml}
                onChange={setSignatureHtml}
                style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              />
            </Box>
            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '10px', bgcolor: 'action.hover' }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                Предпросмотр подписи:
              </Typography>
              <Box
                sx={{
                  mt: 0.8,
                  fontSize: '0.9rem',
                  lineHeight: 1.45,
                  '& img': { maxWidth: '100%' },
                  '& p, & div': { margin: 0 },
                  '& p + p, & p + div, & div + p, & div + div': { marginTop: '0.3em' },
                  '& ul, & ol': { margin: '0.35em 0 0.35em 1.2em', padding: 0 },
                  '& li': { margin: 0 },
                }}
                dangerouslySetInnerHTML={{ __html: signatureHtml || '<span style="color:#999">Подпись не задана</span>' }}
              />
            </Paper>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={() => setSignatureHtml('')}
            disabled={signatureSaving}
            sx={{ textTransform: 'none' }}
          >
            Очистить
          </Button>
          <Button onClick={() => setSignatureOpen(false)} disabled={signatureSaving} sx={{ textTransform: 'none' }}>
            Отмена
          </Button>
          <Button
            variant="contained"
            onClick={handleSaveSignature}
            disabled={signatureSaving}
            sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600 }}
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      {/* ─── Compose dialog ─── */}
      <Dialog open={composeOpen} onClose={() => setComposeOpen(false)} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: '12px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Новое письмо</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <Autocomplete
              multiple
              freeSolo
              size="small"
              options={composeToOptions}
              loading={composeToLoading}
              filterOptions={(x) => x}
              getOptionLabel={(option) => {
                if (typeof option === 'string') return option;
                return `${option.name} <${option.email}>`;
              }}
              value={composeToValues}
              onChange={(event, newValue) => {
                setComposeToValues(newValue);
              }}
              onInputChange={(event, newInputValue) => {
                setComposeToSearch(newInputValue);
              }}
              renderTags={(value, getTagProps) =>
                value.map((option, index) => {
                  const label = typeof option === 'string' ? option : option.name || option.email;
                  return (
                    <Chip variant="outlined" size="small" label={label} {...getTagProps({ index })} />
                  );
                })
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Кому"
                  placeholder="Выберите контакт или введите email..."
                  InputProps={{ ...params.InputProps, sx: { borderRadius: '8px' } }}
                />
              )}
            />
            <TextField
              size="small"
              label="Тема"
              value={composeSubject}
              onChange={(event) => setComposeSubject(event.target.value)}
              InputProps={{ sx: { borderRadius: '8px' } }}
            />
            <Box sx={{
              flex: 1,
              minHeight: 300,
              display: 'flex',
              flexDirection: 'column',
              '& .ql-toolbar': {
                borderColor: 'divider',
                bgcolor: 'action.hover',
                borderTopLeftRadius: '8px',
                borderTopRightRadius: '8px',
                '& .ql-stroke': { stroke: 'text.primary' },
                '& .ql-fill': { fill: 'text.primary' },
                '& .ql-picker': { color: 'text.primary' }
              },
              '& .ql-container': {
                borderColor: 'divider',
                borderBottomLeftRadius: '8px',
                borderBottomRightRadius: '8px',
                color: 'text.primary',
                bgcolor: 'background.paper',
                fontFamily: 'inherit',
                fontSize: '0.95rem'
              },
              '& .ql-editor': {
                minHeight: '260px'
              }
            }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, px: 1 }}>Текст письма</Typography>
              <ReactQuill
                theme="snow"
                value={composeBody}
                onChange={setComposeBody}
                style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              />
            </Box>
            {composeFiles.length > 0 && (
              <Stack spacing={0.8} sx={{ mt: 1 }}>
                <Paper variant="outlined" sx={{ p: 1, borderRadius: '8px', bgcolor: 'action.hover' }}>
                  <Stack direction="row" spacing={0.6} alignItems="center">
                    <AttachFileIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                    <Typography variant="body2" sx={{ fontSize: '0.78rem', fontWeight: 600 }}>
                      {`Прикреплено: ${composeFiles.length} файлов • ${formatFileSize(sumFilesSize(composeFiles))}`}
                    </Typography>
                  </Stack>
                </Paper>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {composeFiles.map((file, idx) => (
                    <Chip
                      key={idx}
                      icon={<AttachFileIcon sx={{ fontSize: '14px !important' }} />}
                      label={file.name}
                      size="small"
                      onDelete={() => removeComposeFile(idx)}
                      sx={{
                        height: 24,
                        fontSize: '0.75rem',
                        maxWidth: { xs: 220, sm: 320 },
                        '& .MuiChip-label': {
                          display: 'block',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        },
                      }}
                    />
                  ))}
                </Stack>
              </Stack>
            )}
            {composeSending && composeFiles.length > 0 ? (
              <Paper variant="outlined" sx={{ p: 1, borderRadius: '8px' }}>
                <Stack spacing={0.6}>
                  <Typography variant="caption" color="text.secondary">
                    {composeUploadProgress > 0 ? `Загрузка вложений: ${composeUploadProgress}%` : 'Загрузка вложений...'}
                  </Typography>
                  {composeUploadProgress > 0 ? (
                    <LinearProgress variant="determinate" value={composeUploadProgress} />
                  ) : (
                    <LinearProgress />
                  )}
                </Stack>
              </Paper>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, justifyContent: 'space-between' }}>
          <Button component="label" startIcon={<AttachFileIcon />} sx={{ textTransform: 'none', color: 'text.secondary' }}>
            Прикрепить
            <input type="file" multiple hidden onChange={handleFileChange} />
          </Button>
          <Stack direction="row" spacing={1}>
            {composeSending && composeFiles.length > 0 ? (
              <Button onClick={cancelComposeUpload} color="warning" sx={{ textTransform: 'none' }}>
                Отменить загрузку
              </Button>
            ) : null}
            <Button onClick={clearComposeDraft} disabled={composeSending} sx={{ textTransform: 'none' }}>
              Очистить черновик
            </Button>
            <Button onClick={() => setComposeOpen(false)} disabled={composeSending} sx={{ textTransform: 'none' }}>Отмена</Button>
            <Button
              variant="contained"
              onClick={handleSendCompose}
              disabled={composeSending}
              startIcon={<SendIcon />}
              sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600, px: 3 }}
            >
              Отправить
            </Button>
          </Stack>
        </DialogActions>
      </Dialog>

      {/* ─── IT Request dialog ─── */}
      <Dialog open={itOpen} onClose={() => setItOpen(false)} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: '12px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Заявка в IT</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <FormControl size="small" fullWidth>
              <InputLabel>Шаблон заявки</InputLabel>
              <Select
                label="Шаблон заявки"
                value={itTemplateId}
                onChange={(event) => {
                  const nextId = String(event.target.value || '');
                  setItTemplateId(nextId);
                  const nextTemplate = templates.find((item) => String(item.id) === nextId);
                  setItFieldValues(buildInitialFieldValues(nextTemplate));
                  setItFieldErrors({});
                  setItFiles([]);
                }}
                sx={{ borderRadius: '8px' }}
              >
                {templates.map((item) => (
                  <MenuItem key={item.id} value={item.id}>{item.title}</MenuItem>
                ))}
              </Select>
            </FormControl>

            {normalizeTemplateFields(activeTemplate?.fields).map((field) => {
              const key = String(field.key || '');
              const errorText = itFieldErrors[key] || '';
              const options = Array.isArray(field.options) ? field.options : [];
              const value = itFieldValues[key];
              if (field.type === 'multiselect') {
                const selected = Array.isArray(value) ? value : [];
                return (
                  <FormControl key={key} size="small" fullWidth error={Boolean(errorText)}>
                    <InputLabel>{field.label || key}</InputLabel>
                    <Select
                      multiple
                      label={field.label || key}
                      value={selected}
                      onChange={(event) => {
                        const nextValue = event.target.value;
                        setItFieldValues((prev) => ({ ...prev, [key]: Array.isArray(nextValue) ? nextValue : [] }));
                        setItFieldErrors((prev) => ({ ...prev, [key]: '' }));
                      }}
                      renderValue={(selectedValues) => (Array.isArray(selectedValues) ? selectedValues.join(', ') : '')}
                      sx={{ borderRadius: '8px' }}
                    >
                      {options.map((option) => (
                        <MenuItem key={option} value={option}>{option}</MenuItem>
                      ))}
                    </Select>
                    {field.help_text ? <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>{field.help_text}</Typography> : null}
                    {errorText ? <Typography variant="caption" color="error" sx={{ mt: 0.5 }}>{errorText}</Typography> : null}
                  </FormControl>
                );
              }
              if (field.type === 'select') {
                return (
                  <FormControl key={key} size="small" fullWidth error={Boolean(errorText)}>
                    <InputLabel>{field.label || key}</InputLabel>
                    <Select
                      label={field.label || key}
                      value={String(value ?? '')}
                      onChange={(event) => {
                        setItFieldValues((prev) => ({ ...prev, [key]: String(event.target.value || '') }));
                        setItFieldErrors((prev) => ({ ...prev, [key]: '' }));
                      }}
                      sx={{ borderRadius: '8px' }}
                    >
                      {options.map((option) => (
                        <MenuItem key={option} value={option}>{option}</MenuItem>
                      ))}
                    </Select>
                    {field.help_text ? <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>{field.help_text}</Typography> : null}
                    {errorText ? <Typography variant="caption" color="error" sx={{ mt: 0.5 }}>{errorText}</Typography> : null}
                  </FormControl>
                );
              }
              if (field.type === 'checkbox') {
                return (
                  <Stack key={key} spacing={0.4}>
                    <FormControlLabel
                      control={(
                        <Switch
                          checked={Boolean(value)}
                          onChange={(event) => {
                            setItFieldValues((prev) => ({ ...prev, [key]: Boolean(event.target.checked) }));
                            setItFieldErrors((prev) => ({ ...prev, [key]: '' }));
                          }}
                        />
                      )}
                      label={field.label || key}
                    />
                    {field.help_text ? <Typography variant="caption" color="text.secondary">{field.help_text}</Typography> : null}
                    {errorText ? <Typography variant="caption" color="error">{errorText}</Typography> : null}
                  </Stack>
                );
              }
              return (
                <TextField
                  key={key}
                  size="small"
                  type={field.type === 'date' ? 'date' : field.type === 'email' ? 'email' : field.type === 'tel' ? 'tel' : 'text'}
                  multiline={field.type === 'textarea'}
                  minRows={field.type === 'textarea' ? 4 : undefined}
                  label={field.label || key}
                  required={Boolean(field.required ?? true)}
                  placeholder={field.placeholder || ''}
                  helperText={errorText || field.help_text || ' '}
                  error={Boolean(errorText)}
                  value={field.type === 'date' ? String(value || '') : String(value ?? '')}
                  onChange={(event) => {
                    setItFieldValues((prev) => ({ ...prev, [key]: event.target.value }));
                    setItFieldErrors((prev) => ({ ...prev, [key]: '' }));
                  }}
                  InputProps={{ sx: { borderRadius: '8px' } }}
                  InputLabelProps={field.type === 'date' ? { shrink: true } : undefined}
                />
              );
            })}

            {activeTemplate ? (
              <Stack spacing={1}>
                <Button component="label" variant="outlined" startIcon={<AttachFileIcon />} sx={{ textTransform: 'none', borderRadius: '8px' }}>
                  Добавить файлы
                  <input type="file" hidden multiple onChange={handleItFilesChange} />
                </Button>
                {itFiles.length > 0 ? (
                  <Stack spacing={0.8}>
                    <Paper variant="outlined" sx={{ p: 1, borderRadius: '8px', bgcolor: 'action.hover' }}>
                      <Stack direction="row" spacing={0.6} alignItems="center">
                        <AttachFileIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                        <Typography variant="body2" sx={{ fontSize: '0.78rem', fontWeight: 600 }}>
                          {`Прикреплено: ${itFiles.length} файлов • ${formatFileSize(sumFilesSize(itFiles))}`}
                        </Typography>
                      </Stack>
                    </Paper>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {itFiles.map((file, index) => (
                        <Chip
                          key={`${file.name}_${index}`}
                          icon={<AttachFileIcon sx={{ fontSize: '14px !important' }} />}
                          label={file.name}
                          size="small"
                          onDelete={() => removeItFile(index)}
                          sx={{
                            height: 24,
                            fontSize: '0.75rem',
                            maxWidth: { xs: 220, sm: 320 },
                            '& .MuiChip-label': {
                              display: 'block',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            },
                          }}
                        />
                      ))}
                    </Stack>
                  </Stack>
                ) : null}
              </Stack>
            ) : null}
            {itSending && itFiles.length > 0 ? (
              <Paper variant="outlined" sx={{ p: 1, borderRadius: '8px' }}>
                <Stack spacing={0.6}>
                  <Typography variant="caption" color="text.secondary">
                    {itUploadProgress > 0 ? `Загрузка вложений: ${itUploadProgress}%` : 'Загрузка вложений...'}
                  </Typography>
                  {itUploadProgress > 0 ? (
                    <LinearProgress variant="determinate" value={itUploadProgress} />
                  ) : (
                    <LinearProgress />
                  )}
                </Stack>
              </Paper>
            ) : null}

            {activeTemplate ? (
              <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '10px', bgcolor: 'action.hover' }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Предпросмотр темы:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>{templatePreview.subject || '-'}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Предпросмотр текста:</Typography>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>{templatePreview.body || '-'}</Typography>
              </Paper>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          {itSending && itFiles.length > 0 ? (
            <Button onClick={cancelItUpload} color="warning" sx={{ textTransform: 'none' }}>
              Отменить загрузку
            </Button>
          ) : null}
          <Button onClick={clearItDraft} disabled={itSending} sx={{ textTransform: 'none' }}>
            Очистить черновик
          </Button>
          <Button onClick={() => setItOpen(false)} disabled={itSending} sx={{ textTransform: 'none' }}>Отмена</Button>
          <Button
            variant="contained"
            onClick={handleSendItRequest}
            disabled={itSending || !itTemplateId}
            startIcon={<AssignmentIcon />}
            sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600, px: 3 }}
          >
            Отправить заявку
          </Button>
        </DialogActions>
      </Dialog>

      {/* ─── Templates dialog ─── */}
      <Dialog open={templatesOpen} onClose={() => setTemplatesOpen(false)} maxWidth="lg" fullWidth PaperProps={{ sx: { borderRadius: '12px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Шаблоны IT-заявок</DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={1.5}>
            <Grid item xs={12} md={4}>
              <Paper variant="outlined" sx={{ maxHeight: 500, overflowY: 'auto', borderRadius: '10px' }}>
                <List dense>
                  <ListItemButton onClick={startCreateTemplate} selected={!templateEditId}>
                    <ListItemText primary="+ Новый шаблон" primaryTypographyProps={{ fontWeight: 600 }} />
                  </ListItemButton>
                  {templates.map((item) => (
                    <ListItemButton key={item.id} onClick={() => startEditTemplate(item)} selected={String(templateEditId) === String(item.id)}>
                      <ListItemText
                        primary={item.title || item.code}
                        secondary={item.code}
                      />
                    </ListItemButton>
                  ))}
                </List>
              </Paper>
            </Grid>
            <Grid item xs={12} md={8}>
              <Stack spacing={1.2}>
                <TextField size="small" label="Код" value={templateCode} onChange={(event) => setTemplateCode(event.target.value)} InputProps={{ sx: { borderRadius: '8px' } }} />
                <TextField size="small" label="Название" value={templateTitle} onChange={(event) => setTemplateTitle(event.target.value)} InputProps={{ sx: { borderRadius: '8px' } }} />
                <TextField size="small" label="Категория" value={templateCategory} onChange={(event) => setTemplateCategory(event.target.value)} InputProps={{ sx: { borderRadius: '8px' } }} />
                <TextField size="small" label="Тема (subject template)" value={templateSubject} onChange={(event) => setTemplateSubject(event.target.value)} InputProps={{ sx: { borderRadius: '8px' } }} />
                <TextField multiline minRows={7} label="Текст шаблона" value={templateBody} onChange={(event) => setTemplateBody(event.target.value)} InputProps={{ sx: { borderRadius: '8px' } }} />
                <Paper variant="outlined" sx={{ p: 1.2, borderRadius: '10px' }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Поля формы</Typography>
                    <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={addTemplateField} sx={{ textTransform: 'none' }}>
                      Добавить поле
                    </Button>
                  </Stack>
                  <Stack spacing={1}>
                    {templateFields.map((field, index, arr) => (
                      <Paper key={`${field.key}_${index}`} variant="outlined" sx={{ p: 1, borderRadius: '8px' }}>
                        <Stack spacing={1}>
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                            <Tooltip title="Вверх">
                              <span>
                                <IconButton size="small" disabled={index === 0} onClick={() => moveTemplateField(index, -1)}>
                                  <ArrowUpwardIcon fontSize="inherit" />
                                </IconButton>
                              </span>
                            </Tooltip>
                            <Tooltip title="Вниз">
                              <span>
                                <IconButton size="small" disabled={index === arr.length - 1} onClick={() => moveTemplateField(index, 1)}>
                                  <ArrowDownwardIcon fontSize="inherit" />
                                </IconButton>
                              </span>
                            </Tooltip>
                            <Tooltip title="Удалить поле">
                              <IconButton size="small" color="error" onClick={() => removeTemplateField(index)}>
                                <DeleteIcon fontSize="inherit" />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                          <Grid container spacing={1}>
                            <Grid item xs={12} md={5}>
                              <TextField
                                size="small"
                                label="Ключ (латиница)"
                                value={field.key}
                                onChange={(event) => updateTemplateField(index, { key: normalizeFieldKey(event.target.value, field.key) })}
                                InputProps={{ sx: { borderRadius: '8px' } }}
                                fullWidth
                              />
                            </Grid>
                            <Grid item xs={12} md={7}>
                              <TextField
                                size="small"
                                label="Название поля"
                                value={field.label}
                                onChange={(event) => updateTemplateField(index, { label: event.target.value })}
                                InputProps={{ sx: { borderRadius: '8px' } }}
                                fullWidth
                              />
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <FormControl size="small" fullWidth>
                                <InputLabel>Тип</InputLabel>
                                <Select
                                  label="Тип"
                                  value={field.type}
                                  onChange={(event) => {
                                    const nextType = String(event.target.value || 'text');
                                    updateTemplateField(index, {
                                      type: nextType,
                                      options: ['select', 'multiselect'].includes(nextType) ? field.options : [],
                                    });
                                  }}
                                  sx={{ borderRadius: '8px' }}
                                >
                                  {TEMPLATE_FIELD_TYPES.map((typeItem) => (
                                    <MenuItem key={typeItem.value} value={typeItem.value}>{typeItem.label}</MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <TextField
                                size="small"
                                label="Placeholder"
                                value={field.placeholder}
                                onChange={(event) => updateTemplateField(index, { placeholder: event.target.value })}
                                InputProps={{ sx: { borderRadius: '8px' } }}
                                fullWidth
                              />
                            </Grid>
                            <Grid item xs={12} md={4}>
                              {field.type === 'checkbox' ? (
                                <FormControlLabel
                                  control={(
                                    <Switch
                                      checked={Boolean(field.default_value)}
                                      onChange={(event) => updateTemplateField(index, { default_value: Boolean(event.target.checked) })}
                                    />
                                  )}
                                  label="Значение по умолчанию"
                                />
                              ) : (
                                <TextField
                                  size="small"
                                  label="Значение по умолчанию"
                                  value={Array.isArray(field.default_value) ? field.default_value.join('; ') : String(field.default_value || '')}
                                  onChange={(event) => {
                                    if (field.type === 'multiselect') {
                                      updateTemplateField(index, { default_value: normalizeFieldOptions(event.target.value) });
                                    } else {
                                      updateTemplateField(index, { default_value: event.target.value });
                                    }
                                  }}
                                  InputProps={{ sx: { borderRadius: '8px' } }}
                                  fullWidth
                                />
                              )}
                            </Grid>
                            <Grid item xs={12}>
                              <TextField
                                size="small"
                                label="Подсказка под полем"
                                value={field.help_text}
                                onChange={(event) => updateTemplateField(index, { help_text: event.target.value })}
                                InputProps={{ sx: { borderRadius: '8px' } }}
                                fullWidth
                              />
                            </Grid>
                            {['select', 'multiselect'].includes(field.type) ? (
                              <Grid item xs={12}>
                                <TextField
                                  size="small"
                                  multiline
                                  minRows={2}
                                  label="Варианты (по одному на строку)"
                                  value={(Array.isArray(field.options) ? field.options : []).join('\n')}
                                  onChange={(event) => updateTemplateField(index, { options: normalizeFieldOptions(event.target.value) })}
                                  InputProps={{ sx: { borderRadius: '8px' } }}
                                  fullWidth
                                />
                              </Grid>
                            ) : null}
                            <Grid item xs={12}>
                              <FormControlLabel
                                control={<Switch checked={Boolean(field.required)} onChange={(event) => updateTemplateField(index, { required: Boolean(event.target.checked) })} />}
                                label="Обязательное поле"
                              />
                            </Grid>
                          </Grid>
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                </Paper>
                <Paper variant="outlined" sx={{ p: 1.2, borderRadius: '10px', bgcolor: 'action.hover' }}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Переменные для шаблона:</Typography>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.8 }}>
                    {templateVariableHints.map((keyName) => (
                      <Chip key={keyName} size="small" label={`{{${keyName}}}`} />
                    ))}
                  </Stack>
                </Paper>
                <Paper variant="outlined" sx={{ p: 1.2, borderRadius: '10px', bgcolor: 'action.hover' }}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Live preview темы:</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>{templateEditorPreview.subject || '-'}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Live preview текста:</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>{templateEditorPreview.body || '-'}</Typography>
                </Paper>
                <Stack direction="row" spacing={1}>
                  <Button
                    variant="contained"
                    onClick={saveTemplate}
                    disabled={templateSaving}
                    sx={{ textTransform: 'none', borderRadius: '8px', fontWeight: 600 }}
                  >
                    {templateEditId ? 'Сохранить' : 'Создать'}
                  </Button>
                  {templateEditId ? (
                    <Button
                      color="error"
                      variant="outlined"
                      onClick={deleteTemplate}
                      disabled={templateDeleting}
                      sx={{ textTransform: 'none', borderRadius: '8px' }}
                    >
                      Отключить
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setTemplatesOpen(false)} sx={{ textTransform: 'none' }}>Закрыть</Button>
        </DialogActions>
        </Dialog>
      </Box>
    </MainLayout>
  );
}

export default Mail;

