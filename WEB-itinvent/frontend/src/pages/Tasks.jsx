import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
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
  InputLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AssignmentIcon from '@mui/icons-material/Assignment';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import EditIcon from '@mui/icons-material/Edit';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import DownloadIcon from '@mui/icons-material/Download';
import DescriptionIcon from '@mui/icons-material/Description';
import FlagIcon from '@mui/icons-material/Flag';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import RefreshIcon from '@mui/icons-material/Refresh';
import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import FilterListIcon from '@mui/icons-material/FilterList';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import MainLayout from '../components/layout/MainLayout';
import { hubAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useLocation } from 'react-router-dom';
import MarkdownRenderer from '../components/hub/MarkdownRenderer';
import MarkdownEditor from '../components/hub/MarkdownEditor';

/* ──────────────── Constants ──────────────── */

const KANBAN_COLUMNS = [
  { key: 'new', label: 'Новое', color: '#3b82f6', bg: 'rgba(59,130,246,0.08)', headerBg: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)' },
  { key: 'in_progress', label: 'В работе', color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', headerBg: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)' },
  { key: 'review', label: 'На проверке', color: '#a855f7', bg: 'rgba(168,85,247,0.08)', headerBg: 'linear-gradient(135deg, #a855f7 0%, #7c3aed 100%)' },
  { key: 'done', label: 'Готово', color: '#22c55e', bg: 'rgba(34,197,94,0.08)', headerBg: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)' },
];

const priorityOptions = [
  { value: 'low', label: 'Низкий', color: 'default', dotColor: '#64748b' },
  { value: 'normal', label: 'Обычный', color: 'primary', dotColor: '#3b82f6' },
  { value: 'high', label: 'Высокий', color: 'warning', dotColor: '#f59e0b' },
  { value: 'urgent', label: 'Срочный', color: 'error', dotColor: '#ef4444' },
];

const dueStateOptions = [
  { value: '', label: 'Любой срок' },
  { value: 'overdue', label: 'Просрочено' },
  { value: 'today', label: 'На сегодня' },
  { value: 'upcoming', label: 'Предстоящие' },
  { value: 'none', label: 'Без срока' },
];

const statusMeta = (status) => {
  const n = String(status || '').toLowerCase();
  const col = KANBAN_COLUMNS.find((c) => c.key === n);
  if (col) return { label: col.label, color: n === 'new' ? 'primary' : n === 'in_progress' ? 'warning' : n === 'review' ? 'secondary' : 'success' };
  return { label: n || '-', color: 'default' };
};

const priorityMeta = (priority) => {
  const found = priorityOptions.find((p) => p.value === String(priority || '').toLowerCase());
  return found || priorityOptions[1];
};

const formatDateTime = (value) => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const formatShortDate = (value) => {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
};

const formatFileSize = (bytes) => {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const getInitials = (name) => {
  if (!name) return '?';
  const parts = String(name).trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return parts[0].slice(0, 2).toUpperCase();
};

/* ──────────────── Styles ──────────────── */
const taskCard = {
  bgcolor: 'background.paper',
  border: '1px solid', borderColor: 'divider',
  borderRadius: '10px',
  transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
  cursor: 'pointer',
  '&:hover': { borderColor: 'action.selected', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
};

const columnScroll = {
  overflowY: 'auto',
  overflowX: 'hidden',
  pr: 0.5,
  '&::-webkit-scrollbar': { width: '4px' },
  '&::-webkit-scrollbar-track': { background: 'transparent' },
  '&::-webkit-scrollbar-thumb': { background: 'rgba(128,128,128,0.3)', borderRadius: '4px' },
  '&::-webkit-scrollbar-thumb:hover': { background: 'rgba(128,128,128,0.5)' },
};

/* ──────────────── Component ──────────────── */
function Tasks() {
  const location = useLocation();
  const { user, hasPermission } = useAuth();
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin';
  const canWriteTasks = hasPermission('tasks.write');
  const canReviewTasks = hasPermission('tasks.review');
  const canUseCreatorTab = canWriteTasks;
  const canUseControllerTab = canWriteTasks && canReviewTasks;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tasksPayload, setTasksPayload] = useState({ items: [], total: 0 });
  const [viewMode, setViewMode] = useState(() => (isAdmin ? 'all' : 'assignee'));
  const [statusFilter, setStatusFilter] = useState('');
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [dueState, setDueState] = useState('');
  const [hasAttachments, setHasAttachments] = useState(false);
  const [sort, setSort] = useState('status:asc');
  const [detailsTaskId, setDetailsTaskId] = useState('');
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const [assignees, setAssignees] = useState([]);
  const [controllers, setControllers] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [createSaving, setCreateSaving] = useState(false);
  const [createData, setCreateData] = useState({
    title: '', description: '', assignee_user_ids: [], controller_user_id: '', due_at: '', priority: 'normal',
  });
  const [submitTask, setSubmitTask] = useState(null);
  const [submitComment, setSubmitComment] = useState('');
  const [submitFile, setSubmitFile] = useState(null);
  const [submitSaving, setSubmitSaving] = useState(false);
  const [reviewTask, setReviewTask] = useState(null);
  const [reviewComment, setReviewComment] = useState('');

  const [editOpen, setEditOpen] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editData, setEditData] = useState({ title: '', description: '', due_at: '', priority: 'normal' });

  const [uploadingAttachment, setUploadingAttachment] = useState(false);

  const selectedTaskId = useMemo(() => {
    const params = new URLSearchParams(location.search || '');
    return String(params.get('task') || '').trim();
  }, [location.search]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(String(q || '').trim()), 250);
    return () => clearTimeout(timer);
  }, [q]);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [sortBy, sortDir] = String(sort || 'status:asc').split(':');
      const scope = viewMode === 'all' ? 'all' : 'my';
      const roleScope = viewMode === 'all' ? 'both' : viewMode;
      const response = await hubAPI.getTasks({
        scope,
        role_scope: roleScope,
        status: statusFilter || undefined,
        q: debouncedQ || undefined,
        assignee_user_id: viewMode === 'all' && assigneeFilter ? Number(assigneeFilter) : undefined,
        has_attachments: hasAttachments || undefined,
        due_state: dueState || undefined,
        sort_by: sortBy || 'status',
        sort_dir: sortDir || 'asc',
        limit: 500,
      });
      setTasksPayload(response || { items: [], total: 0 });
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Ошибка загрузки задач');
    } finally {
      setLoading(false);
    }
  }, [viewMode, statusFilter, debouncedQ, assigneeFilter, hasAttachments, dueState, sort]);

  const loadTaskUsers = useCallback(async () => {
    if (!canWriteTasks) return;
    try {
      const [a, c] = await Promise.all([hubAPI.getAssignees(), hubAPI.getControllers()]);
      setAssignees(Array.isArray(a?.items) ? a.items : []);
      setControllers(Array.isArray(c?.items) ? c.items : []);
    } catch {
      setAssignees([]);
      setControllers([]);
    }
  }, [canWriteTasks]);

  useEffect(() => {
    if (!selectedTaskId) return;
    if (isAdmin) setViewMode('all');
    else if (canUseControllerTab) setViewMode('controller');
    else setViewMode('assignee');
    setDetailsTaskId(selectedTaskId);
    setDetailsOpen(true);
  }, [selectedTaskId, isAdmin, canUseControllerTab]);

  useEffect(() => {
    if (isAdmin) setViewMode((p) => (p === 'assignee' ? 'all' : p));
  }, [isAdmin]);

  useEffect(() => {
    setViewMode((p) => {
      if (p === 'all' && !isAdmin) return 'assignee';
      if (p === 'creator' && !canUseCreatorTab) return 'assignee';
      if (p === 'controller' && !canUseControllerTab) return 'assignee';
      return p;
    });
  }, [isAdmin, canUseCreatorTab, canUseControllerTab]);

  useEffect(() => {
    if (viewMode !== 'all' && assigneeFilter) setAssigneeFilter('');
  }, [viewMode, assigneeFilter]);

  useEffect(() => { loadTasks(); }, [loadTasks]);
  useEffect(() => { loadTaskUsers(); }, [loadTaskUsers]);

  const transformTaskMarkdown = useCallback(async (text, context) => {
    try { return await hubAPI.transformMarkdown({ text, context }); }
    catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === 'string' ? d : (err?.message || 'Ошибка'));
      throw err;
    }
  }, []);

  const taskItems = Array.isArray(tasksPayload?.items) ? tasksPayload.items : [];

  /* ── Kanban columns data ── */
  const columnData = useMemo(() => {
    const map = {};
    KANBAN_COLUMNS.forEach((col) => { map[col.key] = []; });
    taskItems.forEach((t) => {
      const s = String(t?.status || '').toLowerCase();
      if (map[s]) map[s].push(t);
      else if (map.new) map.new.push(t); // fallback
    });
    return map;
  }, [taskItems]);

  const detailsTask = useMemo(() => {
    const activeId = String(detailsTaskId || '').trim();
    if (!activeId) return null;
    return taskItems.find((item) => String(item?.id || '') === activeId) || null;
  }, [taskItems, detailsTaskId]);

  const openTasksCount = useMemo(
    () => taskItems.filter((i) => String(i?.status || '').toLowerCase() !== 'done').length,
    [taskItems],
  );

  const openTaskDetails = useCallback((item) => {
    const id = String(item?.id || '').trim();
    if (!id) return;
    setDetailsTaskId(id);
    setDetailsOpen(true);
  }, []);

  /* ── Handlers ── */
  const handleCreateTask = async () => {
    const selA = Array.isArray(createData.assignee_user_ids) ? createData.assignee_user_ids : [];
    const selC = Number(createData.controller_user_id || 0);
    if (String(createData.title || '').trim().length < 3 || selA.length === 0 || selC <= 0) return;
    setCreateSaving(true);
    try {
      await hubAPI.createTask({
        title: String(createData.title || '').trim(),
        description: String(createData.description || '').trim(),
        assignee_user_ids: selA.map(Number).filter(Number.isInteger),
        controller_user_id: selC,
        due_at: String(createData.due_at || '').trim() || null,
        priority: createData.priority || 'normal',
      });
      setCreateOpen(false);
      setCreateData({ title: '', description: '', assignee_user_ids: [], controller_user_id: '', due_at: '', priority: 'normal' });
      await loadTasks();
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
    finally { setCreateSaving(false); }
  };

  const handleReviewTask = async (decision) => {
    if (!reviewTask?.id) return;
    try {
      await hubAPI.reviewTask(reviewTask.id, { decision, comment: reviewComment });
      setReviewTask(null); setReviewComment('');
      await loadTasks();
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
  };

  const handleStartTask = async (taskId) => {
    try {
      await hubAPI.startTask(taskId);
      await loadTasks();
      window.dispatchEvent(new CustomEvent('hub-refresh-notifications'));
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
  };

  const handleSubmitTask = async () => {
    if (!submitTask?.id) return;
    setSubmitSaving(true);
    try {
      await hubAPI.submitTask({ taskId: submitTask.id, comment: submitComment, file: submitFile || null });
      setSubmitTask(null); setSubmitComment(''); setSubmitFile(null);
      await loadTasks();
      window.dispatchEvent(new CustomEvent('hub-refresh-notifications'));
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
    finally { setSubmitSaving(false); }
  };

  const handleDeleteTask = async (task) => {
    if (!task?.id) return;
    if (!window.confirm(`Удалить "${task?.title || 'задачу'}"?`)) return;
    try {
      await hubAPI.deleteTask(task.id);
      if (String(detailsTaskId || '') === String(task.id)) { setDetailsOpen(false); setDetailsTaskId(''); }
      await loadTasks();
      window.dispatchEvent(new CustomEvent('hub-refresh-notifications'));
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
  };

  const openEditTask = (task) => {
    setEditData({
      title: task?.title || '', description: task?.description || '',
      due_at: task?.due_at ? String(task.due_at).slice(0, 16) : '', priority: task?.priority || 'normal',
    });
    setEditOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!detailsTask?.id) return;
    setEditSaving(true);
    try {
      await hubAPI.updateTask(detailsTask.id, {
        title: String(editData.title || '').trim(),
        description: String(editData.description || '').trim(),
        due_at: String(editData.due_at || '').trim() || null,
      });
      setEditOpen(false);
      await loadTasks();
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
    finally { setEditSaving(false); }
  };

  const handleUploadAttachment = async (taskId, file) => {
    if (!taskId || !file) return;
    setUploadingAttachment(true);
    try { await hubAPI.uploadTaskAttachment({ taskId, file }); await loadTasks(); }
    catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
    finally { setUploadingAttachment(false); }
  };

  const handleDownloadAttachment = async (task, attachment) => {
    try {
      const r = await hubAPI.downloadTaskAttachment({ taskId: task.id, attachmentId: attachment.id });
      const blob = r.data || r;
      const url = window.URL.createObjectURL(blob instanceof Blob ? blob : new Blob([blob]));
      const a = document.createElement('a'); a.href = url; a.download = attachment.file_name || 'file';
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
  };

  const handleDownloadReport = async (report) => {
    if (!report?.id || !report?.file_name) return;
    try {
      const r = await hubAPI.downloadTaskReport(report.id);
      const blob = r.data || r;
      const url = window.URL.createObjectURL(blob instanceof Blob ? blob : new Blob([blob]));
      const a = document.createElement('a'); a.href = url; a.download = report.file_name || 'report';
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
  };

  const canDeleteTask = (task) => {
    if (!task?.id) return false;
    if (isAdmin) return true;
    return canWriteTasks && Number(task?.created_by_user_id) === Number(user?.id);
  };

  const canEditTask = (task) => {
    if (!task?.id || String(task?.status || '').toLowerCase() === 'done') return false;
    if (isAdmin) return true;
    return canWriteTasks && Number(task?.created_by_user_id) === Number(user?.id);
  };

  /* ══════════════════════════════════════════
     ██  R E N D E R
     ══════════════════════════════════════════ */
  return (
    <MainLayout>
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>

        {/* ── HEADER ── */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <AssignmentIcon sx={{ color: '#3b82f6', fontSize: 28 }} />
            <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>Задачи</Typography>
            <Chip size="small" label={`Открыто: ${openTasksCount}`}
              sx={{ fontWeight: 700, bgcolor: openTasksCount > 0 ? 'rgba(59,130,246,0.12)' : 'action.hover', color: openTasksCount > 0 ? 'primary.main' : 'text.secondary', border: 'none' }} />
            <Chip size="small" label={`Всего: ${Number(tasksPayload?.total || 0)}`}
              sx={{ fontWeight: 600, bgcolor: 'action.hover', color: 'text.secondary', border: 'none' }} />
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <Tooltip title="Фильтры">
              <IconButton size="small" onClick={() => setShowFilters((p) => !p)}
                sx={{ bgcolor: showFilters ? 'rgba(59,130,246,0.12)' : 'action.hover', color: showFilters ? 'primary.main' : 'text.secondary' }}>
                <FilterListIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Обновить">
              <IconButton size="small" onClick={loadTasks} sx={{ bgcolor: 'action.hover', color: 'text.secondary' }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            {canWriteTasks && (
              <Button variant="contained" size="small" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}
                sx={{
                  textTransform: 'none', fontWeight: 700, borderRadius: '10px', px: 2,
                  background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                  boxShadow: '0 4px 15px rgba(59,130,246,0.3)',
                  '&:hover': { boxShadow: '0 6px 20px rgba(59,130,246,0.4)' },
                }}>
                Создать задачу
              </Button>
            )}
          </Stack>
        </Box>

        {loading && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} />}
        {error && <Alert severity="error" sx={{ mb: 1, borderRadius: '10px' }} onClose={() => setError('')}>{error}</Alert>}

        {/* ── TABS ── */}
        <Box sx={{ mb: 1.5, bgcolor: 'background.paper', borderRadius: '10px', border: '1px solid', borderColor: 'divider', px: 0.5 }}>
          <Tabs value={viewMode} onChange={(_, v) => setViewMode(v)} variant="scrollable" allowScrollButtonsMobile
            sx={{
              minHeight: 40,
              '& .MuiTab-root': { textTransform: 'none', fontWeight: 600, minHeight: 40, fontSize: '0.85rem' },
              '& .MuiTabs-indicator': { borderRadius: '2px', height: 3 },
            }}>
            {isAdmin && <Tab value="all" label="Все задачи" />}
            <Tab value="assignee" label="Мои задачи" />
            {canUseCreatorTab && <Tab value="creator" label="Созданные мной" />}
            {canUseControllerTab && <Tab value="controller" label="Контроль" />}
          </Tabs>
        </Box>

        {/* ── FILTERS (collapsible) ── */}
        {showFilters && (
          <Box sx={{ mb: 1.5, p: 1.5, bgcolor: 'action.hover', borderRadius: '10px', border: '1px solid', borderColor: 'divider' }}>
            <Grid container spacing={1.5}>
              <Grid item xs={12} sm={6} md={3}>
                <TextField fullWidth size="small" label="Поиск" value={q} onChange={(e) => setQ(e.target.value)}
                  InputProps={{ startAdornment: <SearchIcon sx={{ mr: 0.5, color: 'text.secondary', fontSize: 18 }} /> }} />
              </Grid>
              <Grid item xs={6} sm={3} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Срок</InputLabel>
                  <Select value={dueState} label="Срок" onChange={(e) => setDueState(e.target.value)}>
                    {dueStateOptions.map((o) => <MenuItem key={o.value || 'all'} value={o.value}>{o.label}</MenuItem>)}
                  </Select>
                </FormControl>
              </Grid>
              {isAdmin && viewMode === 'all' && (
                <Grid item xs={6} sm={3} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Исполнитель</InputLabel>
                    <Select value={assigneeFilter} label="Исполнитель" onChange={(e) => setAssigneeFilter(e.target.value)}>
                      <MenuItem value="">Все</MenuItem>
                      {assignees.map((i) => <MenuItem key={i.id} value={String(i.id)}>{i.full_name || i.username}</MenuItem>)}
                    </Select>
                  </FormControl>
                </Grid>
              )}
              <Grid item xs={6} sm={3} md={2}>
                <FormControlLabel control={<Checkbox size="small" checked={hasAttachments} onChange={(e) => setHasAttachments(e.target.checked)} />} label="С файлами" />
              </Grid>
            </Grid>
          </Box>
        )}

        {/* ══════════════════════════════════════
           ██  K A N B A N   B O A R D
           ══════════════════════════════════════ */}
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 1.5,
          flex: 1,
          minHeight: 0,
        }}>
          {KANBAN_COLUMNS.map((col) => {
            const items = columnData[col.key] || [];
            return (
              <Box key={col.key} sx={{
                display: 'flex', flexDirection: 'column',
                bgcolor: col.bg, borderRadius: '10px',
                border: '1px solid', borderColor: 'divider',
                overflow: 'hidden',
                maxHeight: { xs: 'none', lg: 'calc(100vh - 230px)' },
              }}>
                {/* Column Header */}
                <Box sx={{
                  background: col.headerBg, px: 1.5, py: 1,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <Typography sx={{ fontWeight: 800, fontSize: '0.85rem', color: '#fff', letterSpacing: '0.02em' }}>
                    {col.label}
                  </Typography>
                  <Chip size="small" label={items.length}
                    sx={{ fontWeight: 800, bgcolor: 'rgba(255,255,255,0.2)', color: '#fff', height: 22, fontSize: '0.75rem', minWidth: 28 }} />
                </Box>

                {/* Column Body */}
                <Box sx={{ p: 1, flex: 1, ...columnScroll }}>
                  <Stack spacing={1}>
                    {items.length === 0 ? (
                      <Typography variant="caption" sx={{ color: 'text.disabled', textAlign: 'center', py: 3 }}>
                        Нет задач
                      </Typography>
                    ) : (
                      items.map((task) => {
                        const pm = priorityMeta(task?.priority);
                        const attachCount = Number(task?.attachments_count || 0);
                        return (
                          <Box key={task.id} onClick={() => openTaskDetails(task)} sx={{
                            ...taskCard,
                            borderLeft: `3px solid ${task?.is_overdue ? '#ef4444' : col.color}`,
                            p: 1.2,
                          }}>
                            {/* Title row */}
                            <Typography sx={{
                              fontWeight: 700, fontSize: '0.82rem', lineHeight: 1.3,
                              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                              color: 'text.primary',
                            }}>
                              {task?.title || '-'}
                            </Typography>

                            {/* Tags row */}
                            <Stack direction="row" spacing={0.4} sx={{ mt: 0.6, flexWrap: 'wrap', gap: 0.3 }}>
                              {task?.is_overdue && (
                                <Chip size="small" label="Просрочено"
                                  sx={{ height: 18, fontSize: '0.65rem', fontWeight: 700, bgcolor: 'rgba(239,68,68,0.15)', color: '#f87171', border: 'none' }} />
                              )}
                              {pm.value !== 'normal' && (
                                <Chip size="small" icon={<FlagIcon sx={{ fontSize: '12px !important', color: `${pm.dotColor} !important` }} />}
                                  label={pm.label}
                                  sx={{ height: 18, fontSize: '0.65rem', fontWeight: 600, bgcolor: `${pm.dotColor}15`, color: pm.dotColor, border: 'none', '& .MuiChip-icon': { ml: '2px' } }} />
                              )}
                              {attachCount > 0 && (
                                <Chip size="small" icon={<AttachFileIcon sx={{ fontSize: '11px !important' }} />} label={attachCount}
                                  sx={{ height: 18, fontSize: '0.65rem', bgcolor: 'action.hover', color: 'text.secondary', border: 'none', '& .MuiChip-icon': { ml: '2px' } }} />
                              )}
                            </Stack>

                            {/* Bottom row */}
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 0.8 }}>
                              <Stack direction="row" spacing={0.5} alignItems="center">
                                <Avatar sx={{
                                  width: 22, height: 22, fontSize: '0.6rem', fontWeight: 700,
                                  bgcolor: `${col.color}30`, color: col.color,
                                }}>
                                  {getInitials(task?.assignee_full_name || task?.assignee_username)}
                                </Avatar>
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem', maxWidth: 100, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {(task?.assignee_full_name || task?.assignee_username || '').split(' ').slice(0, 2).join(' ')}
                                </Typography>
                              </Stack>
                              {task?.due_at && (
                                <Stack direction="row" spacing={0.3} alignItems="center">
                                  <AccessTimeIcon sx={{ fontSize: 12, color: task?.is_overdue ? '#ef4444' : 'text.disabled' }} />
                                  <Typography variant="caption" sx={{ fontSize: '0.65rem', color: task?.is_overdue ? '#ef4444' : 'text.disabled', fontWeight: task?.is_overdue ? 700 : 400 }}>
                                    {formatShortDate(task.due_at)}
                                  </Typography>
                                </Stack>
                              )}
                            </Stack>
                          </Box>
                        );
                      })
                    )}
                  </Stack>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* ══════════════════════════════════════
         ██  D I A L O G S
         ══════════════════════════════════════ */}

      {/* ── DETAILS ── */}
      <Dialog open={detailsOpen} onClose={() => setDetailsOpen(false)} fullWidth maxWidth="md"
        PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 700 }}>
          {detailsTask?.title || 'Карточка'}
          {canEditTask(detailsTask) && (
            <Tooltip title="Редактировать">
              <IconButton size="small" onClick={() => openEditTask(detailsTask)} sx={{ color: 'primary.main' }}><EditIcon fontSize="small" /></IconButton>
            </Tooltip>
          )}
        </DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          {detailsTask ? (
            <Stack spacing={1.5}>
              <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                <Chip size="small" color={statusMeta(detailsTask?.status).color} label={statusMeta(detailsTask?.status).label} />
                {detailsTask?.is_overdue && <Chip size="small" color="error" label="Просрочено" />}
                {detailsTask?.priority && detailsTask.priority !== 'normal' && (
                  <Chip size="small" icon={<FlagIcon />} color={priorityMeta(detailsTask.priority).color} label={priorityMeta(detailsTask.priority).label} />
                )}
                <Chip size="small" variant="outlined" label={`Срок: ${formatDateTime(detailsTask?.due_at)}`} />
                <Chip size="small" variant="outlined" label={`Обновлено: ${formatDateTime(detailsTask?.updated_at || detailsTask?.created_at)}`} />
              </Stack>

              <Box sx={{ p: 1.2, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid', borderColor: 'divider' }}>
                <Grid container spacing={1}>
                  <Grid item xs={12} sm={4}>
                    <Stack direction="row" spacing={0.8} alignItems="center">
                      <Avatar sx={{ width: 28, height: 28, fontSize: '0.7rem', bgcolor: 'rgba(59,130,246,0.2)', color: '#60a5fa' }}>
                        {getInitials(detailsTask?.assignee_full_name)}
                      </Avatar>
                      <Box>
                        <Typography variant="caption" sx={{ color: '#64748b', display: 'block', lineHeight: 1 }}>Исполнитель</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                          {detailsTask?.assignee_full_name || detailsTask?.assignee_username || '-'}
                        </Typography>
                      </Box>
                    </Stack>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Typography variant="caption" sx={{ color: '#64748b' }}>Постановщик</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                      {detailsTask?.created_by_full_name || detailsTask?.created_by_username || '-'}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Typography variant="caption" sx={{ color: '#64748b' }}>Контроллер</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                      {detailsTask?.controller_full_name || detailsTask?.controller_username || '-'}
                    </Typography>
                  </Grid>
                </Grid>
              </Box>

              <MarkdownRenderer value={detailsTask?.description || ''} />

              {/* Attachments */}
              {(() => {
                const atts = Array.isArray(detailsTask?.attachments) ? detailsTask.attachments : [];
                const report = detailsTask?.latest_report || null;
                if (atts.length === 0 && !report) return null;
                return (
                  <>
                    <Divider sx={{ borderColor: 'divider' }} />
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      <AttachFileIcon sx={{ fontSize: 16, mr: 0.5, verticalAlign: 'text-bottom' }} />
                      Файлы ({atts.length})
                    </Typography>
                    {atts.length > 0 && (
                      <List dense disablePadding>
                        {atts.map((att) => (
                          <ListItem key={att.id} disableGutters secondaryAction={
                            <Tooltip title="Скачать"><IconButton size="small" onClick={() => handleDownloadAttachment(detailsTask, att)}><DownloadIcon fontSize="small" /></IconButton></Tooltip>
                          }>
                            <ListItemIcon sx={{ minWidth: 32 }}><DescriptionIcon fontSize="small" color="action" /></ListItemIcon>
                            <ListItemText primary={att.file_name || 'file'} secondary={`${formatFileSize(att.file_size)} · ${att.scope === 'report' ? 'Отчёт' : 'Вложение'} · ${formatDateTime(att.uploaded_at)}`} />
                          </ListItem>
                        ))}
                      </List>
                    )}
                    {report && (
                      <Box sx={{ p: 1, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid', borderColor: 'divider' }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b' }}>Последний отчёт:</Typography>
                        {report.comment && <Typography variant="body2" sx={{ mt: 0.3 }}>{report.comment}</Typography>}
                        {report.file_name && (
                          <Button size="small" startIcon={<DownloadIcon />} onClick={() => handleDownloadReport(report)} sx={{ mt: 0.3 }}>{report.file_name}</Button>
                        )}
                        <Typography variant="caption" color="text.secondary" display="block">
                          {formatDateTime(report.uploaded_at)} — {report.uploaded_by_username || ''}
                        </Typography>
                      </Box>
                    )}
                  </>
                );
              })()}

              {/* Upload */}
              {(Number(detailsTask?.assignee_user_id) === Number(user?.id) || Number(detailsTask?.created_by_user_id) === Number(user?.id) || Number(detailsTask?.controller_user_id) === Number(user?.id)) && String(detailsTask?.status || '').toLowerCase() !== 'done' && (
                <Button size="small" variant="outlined" component="label" startIcon={<AttachFileIcon />} disabled={uploadingAttachment}
                  sx={{ borderRadius: '10px', textTransform: 'none' }}>
                  {uploadingAttachment ? 'Загрузка...' : 'Прикрепить файл'}
                  <input type="file" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadAttachment(detailsTask.id, f); e.target.value = ''; }} />
                </Button>
              )}

              {/* Actions */}
              <Stack direction="row" spacing={0.8} flexWrap="wrap" sx={{ mt: 0.5 }}>
                {Number(detailsTask?.assignee_user_id) === Number(user?.id) && String(detailsTask?.status || '').toLowerCase() === 'new' && (
                  <Button size="small" variant="outlined" onClick={() => handleStartTask(detailsTask.id)}
                    sx={{ borderRadius: '10px', textTransform: 'none', fontWeight: 600 }}>В работу</Button>
                )}
                {Number(detailsTask?.assignee_user_id) === Number(user?.id) && ['new', 'in_progress', 'review'].includes(String(detailsTask?.status || '').toLowerCase()) && (
                  <Button size="small" variant="contained" onClick={() => setSubmitTask(detailsTask)}
                    sx={{ borderRadius: '10px', textTransform: 'none', fontWeight: 600 }}>Сдать работу</Button>
                )}
                {canReviewTasks && Number(detailsTask?.controller_user_id) === Number(user?.id) && String(detailsTask?.status || '').toLowerCase() === 'review' && (
                  <Button size="small" variant="contained" color="secondary" onClick={() => setReviewTask(detailsTask)}
                    sx={{ borderRadius: '10px', textTransform: 'none', fontWeight: 600 }}>Проверить</Button>
                )}
                {canDeleteTask(detailsTask) && (
                  <Button size="small" color="error" startIcon={<DeleteOutlineIcon />} onClick={() => handleDeleteTask(detailsTask)}
                    sx={{ borderRadius: '10px', textTransform: 'none' }}>Удалить</Button>
                )}
              </Stack>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">Карточка недоступна.</Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setDetailsOpen(false)} sx={{ textTransform: 'none' }}>Закрыть</Button>
        </DialogActions>
      </Dialog>

      {/* ══════════════════════════════════════
         ██  C R E A T E   T A S K
         ══════════════════════════════════════ */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="md"
        PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px', overflow: 'hidden' } }}>

        {/* Header with gradient */}
        <Box sx={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%)',
          px: 3, py: 2,
          borderBottom: '1px solid', borderColor: 'divider',
        }}>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box sx={{
              width: 40, height: 40, borderRadius: '12px',
              background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 15px rgba(59,130,246,0.3)',
            }}>
              <AddIcon sx={{ color: '#fff', fontSize: 22 }} />
            </Box>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.2 }}>
                Создать задачу
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Заполните информацию о новой задаче
              </Typography>
            </Box>
          </Stack>

          {/* Progress indicator */}
          {(() => {
            const steps = [
              String(createData.title || '').trim().length >= 3,
              (Array.isArray(createData.assignee_user_ids) ? createData.assignee_user_ids : []).length > 0,
              Number(createData.controller_user_id || 0) > 0,
            ];
            const done = steps.filter(Boolean).length;
            return (
              <Box sx={{ mt: 1.5 }}>
                <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }}>
                  {['Заголовок', 'Исполнители', 'Контроллер'].map((label, i) => (
                    <Chip key={label} size="small" label={label}
                      sx={{
                        height: 20, fontSize: '0.65rem', fontWeight: 600,
                        bgcolor: steps[i] ? 'rgba(34,197,94,0.15)' : 'action.hover',
                        color: steps[i] ? '#16a34a' : 'text.disabled', border: 'none',
                        transition: 'all 0.3s ease',
                      }} />
                  ))}
                </Stack>
                <LinearProgress variant="determinate" value={(done / 3) * 100}
                  sx={{
                    height: 3, borderRadius: 2, bgcolor: 'action.hover',
                    '& .MuiLinearProgress-bar': {
                      borderRadius: 2,
                      background: done === 3
                        ? 'linear-gradient(90deg, #22c55e, #16a34a)'
                        : 'linear-gradient(90deg, #3b82f6, #60a5fa)',
                      transition: 'all 0.5s ease',
                    },
                  }} />
              </Box>
            );
          })()}
        </Box>

        <DialogContent sx={{ px: 3, py: 2.5 }}>
          <Stack spacing={2.5}>

            {/* ── Section: Title ── */}
            <Box>
              <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 1 }}>
                <AssignmentIcon sx={{ fontSize: 18, color: '#3b82f6' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
                  Название
                </Typography>
              </Stack>
              <TextField
                fullWidth size="small"
                placeholder="Введите название задачи..."
                value={createData.title}
                onChange={(e) => setCreateData((p) => ({ ...p, title: e.target.value }))}
                error={createData.title.length > 0 && createData.title.trim().length < 3}
                helperText={createData.title.length > 0 && createData.title.trim().length < 3 ? 'Минимум 3 символа' : ''}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    borderRadius: '10px', fontSize: '1rem', fontWeight: 600,
                    bgcolor: 'action.hover',
                  },
                }}
              />
            </Box>

            {/* ── Section: Description ── */}
            <Box>
              <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 1 }}>
                <DescriptionIcon sx={{ fontSize: 18, color: '#a855f7' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
                  Описание
                </Typography>
                <Chip size="small" label="Markdown" sx={{ height: 18, fontSize: '0.6rem', bgcolor: 'rgba(168,85,247,0.12)', color: '#c084fc', border: 'none' }} />
              </Stack>
              <MarkdownEditor
                label=""
                value={createData.description}
                onChange={(v) => setCreateData((p) => ({ ...p, description: v }))}
                minRows={5}
                placeholder="Опишите задачу... Можно использовать списки, таблицы и чекбоксы."
                enableAiTransform transformContext="task" onAiTransform={transformTaskMarkdown}
              />
            </Box>

            <Divider sx={{ borderColor: 'divider' }} />

            {/* ── Section: People ── */}
            <Box>
              <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 1.2 }}>
                <PersonOutlineIcon sx={{ fontSize: 18, color: '#f59e0b' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
                  Участники
                </Typography>
              </Stack>

              <Grid container spacing={2}>
                {/* Assignees */}
                <Grid item xs={12} md={7}>
                  <Box sx={{ p: 1.5, borderRadius: '12px', bgcolor: 'action.hover', border: '1px solid', borderColor: 'divider' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.8 }}>
                      Исполнители {createData.assignee_user_ids.length > 0 && (
                        <Chip size="small" label={createData.assignee_user_ids.length} sx={{ height: 16, fontSize: '0.6rem', ml: 0.5, bgcolor: 'rgba(59,130,246,0.12)', color: 'primary.main', border: 'none' }} />
                      )}
                    </Typography>

                    {/* Selected assignees as chips */}
                    {createData.assignee_user_ids.length > 0 && (
                      <Stack direction="row" flexWrap="wrap" sx={{ gap: 0.5, mb: 1 }}>
                        {createData.assignee_user_ids.map((uid) => {
                          const u = assignees.find((a) => String(a.id) === String(uid));
                          if (!u) return null;
                          const name = u.full_name || u.username;
                          return (
                            <Chip key={uid} size="small"
                              avatar={<Avatar sx={{ width: 20, height: 20, fontSize: '0.55rem', bgcolor: 'primary.light', color: 'primary.contrastText' }}>{getInitials(name)}</Avatar>}
                              label={name.split(' ').slice(0, 2).join(' ')}
                              onDelete={() => setCreateData((p) => ({ ...p, assignee_user_ids: p.assignee_user_ids.filter((id) => id !== uid) }))}
                              sx={{
                                height: 26, fontSize: '0.72rem', fontWeight: 600,
                                bgcolor: 'rgba(59,130,246,0.08)', color: 'primary.main',
                                border: '1px solid rgba(59,130,246,0.15)',
                                '& .MuiChip-deleteIcon': { color: 'primary.main', fontSize: 14, '&:hover': { color: '#ef4444' } },
                              }}
                            />
                          );
                        })}
                      </Stack>
                    )}

                    <FormControl fullWidth size="small">
                      <Select
                        multiple displayEmpty
                        value={Array.isArray(createData.assignee_user_ids) ? createData.assignee_user_ids : []}
                        onChange={(e) => setCreateData((p) => ({ ...p, assignee_user_ids: Array.isArray(e.target.value) ? e.target.value : [] }))}
                        renderValue={() => (createData.assignee_user_ids.length === 0 ? <Typography variant="body2" sx={{ color: 'text.disabled' }}>Выберите исполнителей...</Typography> : <Typography variant="body2" sx={{ color: 'text.secondary' }}>Добавить ещё...</Typography>)}
                        sx={{ borderRadius: '8px' }}
                      >
                        {assignees.map((i) => (
                          <MenuItem key={i.id} value={String(i.id)} sx={{ py: 0.5 }}>
                            <Checkbox size="small" checked={Array.isArray(createData.assignee_user_ids) && createData.assignee_user_ids.includes(String(i.id))} />
                            <Avatar sx={{ width: 24, height: 24, fontSize: '0.6rem', mr: 1, bgcolor: 'primary.light', color: 'primary.contrastText' }}>
                              {getInitials(i.full_name || i.username)}
                            </Avatar>
                            <Box>
                              <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>{i.full_name || i.username}</Typography>
                              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>{i.username}</Typography>
                            </Box>
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Box>
                </Grid>

                {/* Controller */}
                <Grid item xs={12} md={5}>
                  <Box sx={{ p: 1.5, borderRadius: '12px', bgcolor: 'action.hover', border: '1px solid', borderColor: 'divider', height: '100%' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.8 }}>
                      Контроллер
                    </Typography>

                    {/* Selected controller preview */}
                    {Number(createData.controller_user_id || 0) > 0 && (() => {
                      const ctrl = controllers.find((c) => String(c.id) === String(createData.controller_user_id));
                      if (!ctrl) return null;
                      const name = ctrl.full_name || ctrl.username;
                      return (
                        <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 1, p: 0.8, borderRadius: '8px', bgcolor: 'rgba(168,85,247,0.08)', border: '1px solid rgba(168,85,247,0.15)' }}>
                          <Avatar sx={{ width: 28, height: 28, fontSize: '0.65rem', bgcolor: 'rgba(168,85,247,0.25)', color: '#c084fc' }}>
                            {getInitials(name)}
                          </Avatar>
                          <Box sx={{ flex: 1 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem', lineHeight: 1.2 }}>{name}</Typography>
                            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>{ctrl.username}</Typography>
                          </Box>
                        </Stack>
                      );
                    })()}

                    <FormControl fullWidth size="small">
                      <Select
                        displayEmpty
                        value={String(createData.controller_user_id || '')}
                        onChange={(e) => setCreateData((p) => ({ ...p, controller_user_id: String(e.target.value || '') }))}
                        renderValue={(v) => {
                          if (!v) return <Typography variant="body2" sx={{ color: 'text.disabled' }}>Выберите контроллера...</Typography>;
                          return null;
                        }}
                        sx={{ borderRadius: '8px' }}
                      >
                        {controllers.map((i) => (
                          <MenuItem key={i.id} value={String(i.id)} sx={{ py: 0.5 }}>
                            <Avatar sx={{ width: 24, height: 24, fontSize: '0.6rem', mr: 1, bgcolor: 'rgba(168,85,247,0.2)', color: '#c084fc' }}>
                              {getInitials(i.full_name || i.username)}
                            </Avatar>
                            <Box>
                              <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>{i.full_name || i.username}</Typography>
                              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>{i.username}</Typography>
                            </Box>
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Box>
                </Grid>
              </Grid>
            </Box>

            <Divider sx={{ borderColor: 'divider' }} />

            {/* ── Section: Settings ── */}
            <Box>
              <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 1.2 }}>
                <AccessTimeIcon sx={{ fontSize: 18, color: '#22c55e' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
                  Параметры
                </Typography>
              </Stack>

              <Grid container spacing={2}>
                {/* Due date */}
                <Grid item xs={12} md={6}>
                  <Box sx={{ p: 1.5, borderRadius: '12px', bgcolor: 'action.hover', border: '1px solid', borderColor: 'divider' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.8 }}>
                      Срок выполнения
                    </Typography>
                    <TextField
                      fullWidth size="small" type="datetime-local"
                      value={createData.due_at}
                      onChange={(e) => setCreateData((p) => ({ ...p, due_at: e.target.value }))}
                      InputLabelProps={{ shrink: true }}
                      sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
                    />
                  </Box>
                </Grid>

                {/* Priority visual selector */}
                <Grid item xs={12} md={6}>
                  <Box sx={{ p: 1.5, borderRadius: '12px', bgcolor: 'action.hover', border: '1px solid', borderColor: 'divider' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 0.8 }}>
                      Приоритет
                    </Typography>
                    <Stack direction="row" spacing={0.6}>
                      {priorityOptions.map((p) => {
                        const isSelected = (createData.priority || 'normal') === p.value;
                        return (
                          <Box key={p.value} onClick={() => setCreateData((prev) => ({ ...prev, priority: p.value }))}
                            sx={{
                              flex: 1, py: 0.8, px: 0.5,
                              borderRadius: '8px', textAlign: 'center', cursor: 'pointer',
                              border: '1.5px solid', borderColor: isSelected ? p.dotColor : 'divider',
                              bgcolor: isSelected ? `${p.dotColor}15` : 'transparent',
                              transition: 'all 0.2s ease',
                              '&:hover': { bgcolor: `${p.dotColor}10`, borderColor: `${p.dotColor}80` },
                            }}>
                            <FlagIcon sx={{ fontSize: 16, color: isSelected ? p.dotColor : 'text.disabled', mb: 0.2, display: 'block', mx: 'auto' }} />
                            <Typography sx={{
                              fontSize: '0.65rem', fontWeight: isSelected ? 700 : 500,
                              color: isSelected ? p.dotColor : 'text.secondary',
                            }}>
                              {p.label}
                            </Typography>
                          </Box>
                        );
                      })}
                    </Stack>
                  </Box>
                </Grid>
              </Grid>
            </Box>
          </Stack>
        </DialogContent>

        {/* Footer */}
        <Box sx={{ px: 3, py: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid', borderColor: 'divider' }}>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {(() => {
              const a = Array.isArray(createData.assignee_user_ids) ? createData.assignee_user_ids : [];
              if (a.length > 1) return `Будет создано ${a.length} задач (по одной на исполнителя)`;
              return '';
            })()}
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button onClick={() => setCreateOpen(false)} disabled={createSaving}
              sx={{ textTransform: 'none', color: 'text.secondary', borderRadius: '10px' }}>
              Отмена
            </Button>
            <Button variant="contained" onClick={handleCreateTask}
              disabled={createSaving || String(createData.title || '').trim().length < 3 || createData.assignee_user_ids.length === 0 || Number(createData.controller_user_id || 0) <= 0}
              sx={{
                textTransform: 'none', fontWeight: 700, borderRadius: '10px', px: 3,
                background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
                boxShadow: '0 4px 15px rgba(59,130,246,0.3)',
                '&:hover': { boxShadow: '0 6px 20px rgba(59,130,246,0.4)' },
                '&.Mui-disabled': { background: 'action.disabledBackground', color: 'action.disabled' },
              }}>
              {createSaving ? 'Создание...' : `Создать${(Array.isArray(createData.assignee_user_ids) ? createData.assignee_user_ids : []).length > 1 ? ` (${createData.assignee_user_ids.length})` : ''}`}
            </Button>
          </Stack>
        </Box>
      </Dialog>

      {/* ── EDIT ── */}
      <Dialog open={editOpen} onClose={() => setEditOpen(false)} fullWidth maxWidth="md"
        PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Редактировать задачу</DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          <Stack spacing={1.2}>
            <TextField size="small" label="Заголовок" value={editData.title} onChange={(e) => setEditData((p) => ({ ...p, title: e.target.value }))} fullWidth />
            <MarkdownEditor label="Описание (Markdown)" value={editData.description}
              onChange={(v) => setEditData((p) => ({ ...p, description: v }))} minRows={6}
              enableAiTransform transformContext="task" onAiTransform={transformTaskMarkdown} />
            <TextField size="small" type="datetime-local" label="Срок" value={editData.due_at}
              onChange={(e) => setEditData((p) => ({ ...p, due_at: e.target.value }))} InputLabelProps={{ shrink: true }} fullWidth />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setEditOpen(false)} disabled={editSaving} sx={{ textTransform: 'none' }}>Отмена</Button>
          <Button variant="contained" onClick={handleSaveEdit} disabled={editSaving || String(editData.title || '').trim().length < 3}
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '10px' }}>
            {editSaving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── REVIEW ── */}
      <Dialog open={Boolean(reviewTask)} onClose={() => setReviewTask(null)} fullWidth maxWidth="sm"
        PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Проверка задачи</DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          <Stack spacing={1.2}>
            <Typography variant="body2">{reviewTask?.title || '-'}</Typography>
            <TextField size="small" label="Комментарий" value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} multiline minRows={3} fullWidth />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setReviewTask(null)} sx={{ textTransform: 'none' }}>Отмена</Button>
          <Button variant="outlined" color="warning" onClick={() => handleReviewTask('reject')} sx={{ textTransform: 'none', borderRadius: '10px' }}>Вернуть</Button>
          <Button variant="contained" color="success" onClick={() => handleReviewTask('approve')} sx={{ textTransform: 'none', borderRadius: '10px', fontWeight: 700 }}>Принять</Button>
        </DialogActions>
      </Dialog>

      {/* ── SUBMIT ── */}
      <Dialog open={Boolean(submitTask)} onClose={() => setSubmitTask(null)} fullWidth maxWidth="sm"
        PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Сдать работу</DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          <Stack spacing={1.2}>
            <Typography variant="body2">{submitTask?.title || '-'}</Typography>
            <TextField size="small" label="Комментарий" value={submitComment} onChange={(e) => setSubmitComment(e.target.value)} multiline minRows={3} fullWidth />
            <Button component="label" size="small" variant="outlined" startIcon={<AttachFileIcon />} sx={{ textTransform: 'none', borderRadius: '10px' }}>
              {submitFile ? submitFile.name : 'Прикрепить файл'}
              <input type="file" hidden onChange={(e) => setSubmitFile(e.target.files?.[0] || null)} />
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => { setSubmitTask(null); setSubmitFile(null); }} disabled={submitSaving} sx={{ textTransform: 'none' }}>Отмена</Button>
          <Button variant="contained" onClick={handleSubmitTask} disabled={submitSaving}
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '10px' }}>
            {submitSaving ? 'Отправка...' : 'Сдать'}
          </Button>
        </DialogActions>
      </Dialog>
    </MainLayout>
  );
}

export default Tasks;
