/**
 * Main Layout component - AppBar and Sidebar navigation.
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar,
  Badge,
  Box,
  Toolbar,
  Typography,
  IconButton,
  Drawer,
  List,
  ListItem,
  ListItemIcon,
  ListItemButton,
  ListItemText,
  Divider,
  Button,
  FormControl,
  Select,
  MenuItem,
  Chip,
  Stack,
  Snackbar,
  Alert,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import StorageIcon from '@mui/icons-material/Storage';
import SettingsIcon from '@mui/icons-material/Settings';
import LogoutIcon from '@mui/icons-material/Logout';
import BarChartIcon from '@mui/icons-material/BarChart';
import LanIcon from '@mui/icons-material/Lan';
import ComputerIcon from '@mui/icons-material/Computer';
import PrintIcon from '@mui/icons-material/Print';
import ShieldIcon from '@mui/icons-material/Policy';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import DashboardIcon from '@mui/icons-material/Dashboard';
import TaskAltIcon from '@mui/icons-material/TaskAlt';
import NotificationsIcon from '@mui/icons-material/Notifications';
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone';
import AssignmentIcon from '@mui/icons-material/Assignment';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import GroupIcon from '@mui/icons-material/Group';
import VideocamIcon from '@mui/icons-material/Videocam';
import { useAuth } from '../../contexts/AuthContext';
import apiClient, { mailAPI } from '../../api/client';
import { getOrFetchSWR, buildCacheKey } from '../../lib/swrCache';

const DRAWER_WIDTH = 240;
const KB_WIKI_URL = 'https://wiki.zsgp.ru/';
const HUB_POLL_INTERVAL_MS = 20_000;


const navigationItems = [
  { path: '/dashboard', label: 'Центр управления', icon: <DashboardIcon />, permission: 'dashboard.read' },
  { path: '/tasks', label: 'Задачи', icon: <TaskAltIcon />, permission: 'tasks.read' },
  { path: '/mail', label: 'Почта', icon: <MailOutlineIcon />, permission: 'mail.access' },
  { path: '/database', label: 'IT-invent WEB', icon: <StorageIcon />, permission: 'database.read' },
  { path: '/networks', label: 'Сети', icon: <LanIcon />, permission: 'networks.read' },
  { path: '/ad-users', label: 'Пользователи AD', icon: <GroupIcon />, permission: 'ad_users.read' },
  { path: '/vcs', label: 'ВКС терминалы', icon: <VideocamIcon />, permission: 'vcs.read' },
  { path: '/mfu', label: 'МФУ', icon: <PrintIcon />, permission: 'database.read' },
  { path: '/computers', label: 'Компьютеры', icon: <ComputerIcon />, permission: 'computers.read' },
  { path: '/scan-center', label: 'Scan Center', icon: <ShieldIcon />, permission: 'scan.read' },
  { path: '/statistics', label: 'Статистика', icon: <BarChartIcon />, permission: 'statistics.read' },
  { path: '/kb', label: 'IT База знаний', icon: <MenuBookIcon />, permission: 'kb.read', externalUrl: KB_WIKI_URL },
  { path: '/settings', label: 'Настройки', icon: <SettingsIcon />, permission: 'settings.read' },
];

const SIDEBAR_COLLAPSED_KEY = 'sidebar_collapsed';
const normalizeDbId = (value) => String(value ?? '').trim();
const SWR_STALE_TIME_MS = 30_000;

function MainLayout({ children }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    return saved === 'true';
  });
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, hasPermission } = useAuth();
  const [databases, setDatabases] = useState([]);
  const [currentDb, setCurrentDb] = useState(null);
  const [dbLocked, setDbLocked] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCounts, setUnreadCounts] = useState({
    notifications_unread_total: 0,
    announcements_unread: 0,
    tasks_open: 0,
    tasks_new: 0,
    mail_unread: 0,
  });
  const [toastQueue, setToastQueue] = useState([]);
  const [activeToast, setActiveToast] = useState(null);
  const [toastOpen, setToastOpen] = useState(false);
  const lastPollRef = useRef('');
  const pollNotificationsRef = useRef(null);
  const hubPollBackoffUntilRef = useRef(0);
  const hubPollFailureCountRef = useRef(0);
  const hubPollLastWarnAtRef = useRef(0);
  const hasDashboardPermission = hasPermission('dashboard.read');
  const hasMailPermission = hasPermission('mail.access');
  const visibleNavigationItems = navigationItems.filter(
    (item) => !item.permission || hasPermission(item.permission)
  );

  const toggleSidebar = () => {
    const newState = !sidebarCollapsed;
    setSidebarCollapsed(newState);
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(newState));
  };

  // Fetch available databases
  useEffect(() => {
    const fetchDatabases = async () => {
      try {
        const cacheKey = buildCacheKey('database-list', normalizeDbId(localStorage.getItem('selected_database') || ''));
        const { data } = await getOrFetchSWR(
          cacheKey,
          async () => (await apiClient.get('/database/list')).data,
          { staleTimeMs: SWR_STALE_TIME_MS }
        );
        setDatabases(Array.isArray(data) ? data : []);
      } catch (error) {
        console.error('Error fetching databases:', error);
      }
    };

    const fetchCurrentDb = async () => {
      try {
        const cacheKey = buildCacheKey('database-current', normalizeDbId(localStorage.getItem('selected_database') || ''));
        const { data } = await getOrFetchSWR(
          cacheKey,
          async () => (await apiClient.get('/database/current')).data,
          { staleTimeMs: SWR_STALE_TIME_MS }
        );
        setCurrentDb({
          id: normalizeDbId(data?.id || data?.database_id || ''),
          name: data?.name || data?.database || data?.database_name || '',
        });
        setDbLocked(String(data?.locked || '') === 'true');
      } catch (error) {
        console.error('Error fetching current database:', error);
      }
    };

    fetchDatabases();
    fetchCurrentDb();
  }, []);

  useEffect(() => {
    if (databases.length === 0) return;

    const currentId = normalizeDbId(currentDb?.id);
    const storedId = normalizeDbId(localStorage.getItem('selected_database'));
    const preferredId = storedId || currentId;

    const selectedDb =
      databases.find((db) => normalizeDbId(db.id) === preferredId) ||
      databases.find((db) => normalizeDbId(db.id) === currentId) ||
      databases[0];

    if (!selectedDb) return;

    const selectedId = normalizeDbId(selectedDb.id);
    if (selectedId !== currentId || !currentDb?.name) {
      setCurrentDb({
        id: selectedId,
        name: selectedDb.name || currentDb?.name || '',
      });
    }

    localStorage.setItem('selected_database', selectedId);
  }, [databases, currentDb?.id, currentDb?.name]);

  useEffect(() => {
    if (!hasDashboardPermission && !hasMailPermission) return;

    let mounted = true;

    const fetchUnreadCounts = async () => {
      try {
        let notifTotal = 0;
        let annUnread = 0;
        let tasksOpen = 0;
        let tasksNew = 0;
        let mailUnread = 0;

        const promises = [];
        if (hasDashboardPermission) {
          promises.push(apiClient.get('/hub/notifications/unread-counts').then(res => {
            const data = res?.data || {};
            notifTotal = Number(data.notifications_unread_total || 0);
            annUnread = Number(data.announcements_unread || 0);
            tasksOpen = Number(data.tasks_open || 0);
            tasksNew = Number(data.tasks_new || 0);
          }));
        }

        if (hasMailPermission) {
          promises.push(mailAPI.getUnreadCount().then(data => {
            mailUnread = Number(data?.unread_count || 0);
          }));
        }

        await Promise.allSettled(promises);

        if (!mounted) return;
        setUnreadCounts({
          notifications_unread_total: notifTotal + mailUnread,
          announcements_unread: annUnread,
          tasks_open: tasksOpen,
          tasks_new: tasksNew,
          mail_unread: mailUnread,
        });
      } catch (error) {
        console.error('Hub unread counts error:', error);
      }
    };

    const pollNotifications = async ({ forceFull = false, enableToasts = true, ignoreBackoff = false } = {}) => {
      if (document.visibilityState !== 'visible') return;
      if (!ignoreBackoff && Date.now() < Number(hubPollBackoffUntilRef.current || 0)) return;
      try {
        const sinceValue = forceFull ? '' : String(lastPollRef.current || '').trim();
        const response = await apiClient.get('/hub/notifications/poll', {
          params: {
            since: sinceValue || undefined,
            limit: 20,
          },
        });
        hubPollFailureCountRef.current = 0;
        hubPollBackoffUntilRef.current = 0;
        const payload = response?.data || {};
        const items = Array.isArray(payload?.items) ? payload.items : [];
        if (!mounted) return;

        if (items.length > 0) {
          const maxTs = items.reduce((acc, item) => {
            const ts = String(item?.created_at || '').trim();
            if (!ts) return acc;
            return ts > acc ? ts : acc;
          }, String(lastPollRef.current || ''));
          lastPollRef.current = maxTs || lastPollRef.current;

          setNotifications((prev) => {
            const map = new Map((Array.isArray(prev) ? prev : []).map((item) => [String(item.id || ''), item]));
            items.forEach((item) => {
              const id = String(item?.id || '').trim();
              if (id) map.set(id, item);
            });
            return Array.from(map.values())
              .sort((a, b) => String(b?.created_at || '').localeCompare(String(a?.created_at || '')))
              .slice(0, 60);
          });

          if (enableToasts) {
            setToastQueue((prev) => {
              const existingIds = new Set((Array.isArray(prev) ? prev : []).map((item) => String(item?.id || '')));
              const additions = [];
              items
                .slice()
                .reverse()
                .forEach((item) => {
                  const id = String(item?.id || '').trim();
                  if (!id || existingIds.has(id)) return;
                  additions.push({
                    id,
                    title: String(item?.title || 'Новое уведомление'),
                    body: String(item?.body || ''),
                  });
                });
              return [...(Array.isArray(prev) ? prev : []), ...additions].slice(-20);
            });
          }
        }

        if (hasDashboardPermission) {
          const counts = payload?.unread_counts || {};
          let mailUnread = 0;
          if (hasMailPermission) {
            try {
              const mailData = await mailAPI.getUnreadCount();
              mailUnread = Number(mailData?.unread_count || 0);
            } catch (e) { }
          }
          setUnreadCounts((prev) => {
            if (mailUnread > (prev.mail_unread || 0)) {
              window.dispatchEvent(new CustomEvent('mail-needs-refresh'));
            }
            return {
              notifications_unread_total: Number(counts?.notifications_unread_total || 0) + mailUnread,
              announcements_unread: Number(counts?.announcements_unread || 0),
              tasks_open: Number(counts?.tasks_open || 0),
              tasks_new: Number(counts?.tasks_new || 0),
              mail_unread: mailUnread,
            };
          });
        }
      } catch (error) {
        const status = Number(error?.response?.status || 0);
        const isTransient = status === 0 || status === 502 || status === 503 || status === 504;
        if (isTransient) {
          const nextFailureCount = Math.min(6, Number(hubPollFailureCountRef.current || 0) + 1);
          hubPollFailureCountRef.current = nextFailureCount;
          const backoffMs = Math.min(
            300_000,
            HUB_POLL_INTERVAL_MS * (2 ** Math.max(0, nextFailureCount - 1))
          );
          hubPollBackoffUntilRef.current = Date.now() + backoffMs;

          const now = Date.now();
          if (now - Number(hubPollLastWarnAtRef.current || 0) > 60_000) {
            hubPollLastWarnAtRef.current = now;
            const codeText = status > 0 ? String(status) : 'network';
            console.warn(`Hub notifications poll temporary error (${codeText}), retry in ${Math.ceil(backoffMs / 1000)}s.`);
          }
          return;
        }
        console.error('Hub notifications poll error:', error);
      }
    };

    pollNotificationsRef.current = pollNotifications;
    lastPollRef.current = '';
    hubPollBackoffUntilRef.current = 0;
    hubPollFailureCountRef.current = 0;
    hubPollLastWarnAtRef.current = 0;
    fetchUnreadCounts();
    pollNotifications({ forceFull: true, enableToasts: false });
    const timer = setInterval(() => {
      pollNotifications({ forceFull: false, enableToasts: true });
    }, HUB_POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        pollNotifications({ forceFull: false, enableToasts: false });
      }
    };
    const onHubRefresh = () => {
      fetchUnreadCounts();
      pollNotifications({ forceFull: true, enableToasts: false, ignoreBackoff: true });
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('hub-refresh-notifications', onHubRefresh);

    const onMailRead = () => {
      setUnreadCounts(prev => {
        const mailUnread = Math.max(0, (prev.mail_unread || 0) - 1);
        const diff = (prev.mail_unread || 0) - mailUnread;
        return {
          ...prev,
          mail_unread: mailUnread,
          notifications_unread_total: Math.max(0, (prev.notifications_unread_total || 0) - diff)
        };
      });
    };
    window.addEventListener('mail-read', onMailRead);

    return () => {
      mounted = false;
      pollNotificationsRef.current = null;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('hub-refresh-notifications', onHubRefresh);
      window.removeEventListener('mail-read', onMailRead);
    };
  }, [hasDashboardPermission, hasMailPermission]);

  useEffect(() => {
    if (activeToast || toastQueue.length === 0) return;
    const [next, ...rest] = toastQueue;
    setActiveToast(next);
    setToastQueue(rest);
    setToastOpen(true);
  }, [activeToast, toastQueue]);

  const handleDatabaseChange = async (event) => {
    if (dbLocked) return;
    const newDbId = normalizeDbId(event.target.value);
    const selectedDb = databases.find((db) => normalizeDbId(db.id) === newDbId);

    if (selectedDb && newDbId !== normalizeDbId(currentDb?.id)) {
      try {
        await apiClient.post('/database/switch', { database_id: newDbId });
        const selectedId = normalizeDbId(selectedDb.id);
        setCurrentDb({ id: selectedId, name: selectedDb.name });
        localStorage.setItem('selected_database', selectedId);
        window.dispatchEvent(new CustomEvent('database-changed', { detail: { databaseId: selectedId } }));
      } catch (error) {
        console.error('Error switching database:', error);
        alert('Ошибка при переключении базы данных');
      }
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleMarkNotificationRead = async (notificationId) => {
    const id = String(notificationId || '').trim();
    if (!id) return;
    try {
      await apiClient.post(`/hub/notifications/${encodeURIComponent(id)}/read`);
      setNotifications((prev) => (Array.isArray(prev)
        ? prev.map((item) => (String(item?.id || '') === id ? { ...item, unread: 0 } : item))
        : []));
      setUnreadCounts((prev) => ({
        ...(prev || {}),
        notifications_unread_total: Math.max(0, Number(prev?.notifications_unread_total || 0) - 1),
      }));
    } catch (error) {
      console.error('Mark notification read failed:', error);
    }
  };

  const handleOpenNotification = async (item) => {
    if (!item) return;
    const entityType = String(item?.entity_type || '').trim().toLowerCase();
    const entityId = String(item?.entity_id || '').trim();
    if (Number(item?.unread || 0) === 1) {
      await handleMarkNotificationRead(item?.id);
    }
    setNotificationsOpen(false);
    if (entityType === 'task') {
      const suffix = entityId ? `?task=${encodeURIComponent(entityId)}` : '';
      navigate(`/tasks${suffix}`);
      return;
    }
    if (entityType === 'announcement') {
      navigate('/dashboard');
      return;
    }
    navigate('/dashboard');
  };

  const handleCloseToast = () => {
    setToastOpen(false);
    setActiveToast(null);
  };

  const handleNavigation = (item) => {
    const externalUrl = String(item?.externalUrl || '').trim();
    if (externalUrl) {
      window.open(externalUrl, '_blank', 'noopener,noreferrer');
      setDrawerOpen(false);
      return;
    }
    navigate(item.path);
    setDrawerOpen(false);
  };

  const handleOpenNotifications = () => {
    setNotificationsOpen(true);
    if (typeof pollNotificationsRef.current === 'function') {
      pollNotificationsRef.current({ forceFull: true, enableToasts: false, ignoreBackoff: true });
    }
  };

  const isItemActive = (path) => {
    if (path === '/networks') {
      return location.pathname === '/networks' || location.pathname.startsWith('/networks/');
    }
    return location.pathname === path;
  };

  const getCurrentTitle = () => {
    const item = visibleNavigationItems.find((item) => isItemActive(item.path));
    return item ? item.label : 'IT-invent Web';
  };

  const drawerContent = (
    <Box>
      <Toolbar />
      <List>
        {visibleNavigationItems.map((item) => (
          <ListItem key={item.path} disablePadding>
            <ListItemButton
              selected={!item.externalUrl && isItemActive(item.path)}
              onClick={() => handleNavigation(item)}
            >
              <ListItemIcon>
                {item.path === '/tasks' && Number(unreadCounts?.tasks_open || 0) > 0 ? (
                  <Badge color="error" badgeContent={Number(unreadCounts?.tasks_open || 0)}>
                    {item.icon}
                  </Badge>
                ) : item.path === '/mail' && Number(unreadCounts?.mail_unread || 0) > 0 ? (
                  <Badge color="error" badgeContent={Number(unreadCounts?.mail_unread || 0)}>
                    {item.icon}
                  </Badge>
                ) : item.icon}
              </ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Divider />
    </Box>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      {/* AppBar */}
      <AppBar
        position="fixed"
        sx={{
          width: { sm: sidebarCollapsed ? '100%' : `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { sm: sidebarCollapsed ? 0 : `${DRAWER_WIDTH}px` },
          transition: (theme) => theme.transitions.create(['width', 'margin'], {
            duration: theme.transitions.duration.standard,
          }),
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            onClick={() => {
              if (window.innerWidth < 600) {
                setDrawerOpen(!drawerOpen);
              } else {
                toggleSidebar();
              }
            }}
            sx={{
              mr: 2,
              '& .MuiSvgIcon-root': {
                transition: (theme) => theme.transitions.create('transform', {
                  duration: theme.transitions.duration.standard,
                }),
                transform: sidebarCollapsed ? 'rotate(180deg)' : 'rotate(0deg)',
              },
            }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {getCurrentTitle()}
          </Typography>
          {hasDashboardPermission ? (
            <IconButton color="inherit" onClick={handleOpenNotifications} sx={{ mr: 1 }}>
              <Badge color="error" badgeContent={Number(unreadCounts?.notifications_unread_total || 0)}>
                <NotificationsIcon />
              </Badge>
            </IconButton>
          ) : null}
          <Typography variant="body2" sx={{ mr: 2 }}>
            {user?.username}
          </Typography>
          <FormControl size="small" sx={{ mr: 2, minWidth: 180 }}>
            <Select
              value={normalizeDbId(currentDb?.id)}
              onChange={handleDatabaseChange}
              disabled={dbLocked}
              displayEmpty
              sx={{
                color: 'white',
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: 'rgba(255, 255, 255, 0.3)',
                },
                '&:hover .MuiOutlinedInput-notchedOutline': {
                  borderColor: 'rgba(255, 255, 255, 0.5)',
                },
                '& .MuiSelect-icon': {
                  color: 'white',
                },
              }}
            >
              {databases.map((db) => (
                <MenuItem key={normalizeDbId(db.id)} value={normalizeDbId(db.id)}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <span>{db.name}</span>
                    {normalizeDbId(db.id) === normalizeDbId(currentDb?.id) && (
                      <Chip label="Текущая" size="small" color="success" sx={{ ml: 1, height: 20, fontSize: '0.7rem' }} />
                    )}
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {dbLocked && (
            <Chip
              label="БД закреплена"
              size="small"
              color="warning"
              sx={{ mr: 2 }}
            />
          )}
          <Button color="inherit" onClick={handleLogout} startIcon={<LogoutIcon />}>
            Выход
          </Button>
        </Toolbar>
      </AppBar>

      {/* Sidebar Drawer */}
      <Box
        component="nav"
        sx={{
          width: { sm: sidebarCollapsed ? 0 : DRAWER_WIDTH },
          flexShrink: { sm: 0 },
          transition: (theme) => theme.transitions.create('width', {
            duration: theme.transitions.duration.standard,
          }),
        }}
      >
        <Drawer
          variant="temporary"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
          }}
        >
          {drawerContent}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: sidebarCollapsed ? 'none' : 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
            transition: (theme) => theme.transitions.create('display', {
              duration: theme.transitions.duration.standard,
            }),
          }}
          open
        >
          {drawerContent}
        </Drawer>
      </Box>

      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: {
            xs: '100%',
            sm: sidebarCollapsed ? '100%' : `calc(100% - ${DRAWER_WIDTH}px)`
          },
          mt: 8, // Offset for fixed AppBar
          transition: (theme) => theme.transitions.create(['width', 'margin'], {
            duration: theme.transitions.duration.standard,
          }),
        }}
      >
        {children}
      </Box>

      <Drawer
        anchor="right"
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
        PaperProps={{ sx: { bgcolor: 'background.paper', borderLeft: '1px solid', borderColor: 'divider' } }}
      >
        <Box sx={{ width: { xs: 340, sm: 400 }, display: 'flex', flexDirection: 'column', height: '100%' }}>
          {/* Header */}
          <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="subtitle1" sx={{ fontWeight: 800, fontSize: '1.05rem' }}>Уведомления</Typography>
                {Number(unreadCounts?.notifications_unread_total || 0) > 0 && (
                  <Chip size="small" label={unreadCounts.notifications_unread_total}
                    sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700, bgcolor: 'rgba(59,130,246,0.12)', color: 'primary.main' }} />
                )}
              </Stack>
              {Number(unreadCounts?.notifications_unread_total || 0) > 0 && (
                <Button size="small" onClick={async () => {
                  const unreadItems = (Array.isArray(notifications) ? notifications : []).filter((i) => Number(i?.unread || 0) === 1);
                  for (const item of unreadItems) {
                    try { await apiClient.post(`/hub/notifications/${encodeURIComponent(item.id)}/read`); } catch { }
                  }
                  setNotifications((prev) => (Array.isArray(prev) ? prev.map((i) => ({ ...i, unread: 0 })) : []));
                  setUnreadCounts((prev) => ({ ...(prev || {}), notifications_unread_total: 0 }));
                }}
                  sx={{ textTransform: 'none', fontSize: '0.72rem', fontWeight: 600 }}>
                  Прочитать все
                </Button>
              )}
            </Stack>
          </Box>

          {/* Content */}
          <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>
            {notifications.length === 0 ? (
              <Box sx={{ textAlign: 'center', py: 6 }}>
                <NotificationsNoneIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>Нет уведомлений</Typography>
              </Box>
            ) : (() => {
              const now = new Date();
              const todayStr = now.toDateString();
              const yesterday = new Date(now); yesterday.setDate(yesterday.getDate() - 1);
              const yesterdayStr = yesterday.toDateString();
              const groups = { today: [], yesterday: [], earlier: [] };
              notifications.forEach((item) => {
                const d = new Date(item?.created_at || '');
                if (d.toDateString() === todayStr) groups.today.push(item);
                else if (d.toDateString() === yesterdayStr) groups.yesterday.push(item);
                else groups.earlier.push(item);
              });
              const sections = [
                { key: 'today', label: 'Сегодня', items: groups.today },
                { key: 'yesterday', label: 'Вчера', items: groups.yesterday },
                { key: 'earlier', label: 'Ранее', items: groups.earlier },
              ].filter((s) => s.items.length > 0);

              return sections.map((section) => (
                <Box key={section.key} sx={{ mb: 2 }}>
                  <Typography variant="overline" sx={{ color: 'text.disabled', fontWeight: 700, fontSize: '0.6rem', letterSpacing: '0.1em', display: 'block', mb: 0.8, px: 0.5 }}>
                    {section.label}
                  </Typography>
                  <Stack spacing={0.5}>
                    {section.items.map((item) => {
                      const unread = Number(item?.unread || 0) === 1;
                      const entityType = String(item?.entity_type || '').toLowerCase();
                      const isTask = entityType === 'task';
                      const accentColor = isTask ? '#f59e0b' : '#3b82f6';
                      return (
                        <Box key={item.id} sx={{
                          p: 1.2, borderRadius: '10px', cursor: 'pointer',
                          borderLeft: `3px solid ${unread ? accentColor : 'transparent'}`,
                          bgcolor: unread ? (isTask ? 'rgba(245,158,11,0.05)' : 'rgba(59,130,246,0.05)') : 'transparent',
                          border: '1px solid', borderColor: unread ? (isTask ? 'rgba(245,158,11,0.12)' : 'rgba(59,130,246,0.12)') : 'divider',
                          transition: 'all 0.15s ease',
                          '&:hover': { bgcolor: 'action.hover', borderColor: 'action.selected' },
                        }}
                          onClick={() => handleOpenNotification(item)}
                        >
                          <Stack direction="row" spacing={1} alignItems="flex-start">
                            <Box sx={{
                              width: 32, height: 32, borderRadius: '8px', flexShrink: 0, mt: 0.2,
                              bgcolor: `${accentColor}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                              {isTask
                                ? <AssignmentIcon sx={{ fontSize: 16, color: accentColor }} />
                                : <NotificationsNoneIcon sx={{ fontSize: 16, color: accentColor }} />
                              }
                            </Box>
                            <Box sx={{ flex: 1, minWidth: 0 }}>
                              <Stack direction="row" justifyContent="space-between" alignItems="center">
                                <Typography variant="body2" sx={{
                                  fontWeight: unread ? 700 : 500, fontSize: '0.82rem', lineHeight: 1.3,
                                  color: 'text.primary',
                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                }}>
                                  {item?.title || 'Уведомление'}
                                </Typography>
                                {unread && (
                                  <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: accentColor, flexShrink: 0, ml: 1 }} />
                                )}
                              </Stack>
                              {item?.body && (
                                <Typography variant="caption" sx={{
                                  color: 'text.secondary', display: 'block', mt: 0.3, fontSize: '0.72rem', lineHeight: 1.3,
                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                }}>{item.body}</Typography>
                              )}
                              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 0.5 }}>
                                <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem' }}>
                                  {item?.created_at ? new Date(item.created_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '-'}
                                </Typography>
                                {unread && (
                                  <Button size="small" onClick={(e) => { e.stopPropagation(); handleMarkNotificationRead(item.id); }}
                                    sx={{ textTransform: 'none', fontSize: '0.62rem', fontWeight: 600, minWidth: 0, py: 0, px: 0.5 }}>
                                    Прочитано
                                  </Button>
                                )}
                              </Stack>
                            </Box>
                          </Stack>
                        </Box>
                      );
                    })}
                  </Stack>
                </Box>
              ));
            })()}
          </Box>
        </Box>
      </Drawer>

      <Snackbar
        open={toastOpen}
        autoHideDuration={4000}
        onClose={handleCloseToast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Alert onClose={handleCloseToast} severity="info" variant="filled" sx={{ width: '100%' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>{activeToast?.title || 'Уведомление'}</Typography>
          {activeToast?.body ? (
            <Typography variant="caption">{activeToast.body}</Typography>
          ) : null}
        </Alert>
      </Snackbar>
    </Box>
  );
}

export default MainLayout;
