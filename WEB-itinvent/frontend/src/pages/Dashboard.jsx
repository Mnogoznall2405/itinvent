import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Avatar, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, FormControl, FormControlLabel, Grid, IconButton,
  InputLabel, LinearProgress, List, ListItem, ListItemText, Menu, MenuItem, Select,
  Stack, TextField, Tooltip, Typography,
} from '@mui/material';
import CampaignIcon from '@mui/icons-material/Campaign';
import AssignmentIcon from '@mui/icons-material/Assignment';
import AddIcon from '@mui/icons-material/Add';
import VisibilityIcon from '@mui/icons-material/Visibility';
import DownloadIcon from '@mui/icons-material/Download';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import NotificationsIcon from '@mui/icons-material/Notifications';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import FlagIcon from '@mui/icons-material/Flag';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import SearchIcon from '@mui/icons-material/Search';
import FilterListIcon from '@mui/icons-material/FilterList';
import RefreshIcon from '@mui/icons-material/Refresh';
import DescriptionIcon from '@mui/icons-material/Description';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import MainLayout from '../components/layout/MainLayout';
import { hubAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import MarkdownRenderer from '../components/hub/MarkdownRenderer';
import MarkdownEditor from '../components/hub/MarkdownEditor';

const ANNOUNCEMENTS_LIMIT = 50;
const TASKS_LIMIT = 12;

const announcementPriorityMeta = (p) => {
  const n = String(p || '').toLowerCase();
  if (n === 'high') return { label: 'Высокий', color: '#ef4444', bg: 'rgba(239,68,68,0.12)' };
  if (n === 'low') return { label: 'Низкий', color: '#22c55e', bg: 'rgba(34,197,94,0.12)' };
  return { label: 'Обычный', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' };
};

const statusColors = { new: '#3b82f6', in_progress: '#f59e0b', review: '#a855f7', done: '#22c55e' };
const statusLabels = { new: 'Новое', in_progress: 'В работе', review: 'На проверке', done: 'Готово' };

const fmt = (v) => {
  if (!v) return '-';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};
const fmtSize = (b) => {
  const n = Number(b || 0);
  if (n <= 0) return '-';
  if (n < 1024) return `${n} Б`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} КБ`;
  return `${(n / 1048576).toFixed(1)} МБ`;
};
const initials = (name) => {
  if (!name) return '?';
  const p = String(name).trim().split(/\s+/);
  return p.length >= 2 ? (p[0][0] + p[1][0]).toUpperCase() : p[0].slice(0, 2).toUpperCase();
};

const card = {
  bgcolor: 'background.paper',
  border: '1px solid', borderColor: 'divider', borderRadius: '10px',
  transition: 'border-color 0.15s ease, box-shadow 0.15s ease', cursor: 'pointer',
  '&:hover': { borderColor: 'action.selected', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
};

function Dashboard() {
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const canWriteAnn = hasPermission('announcements.write');
  const canWriteTasks = hasPermission('tasks.write');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [annPayload, setAnnPayload] = useState({ items: [], unread_total: 0, total: 0 });
  const [tasksPayload, setTasksPayload] = useState({ items: [], total: 0 });
  const [counts, setCounts] = useState({ notifications_unread_total: 0, announcements_unread: 0, tasks_open: 0, tasks_new: 0 });
  const [detailsId, setDetailsId] = useState('');
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [readsOpen, setReadsOpen] = useState(false);
  const [readsLoading, setReadsLoading] = useState(false);
  const [readsRows, setReadsRows] = useState([]);
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [hasAtt, setHasAtt] = useState(false);
  const [sortBy, setSortBy] = useState('published_at');
  const [sortDir, setSortDir] = useState('desc');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createPayload, setCreatePayload] = useState({ title: '', preview: '', body: '', priority: 'normal' });
  const [createFiles, setCreateFiles] = useState([]);
  const [createSaving, setCreateSaving] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editId, setEditId] = useState('');
  const [editPayload, setEditPayload] = useState({ title: '', preview: '', body: '', priority: 'normal' });
  const [editSaving, setEditSaving] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [menuItem, setMenuItem] = useState(null);

  useEffect(() => { const t = setTimeout(() => setDebouncedQ(String(q || '').trim()), 250); return () => clearTimeout(t); }, [q]);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [ann, tasks, c] = await Promise.all([
        hubAPI.getAnnouncements({ q: debouncedQ || undefined, priority: priority || undefined, unread_only: unreadOnly || undefined, has_attachments: hasAtt || undefined, sort_by: sortBy, sort_dir: sortDir, limit: ANNOUNCEMENTS_LIMIT }),
        hubAPI.getTasks({ scope: 'my', role_scope: 'assignee', limit: TASKS_LIMIT, sort_by: 'updated_at', sort_dir: 'desc' }),
        hubAPI.getUnreadCounts(),
      ]);
      setAnnPayload(ann || { items: [], unread_total: 0, total: 0 });
      setTasksPayload(tasks || { items: [], total: 0 });
      setCounts(c || {});
    } catch (err) { setError(err?.response?.data?.detail || err?.message || 'Ошибка'); }
    finally { setLoading(false); }
  }, [debouncedQ, priority, unreadOnly, hasAtt, sortBy, sortDir]);

  useEffect(() => { load(); }, [load]);

  const transformMd = useCallback(async (text, context) => {
    try { return await hubAPI.transformMarkdown({ text, context }); }
    catch (err) { setError(err?.response?.data?.detail || err?.message || 'Ошибка'); throw err; }
  }, []);

  const annItems = Array.isArray(annPayload?.items) ? annPayload.items : [];
  const taskItems = Array.isArray(tasksPayload?.items) ? tasksPayload.items : [];
  const unreadAnn = Number(counts?.announcements_unread || annPayload?.unread_total || 0);
  const detailsAnn = useMemo(() => annItems.find((i) => String(i?.id || '') === String(detailsId || '').trim()) || null, [annItems, detailsId]);
  const overdueCount = useMemo(() => taskItems.filter((t) => t?.is_overdue).length, [taskItems]);

  const openDetails = useCallback(async (item) => {
    if (!item?.id) return;
    setDetailsId(String(item.id)); setDetailsOpen(true);
    if (Number(item?.unread || 0) === 1) {
      try { await hubAPI.markAnnouncementRead(item.id); window.dispatchEvent(new CustomEvent('hub-refresh-notifications')); await load(); } catch { }
    }
  }, [load]);

  const downloadBlob = useCallback((r, name) => {
    const blob = new Blob([r.data], { type: r?.headers?.['content-type'] || 'application/octet-stream' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name || 'file';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }, []);

  const downloadAtt = useCallback(async (annId, att) => {
    try { downloadBlob(await hubAPI.downloadAnnouncementAttachment(annId, att.id), att.file_name); } catch { setError('Ошибка скачивания'); }
  }, [downloadBlob]);

  const handleDelete = useCallback(async (item) => {
    if (!item?.id || !window.confirm(`Удалить "${item?.title || ''}"?`)) return;
    try {
      await hubAPI.deleteAnnouncement(item.id);
      if (detailsId === String(item.id)) { setDetailsOpen(false); setDetailsId(''); }
      await load(); window.dispatchEvent(new CustomEvent('hub-refresh-notifications'));
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); }
  }, [detailsId, load]);

  const openMenu = useCallback((e, item) => { e.stopPropagation(); setMenuAnchor(e.currentTarget); setMenuItem(item); }, []);
  const closeMenu = useCallback(() => { setMenuAnchor(null); setMenuItem(null); }, []);

  const handleMenuReads = useCallback(async () => {
    if (!menuItem?.id) return; const item = menuItem; closeMenu();
    setReadsOpen(true); setReadsLoading(true); setReadsRows([]);
    try { const r = await hubAPI.getAnnouncementReads(item.id); setReadsRows(Array.isArray(r?.items) ? r.items : []); } catch { setReadsRows([]); }
    finally { setReadsLoading(false); }
  }, [menuItem, closeMenu]);

  const handleMenuEdit = useCallback(() => {
    if (!menuItem?.id) return; const item = menuItem; closeMenu();
    setEditId(String(item.id)); setEditPayload({ title: item.title || '', preview: item.preview || '', body: item.body || '', priority: item.priority || 'normal' }); setEditOpen(true);
  }, [menuItem, closeMenu]);

  const handleMenuDelete = useCallback(async () => { if (!menuItem?.id) return; const item = menuItem; closeMenu(); await handleDelete(item); }, [menuItem, closeMenu, handleDelete]);

  const handleUpdate = useCallback(async () => {
    const title = String(editPayload.title || '').trim();
    if (!editId || title.length < 3) return; setEditSaving(true);
    try { await hubAPI.updateAnnouncement(editId, { title, preview: editPayload.preview?.trim() || '', body: editPayload.body?.trim() || '', priority: editPayload.priority || 'normal' }); setEditOpen(false); setEditId(''); await load(); }
    catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); } finally { setEditSaving(false); }
  }, [editId, editPayload, load]);

  const handleCreate = useCallback(async () => {
    const title = String(createPayload.title || '').trim();
    if (title.length < 3) return; setCreateSaving(true);
    try {
      await hubAPI.createAnnouncement({ title, preview: createPayload.preview?.trim() || '', body: createPayload.body?.trim() || '', priority: createPayload.priority || 'normal' }, createFiles);
      setCreateOpen(false); setCreatePayload({ title: '', preview: '', body: '', priority: 'normal' }); setCreateFiles([]); await load();
    } catch (err) { setError(err?.response?.data?.detail || 'Ошибка'); } finally { setCreateSaving(false); }
  }, [createFiles, createPayload, load]);

  /* ── STAT CARDS DATA ── */
  const stats = [
    { icon: <CampaignIcon />, label: 'Заметки', value: unreadAnn, sub: 'непрочитано', gradient: 'linear-gradient(135deg, #3b82f6, #2563eb)', shadow: 'rgba(59,130,246,0.3)' },
    { icon: <AssignmentIcon />, label: 'Задачи', value: Number(counts?.tasks_open || 0), sub: 'открыто', gradient: 'linear-gradient(135deg, #f59e0b, #d97706)', shadow: 'rgba(245,158,11,0.3)' },
    { icon: <WarningAmberIcon />, label: 'Просрочено', value: overdueCount, sub: 'задач', gradient: 'linear-gradient(135deg, #ef4444, #dc2626)', shadow: 'rgba(239,68,68,0.3)' },
    { icon: <NotificationsIcon />, label: 'Уведомления', value: Number(counts?.notifications_unread_total || 0), sub: 'новых', gradient: 'linear-gradient(135deg, #a855f7, #7c3aed)', shadow: 'rgba(168,85,247,0.3)' },
  ];

  return (
    <MainLayout>
      <Box>
        {/* ── HEADER ── */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Box sx={{ width: 36, height: 36, borderRadius: '10px', background: 'linear-gradient(135deg, #3b82f6, #2563eb)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(59,130,246,0.3)' }}>
              <CampaignIcon sx={{ color: '#fff', fontSize: 20 }} />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>Центр управления</Typography>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Tooltip title="Обновить"><IconButton size="small" onClick={load} sx={{ bgcolor: 'rgba(255,255,255,0.06)', color: 'text.secondary' }}><RefreshIcon fontSize="small" /></IconButton></Tooltip>
            {canWriteAnn && (
              <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}
                sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '10px', background: 'linear-gradient(135deg, #3b82f6, #2563eb)', boxShadow: '0 4px 15px rgba(59,130,246,0.3)' }}>
                Новая заметка
              </Button>
            )}
          </Stack>
        </Box>

        {loading && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} />}
        {error && <Alert severity="error" sx={{ mb: 1.5, borderRadius: '10px' }} onClose={() => setError('')}>{error}</Alert>}

        {/* ── STAT CARDS ── */}
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          {stats.map((s) => (
            <Grid item xs={6} md={3} key={s.label}>
              <Box sx={{ p: 1.5, borderRadius: '10px', bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 1 }}>
                <Box sx={{ width: 36, height: 36, borderRadius: '10px', background: s.gradient, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, '& svg': { fontSize: 18, color: '#fff' } }}>
                  {s.icon}
                </Box>
                <Box>
                  <Typography sx={{ fontSize: '1.15rem', fontWeight: 700, lineHeight: 1 }}>{s.value}</Typography>
                  <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.68rem' }}>{s.label} · {s.sub}</Typography>
                </Box>
              </Box>
            </Grid>
          ))}
        </Grid>

        {/* ── MAIN CONTENT ── */}
        <Grid container spacing={2}>
          {/* LEFT: Announcements */}
          <Grid item xs={12} md={8}>
            <Box sx={{ mb: 1.5 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Stack direction="row" spacing={0.8} alignItems="center">
                  <CampaignIcon sx={{ fontSize: 18, color: '#3b82f6' }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>Лента заметок</Typography>
                  <Chip size="small" label={`${Number(annPayload?.total || 0)}`} sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700, bgcolor: 'rgba(255,255,255,0.06)', color: '#64748b' }} />
                </Stack>
                <Tooltip title="Фильтры">
                  <IconButton size="small" onClick={() => setShowFilters((p) => !p)} sx={{ bgcolor: showFilters ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.06)', color: showFilters ? '#60a5fa' : 'text.secondary' }}>
                    <FilterListIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>

              {showFilters && (
                <Box sx={{ mb: 1.5, p: 1.5, borderRadius: '10px', bgcolor: 'action.hover', border: '1px solid', borderColor: 'divider' }}>
                  <Grid container spacing={1.5}>
                    <Grid item xs={12} md={4}><TextField fullWidth size="small" placeholder="Поиск..." value={q} onChange={(e) => setQ(e.target.value)} InputProps={{ startAdornment: <SearchIcon sx={{ mr: 0.5, color: 'text.secondary', fontSize: 18 }} /> }} /></Grid>
                    <Grid item xs={6} md={2}>
                      <FormControl fullWidth size="small"><InputLabel>Приоритет</InputLabel>
                        <Select value={priority} label="Приоритет" onChange={(e) => setPriority(e.target.value)}>
                          <MenuItem value="">Все</MenuItem><MenuItem value="low">Низкий</MenuItem><MenuItem value="normal">Обычный</MenuItem><MenuItem value="high">Высокий</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={6} md={2}>
                      <FormControl fullWidth size="small"><InputLabel>Сортировка</InputLabel>
                        <Select value={`${sortBy}:${sortDir}`} label="Сортировка" onChange={(e) => { const [b, d] = String(e.target.value).split(':'); setSortBy(b); setSortDir(d); }}>
                          <MenuItem value="published_at:desc">Новые</MenuItem><MenuItem value="published_at:asc">Старые</MenuItem><MenuItem value="priority:desc">Приоритет</MenuItem><MenuItem value="updated_at:desc">Обновленные</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={6} md={2}><FormControlLabel control={<Checkbox size="small" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />} label="Непрочитанные" /></Grid>
                    <Grid item xs={6} md={2}><FormControlLabel control={<Checkbox size="small" checked={hasAtt} onChange={(e) => setHasAtt(e.target.checked)} />} label="С файлами" /></Grid>
                  </Grid>
                </Box>
              )}

              {annItems.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>Заметки не найдены.</Typography>
              ) : (
                <Grid container spacing={1}>
                  {annItems.map((item) => {
                    const pm = announcementPriorityMeta(item?.priority);
                    const atts = Array.isArray(item?.attachments) ? item.attachments : [];
                    const canManage = canWriteAnn && Number(item?.author_user_id) === Number(user?.id);
                    const unread = Number(item?.unread || 0) === 1;
                    return (
                      <Grid item xs={12} sm={6} key={item.id}>
                        <Box onClick={() => openDetails(item)} sx={{
                          ...card, p: 1.3,
                          borderLeft: `3px solid ${unread ? '#3b82f6' : 'transparent'}`,
                          bgcolor: unread ? 'rgba(59,130,246,0.05)' : 'background.paper',
                        }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                            <Typography sx={{ fontWeight: 700, fontSize: '0.85rem', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', flex: 1 }}>
                              {item.title || '-'}
                            </Typography>
                            {(canWriteAnn || canManage) && (
                              <IconButton size="small" onClick={(e) => openMenu(e, item)} sx={{ ml: 0.5, mt: -0.3 }}><MoreVertIcon sx={{ fontSize: 16 }} /></IconButton>
                            )}
                          </Stack>
                          <Stack direction="row" spacing={0.4} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 0.3 }}>
                            {unread && <Chip size="small" label="Новое" sx={{ height: 18, fontSize: '0.6rem', fontWeight: 700, bgcolor: 'rgba(59,130,246,0.15)', color: '#60a5fa' }} />}
                            <Chip size="small" label={pm.label} sx={{ height: 18, fontSize: '0.6rem', fontWeight: 600, bgcolor: pm.bg, color: pm.color }} />
                            {atts.length > 0 && <Chip size="small" icon={<AttachFileIcon sx={{ fontSize: '11px !important' }} />} label={atts.length} sx={{ height: 18, fontSize: '0.6rem', bgcolor: 'action.hover', color: 'text.secondary' }} />}
                          </Stack>
                          <Typography variant="body2" sx={{ mt: 0.6, color: 'text.secondary', fontSize: '0.78rem', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 32 }}>
                            {item.preview || item.body || '-'}
                          </Typography>
                          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 0.6 }}>
                            <Stack direction="row" spacing={0.5} alignItems="center">
                              <Avatar sx={{ width: 20, height: 20, fontSize: '0.55rem', bgcolor: 'primary.light', color: 'primary.contrastText' }}>{initials(item?.author_full_name)}</Avatar>
                              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>{(item?.author_full_name || '').split(' ').slice(0, 2).join(' ')}</Typography>
                            </Stack>
                            <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem' }}>{fmt(item?.published_at)}</Typography>
                          </Stack>
                        </Box>
                      </Grid>
                    );
                  })}
                </Grid>
              )}
            </Box>
          </Grid>

          {/* RIGHT: My Tasks */}
          <Grid item xs={12} md={4}>
            <Box sx={{ position: 'sticky', top: 80 }}>
              <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mb: 1 }}>
                <AssignmentIcon sx={{ fontSize: 18, color: '#f59e0b' }} />
                <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>Мои задачи</Typography>
                <Chip size="small" label={taskItems.length} sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700, bgcolor: 'rgba(245,158,11,0.12)', color: '#d97706' }} />
              </Stack>

              {taskItems.length === 0 ? (
                <Typography variant="body2" sx={{ color: 'text.secondary', py: 2, textAlign: 'center' }}>Активных задач нет.</Typography>
              ) : (
                <Stack spacing={0.8}>
                  {taskItems.map((task) => {
                    const s = String(task?.status || '').toLowerCase();
                    const col = statusColors[s] || '#64748b';
                    return (
                      <Box key={task.id} onClick={() => navigate(`/tasks?task=${encodeURIComponent(task.id)}`)} sx={{
                        ...card, p: 1, borderLeft: `3px solid ${task?.is_overdue ? '#ef4444' : col}`,
                      }}>
                        <Typography sx={{ fontWeight: 700, fontSize: '0.8rem', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          {task?.title || '-'}
                        </Typography>
                        <Stack direction="row" spacing={0.4} alignItems="center" sx={{ mt: 0.4 }}>
                          <Chip size="small" label={statusLabels[s] || s} sx={{ height: 18, fontSize: '0.6rem', fontWeight: 600, bgcolor: `${col}18`, color: col }} />
                          {task?.is_overdue && <Chip size="small" label="Просрочено" sx={{ height: 18, fontSize: '0.6rem', fontWeight: 700, bgcolor: 'rgba(239,68,68,0.15)', color: '#f87171' }} />}
                          {task?.due_at && (
                            <Stack direction="row" spacing={0.2} alignItems="center" sx={{ ml: 'auto' }}>
                              <AccessTimeIcon sx={{ fontSize: 11, color: task?.is_overdue ? '#f87171' : '#64748b' }} />
                              <Typography variant="caption" sx={{ fontSize: '0.6rem', color: task?.is_overdue ? '#f87171' : '#64748b' }}>{new Date(task.due_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}</Typography>
                            </Stack>
                          )}
                        </Stack>
                      </Box>
                    );
                  })}
                </Stack>
              )}

              <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
                <Button fullWidth size="small" variant="outlined" onClick={() => navigate('/tasks')} sx={{ textTransform: 'none', borderRadius: '10px', fontWeight: 600 }}>
                  Все задачи
                </Button>
              </Stack>
            </Box>
          </Grid>
        </Grid>
      </Box>

      {/* ── MENU ── */}
      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={closeMenu} PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '10px' } }}>
        <MenuItem onClick={() => void handleMenuReads()}><VisibilityIcon fontSize="small" sx={{ mr: 1 }} />Кто просмотрел</MenuItem>
        {canWriteAnn && Number(menuItem?.author_user_id) === Number(user?.id) && <MenuItem onClick={handleMenuEdit}><EditOutlinedIcon fontSize="small" sx={{ mr: 1 }} />Редактировать</MenuItem>}
        {canWriteAnn && Number(menuItem?.author_user_id) === Number(user?.id) && <MenuItem onClick={() => void handleMenuDelete()} sx={{ color: '#ef4444' }}><DeleteOutlineIcon fontSize="small" sx={{ mr: 1 }} />Удалить</MenuItem>}
      </Menu>

      {/* ── READS DIALOG ── */}
      <Dialog open={readsOpen} onClose={() => setReadsOpen(false)} fullWidth maxWidth="sm" PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Кто просмотрел</DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          {readsLoading && <LinearProgress sx={{ mb: 1 }} />}
          {readsRows.length === 0 && !readsLoading ? <Typography variant="body2" color="text.secondary">Пока нет отметок.</Typography> : (
            <List dense>{readsRows.map((r) => <ListItem key={`${r.announcement_id}-${r.user_id}`}><ListItemText primary={r?.full_name || r?.username || '-'} secondary={fmt(r?.read_at)} /></ListItem>)}</List>
          )}
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}><Button onClick={() => setReadsOpen(false)} sx={{ textTransform: 'none' }}>Закрыть</Button></DialogActions>
      </Dialog>

      {/* ── DETAILS ── */}
      <Dialog open={detailsOpen} onClose={() => setDetailsOpen(false)} fullWidth maxWidth="md" PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>{detailsAnn?.title || 'Заметка'}</DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          {detailsAnn ? (
            <Stack spacing={1.2}>
              <Stack direction="row" spacing={0.5} flexWrap="wrap">
                {(() => { const pm = announcementPriorityMeta(detailsAnn.priority); return <Chip size="small" label={pm.label} sx={{ bgcolor: pm.bg, color: pm.color }} />; })()}
                <Chip size="small" variant="outlined" label={fmt(detailsAnn.published_at)} />
              </Stack>
              <Stack direction="row" spacing={0.5} alignItems="center">
                <Avatar sx={{ width: 24, height: 24, fontSize: '0.6rem', bgcolor: 'primary.light', color: 'primary.contrastText' }}>{initials(detailsAnn.author_full_name)}</Avatar>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>{detailsAnn.author_full_name || detailsAnn.author_username || '-'}</Typography>
              </Stack>
              <MarkdownRenderer value={detailsAnn.body || detailsAnn.preview || ''} />
              {Array.isArray(detailsAnn.attachments) && detailsAnn.attachments.length > 0 && (
                <>
                  <Divider sx={{ borderColor: 'divider' }} />
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}><AttachFileIcon sx={{ fontSize: 16, mr: 0.5, verticalAlign: 'text-bottom' }} />Файлы ({detailsAnn.attachments.length})</Typography>
                  <List dense disablePadding>
                    {detailsAnn.attachments.map((a) => (
                      <ListItem key={a.id} disableGutters secondaryAction={<IconButton size="small" onClick={() => downloadAtt(detailsAnn.id, a)}><DownloadIcon fontSize="small" /></IconButton>}>
                        <ListItemText primary={a.file_name || 'file'} secondary={`${fmtSize(a.file_size)} · ${fmt(a.uploaded_at)}`} />
                      </ListItem>
                    ))}
                  </List>
                </>
              )}
            </Stack>
          ) : <Typography variant="body2" color="text.secondary">Заметка недоступна.</Typography>}
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}><Button onClick={() => setDetailsOpen(false)} sx={{ textTransform: 'none' }}>Закрыть</Button></DialogActions>
      </Dialog>

      {/* ── CREATE ── */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="md" PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <Box sx={{ background: 'linear-gradient(135deg, #3b82f6, #2563eb)', px: 3, py: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Box sx={{ width: 40, height: 40, borderRadius: '12px', background: 'linear-gradient(135deg, #3b82f6, #2563eb)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><AddIcon sx={{ color: '#fff' }} /></Box>
            <Box><Typography variant="h6" sx={{ fontWeight: 800, color: '#fff' }}>Новая заметка</Typography><Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.7)' }}>Создайте объявление для команды</Typography></Box>
          </Stack>
        </Box>
        <DialogContent sx={{ px: 3, py: 2.5 }}>
          <Stack spacing={2}>
            <TextField fullWidth size="small" placeholder="Заголовок..." value={createPayload.title} onChange={(e) => setCreatePayload((p) => ({ ...p, title: e.target.value }))} sx={{ '& .MuiOutlinedInput-root': { borderRadius: '10px', fontSize: '1rem', fontWeight: 600 } }} />
            <TextField fullWidth size="small" placeholder="Краткое описание (превью)..." value={createPayload.preview} onChange={(e) => setCreatePayload((p) => ({ ...p, preview: e.target.value }))} />
            <Stack direction="row" spacing={0.6}>
              {[{ v: 'low', l: 'Низкий', c: '#22c55e' }, { v: 'normal', l: 'Обычный', c: '#f59e0b' }, { v: 'high', l: 'Высокий', c: '#ef4444' }].map((p) => {
                const sel = (createPayload.priority || 'normal') === p.v;
                return <Box key={p.v} onClick={() => setCreatePayload((pr) => ({ ...pr, priority: p.v }))} sx={{ flex: 1, py: 0.8, borderRadius: '8px', textAlign: 'center', cursor: 'pointer', border: '1.5px solid', borderColor: sel ? p.c : 'divider', bgcolor: sel ? `${p.c}15` : 'transparent', transition: 'all 0.2s', '&:hover': { borderColor: `${p.c}80` } }}>
                  <FlagIcon sx={{ fontSize: 16, color: sel ? p.c : 'text.disabled', display: 'block', mx: 'auto', mb: 0.2 }} />
                  <Typography sx={{ fontSize: '0.65rem', fontWeight: sel ? 700 : 500, color: sel ? p.c : 'text.secondary' }}>{p.l}</Typography>
                </Box>;
              })}
            </Stack>
            <MarkdownEditor label="" value={createPayload.body} onChange={(v) => setCreatePayload((p) => ({ ...p, body: v }))} minRows={6} placeholder="Текст заметки (Markdown)..." enableAiTransform transformContext="announcement" onAiTransform={transformMd} />
            <Button variant="outlined" component="label" size="small" startIcon={<AttachFileIcon />} sx={{ textTransform: 'none', borderRadius: '10px' }}>
              {createFiles.length > 0 ? `Файлов: ${createFiles.length}` : 'Добавить вложения'}
              <input type="file" hidden multiple onChange={(e) => setCreateFiles(Array.from(e.target.files || []))} />
            </Button>
          </Stack>
        </DialogContent>
        <Box sx={{ px: 3, py: 1.5, display: 'flex', justifyContent: 'flex-end', gap: 1, borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setCreateOpen(false)} disabled={createSaving} sx={{ textTransform: 'none', color: 'text.secondary' }}>Отмена</Button>
          <Button variant="contained" onClick={handleCreate} disabled={createSaving || String(createPayload.title || '').trim().length < 3}
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '10px', background: 'linear-gradient(135deg, #3b82f6, #2563eb)', boxShadow: '0 4px 15px rgba(59,130,246,0.3)' }}>
            {createSaving ? 'Публикация...' : 'Опубликовать'}
          </Button>
        </Box>
      </Dialog>

      {/* ── EDIT ── */}
      <Dialog open={editOpen} onClose={() => setEditOpen(false)} fullWidth maxWidth="md" PaperProps={{ sx: { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: '16px' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Редактировать заметку</DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider' }}>
          <Stack spacing={1.5}>
            <TextField fullWidth size="small" label="Заголовок" value={editPayload.title} onChange={(e) => setEditPayload((p) => ({ ...p, title: e.target.value }))} />
            <TextField fullWidth size="small" label="Краткое описание" value={editPayload.preview} onChange={(e) => setEditPayload((p) => ({ ...p, preview: e.target.value }))} />
            <FormControl fullWidth size="small"><InputLabel>Приоритет</InputLabel>
              <Select value={editPayload.priority} label="Приоритет" onChange={(e) => setEditPayload((p) => ({ ...p, priority: e.target.value }))}>
                <MenuItem value="low">Низкий</MenuItem><MenuItem value="normal">Обычный</MenuItem><MenuItem value="high">Высокий</MenuItem>
              </Select>
            </FormControl>
            <MarkdownEditor label="Текст заметки (Markdown)" value={editPayload.body} onChange={(v) => setEditPayload((p) => ({ ...p, body: v }))} minRows={6} enableAiTransform transformContext="announcement" onAiTransform={transformMd} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
          <Button onClick={() => setEditOpen(false)} disabled={editSaving} sx={{ textTransform: 'none' }}>Отмена</Button>
          <Button variant="contained" onClick={handleUpdate} disabled={editSaving || String(editPayload.title || '').trim().length < 3} sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '10px' }}>
            {editSaving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </DialogActions>
      </Dialog>
    </MainLayout>
  );
}

export default Dashboard;
