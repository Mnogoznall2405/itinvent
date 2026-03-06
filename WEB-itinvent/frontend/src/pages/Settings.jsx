import { useCallback, useEffect, useMemo, useState, memo } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormGroup,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Divider,
  Drawer,
  IconButton,
} from '@mui/material';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import PaletteOutlinedIcon from '@mui/icons-material/PaletteOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import GroupOutlinedIcon from '@mui/icons-material/GroupOutlined';
import SecurityOutlinedIcon from '@mui/icons-material/SecurityOutlined';
import SyncOutlinedIcon from '@mui/icons-material/SyncOutlined';
import CloseOutlinedIcon from '@mui/icons-material/CloseOutlined';
import CircularProgress from '@mui/material/CircularProgress';
import MainLayout from '../components/layout/MainLayout';
import apiClient, { authAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { usePreferences } from '../contexts/PreferencesContext';

const roleOptions = [
  { value: 'admin', label: 'Админ' },
  { value: 'operator', label: 'Оператор' },
  { value: 'viewer', label: 'Просмотр' },
];

const permissionGroups = [
  {
    group: 'Общие',
    permissions: [
      { value: 'dashboard.read', label: 'Dashboard: просмотр' },
      { value: 'announcements.write', label: 'Объявления: публикация' },
      { value: 'statistics.read', label: 'Статистика: просмотр' },
    ]
  },
  {
    group: 'IT-invent WEB',
    permissions: [
      { value: 'database.read', label: 'База: просмотр' },
      { value: 'database.write', label: 'База: изменения' },
      { value: 'computers.read', label: 'Компьютеры: просмотр' },
      { value: 'computers.read_all', label: 'Компьютеры: просмотр всех БД' },
    ]
  },
  {
    group: 'Задачи',
    permissions: [
      { value: 'tasks.read', label: 'Задачи: просмотр' },
      { value: 'tasks.write', label: 'Задачи: создание/редактирование' },
      { value: 'tasks.review', label: 'Задачи: проверка' },
    ]
  },
  {
    group: 'Инструменты сети',
    permissions: [
      { value: 'networks.read', label: 'Сети: просмотр' },
      { value: 'networks.write', label: 'Сети: изменения' },
      { value: 'scan.read', label: 'Scan Center: просмотр' },
      { value: 'scan.ack', label: 'Scan Center: ACK инцидентов' },
      { value: 'scan.tasks', label: 'Scan Center: задачи агентам' },
      { value: 'vcs.read', label: 'Терминалы ВКС: просмотр' },
      { value: 'vcs.manage', label: 'Терминалы ВКС: управление' },
    ]
  },
  {
    group: 'Интеграции',
    permissions: [
      { value: 'mail.access', label: 'Почта: доступ к Exchange' },
      { value: 'ad_users.read', label: 'Пользователи AD: просмотр' },
      { value: 'ad_users.manage', label: 'Пользователи AD: управление' },
    ]
  },
  {
    group: 'База знаний',
    permissions: [
      { value: 'kb.read', label: 'База знаний: просмотр' },
      { value: 'kb.write', label: 'База знаний: редактирование' },
      { value: 'kb.publish', label: 'База знаний: публикация' },
    ]
  },
  {
    group: 'Настройки',
    permissions: [
      { value: 'settings.read', label: 'Настройки: просмотр' },
      { value: 'settings.users.manage', label: 'Пользователи: управление' },
      { value: 'settings.sessions.manage', label: 'Сессии: управление' },
    ]
  },
];

const normalizePermissions = (value) => {
  const list = Array.isArray(value) ? value : [];
  return [...new Set(list.map((item) => String(item || '').trim()).filter(Boolean))];
};

const UserRow = memo(({ item, dbOptions, roleOptions, onEdit, onDelete }) => (
  <TableRow hover>
    <TableCell>{item.username}</TableCell>
    <TableCell>{item.full_name || '—'}</TableCell>
    <TableCell>{item.email || '—'}</TableCell>
    <TableCell>{item.mailbox_email || '—'}</TableCell>
    <TableCell>{item.telegram_id || '—'}</TableCell>
    <TableCell>
      {item.auth_source === 'ldap' ? 'AD (LDAP)' : 'Локальная'}
    </TableCell>
    <TableCell>
      {item.assigned_database
        ? dbOptions.find((d) => String(d.id) === String(item.assigned_database))?.name || item.assigned_database
        : 'Не ограничивать'}
    </TableCell>
    <TableCell>
      {roleOptions.find((r) => r.value === item.role)?.label || item.role}
    </TableCell>
    <TableCell>
      {item.use_custom_permissions
        ? `Индивидуально (${normalizePermissions(item.custom_permissions).length})`
        : 'По роли'}
    </TableCell>
    <TableCell>
      {item.is_active ? 'Активен' : 'Отключен'}
    </TableCell>
    <TableCell>
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="outlined" onClick={() => onEdit(item)}>Редакт.</Button>
        <Button size="small" variant="outlined" color="error" onClick={() => onDelete(item)}>Удал.</Button>
      </Stack>
    </TableCell>
  </TableRow>
));

const UserEditDrawer = memo(({ open, item, dbOptions, roleOptions, permissionGroups, onClose, onSave, saving }) => {
  const [editData, setEditData] = useState(null);

  useEffect(() => {
    if (!item) {
      setEditData(null);
      return;
    }
    setEditData({
      ...item,
      use_custom_permissions: Boolean(item.use_custom_permissions),
      custom_permissions: normalizePermissions(item.custom_permissions),
      mailbox_email: item.mailbox_email || '',
      mailbox_login: item.mailbox_login || '',
      mailbox_password: '',
    });
  }, [item, open]);

  const handleLocalChange = (field, value) => {
    setEditData((prev) => ({ ...(prev || {}), [field]: value }));
  };

  const togglePermission = (permission) => {
    const current = normalizePermissions(editData?.custom_permissions);
    if (current.includes(permission)) {
      handleLocalChange('custom_permissions', current.filter((entry) => entry !== permission));
      return;
    }
    handleLocalChange('custom_permissions', [...current, permission]);
  };

  const handleSave = () => {
    if (!editData) return;
    onSave(editData);
  };

  return (
    <Drawer anchor="right" open={open} onClose={onClose}>
      <Box sx={{ width: { xs: '100vw', sm: 500 }, height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Редактирование пользователя
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {item?.username || '—'}
            </Typography>
          </Box>
          <IconButton size="small" onClick={onClose} disabled={saving}>
            <CloseOutlinedIcon fontSize="small" />
          </IconButton>
        </Box>
        <Divider />
        <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
          {!editData && (
            <Typography variant="body2" color="text.secondary">Нет данных для редактирования.</Typography>
          )}
          {editData && (
            <Stack spacing={1.5}>
              <TextField size="small" label="Логин" value={editData.username || ''} disabled />
              <TextField size="small" label="ФИО" value={editData.full_name || ''} onChange={(e) => handleLocalChange('full_name', e.target.value)} />
              <TextField size="small" label="Email" value={editData.email || ''} onChange={(e) => handleLocalChange('email', e.target.value)} />
              <TextField size="small" label="Почта Exchange" value={editData.mailbox_email || ''} onChange={(e) => handleLocalChange('mailbox_email', e.target.value)} />
              <TextField size="small" label="Логин Exchange" value={editData.mailbox_login || ''} onChange={(e) => handleLocalChange('mailbox_login', e.target.value)} />
              <TextField
                size="small"
                label="Новый пароль Exchange"
                type="password"
                value={editData.mailbox_password || ''}
                helperText="Оставьте пустым, чтобы не менять пароль."
                onChange={(e) => handleLocalChange('mailbox_password', e.target.value)}
              />
              <TextField size="small" label="Telegram ID" value={editData.telegram_id || ''} onChange={(e) => handleLocalChange('telegram_id', e.target.value)} />
              <FormControl size="small" fullWidth>
                <InputLabel>Источник</InputLabel>
                <Select label="Источник" value={editData.auth_source || 'local'} onChange={(e) => handleLocalChange('auth_source', e.target.value)}>
                  <MenuItem value="local">Локальная</MenuItem>
                  <MenuItem value="ldap">AD (LDAP)</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" fullWidth>
                <InputLabel>Назначенная БД</InputLabel>
                <Select label="Назначенная БД" value={editData.assigned_database || ''} onChange={(e) => handleLocalChange('assigned_database', e.target.value)}>
                  <MenuItem value="">Не ограничивать</MenuItem>
                  {dbOptions.map((db) => (
                    <MenuItem key={db.id} value={db.id}>{db.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" fullWidth>
                <InputLabel>Роль</InputLabel>
                <Select label="Роль" value={editData.role || 'viewer'} onChange={(e) => handleLocalChange('role', e.target.value)}>
                  {roleOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControlLabel
                control={<Switch checked={Boolean(editData.is_active)} onChange={(e) => handleLocalChange('is_active', e.target.checked)} />}
                label={editData.is_active ? 'Активен' : 'Отключен'}
              />
              <FormControlLabel
                control={<Switch checked={Boolean(editData.use_custom_permissions)} onChange={(e) => handleLocalChange('use_custom_permissions', e.target.checked)} />}
                label="Индивидуальные права"
              />
              {Boolean(editData.use_custom_permissions) && (
                <Paper variant="outlined" sx={{ p: 1.2, maxHeight: 320, overflow: 'auto' }}>
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                    Доступы по чекбоксам
                  </Typography>
                  {permissionGroups.map((group) => (
                    <Box key={group.group} sx={{ mb: 1.5 }}>
                      <Typography variant="caption" sx={{ fontWeight: 'bold', color: 'text.secondary', display: 'block', mb: 0.5, textTransform: 'uppercase' }}>
                        {group.group}
                      </Typography>
                      <FormGroup>
                        {group.permissions.map((permission) => {
                          const checked = normalizePermissions(editData.custom_permissions).includes(permission.value);
                          return (
                            <FormControlLabel
                              key={permission.value}
                              control={<Checkbox size="small" checked={checked} onChange={() => togglePermission(permission.value)} />}
                              label={permission.label}
                              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.875rem' } }}
                            />
                          );
                        })}
                      </FormGroup>
                    </Box>
                  ))}
                </Paper>
              )}
            </Stack>
          )}
        </Box>
        <Divider />
        <Box sx={{ px: 2, py: 1.5, display: 'flex', justifyContent: 'flex-end', gap: 1 }}>
          <Button variant="outlined" onClick={onClose} disabled={saving}>Отмена</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving || !editData}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </Box>
      </Box>
    </Drawer>
  );
});

function TabPanel({ value, current, children }) {
  return (
    <Box role="tabpanel" hidden={value !== current}>
      {value === current ? children : null}
    </Box>
  );
}

const CreateUserForm = memo(({ dbOptions, roleOptions, permissionGroups, onSuccess, onError, onMessage }) => {
  const [newUser, setNewUser] = useState({
    username: '',
    password: '',
    full_name: '',
    email: '',
    mailbox_email: '',
    mailbox_login: '',
    mailbox_password: '',
    role: 'viewer',
    auth_source: 'local',
    telegram_id: '',
    assigned_database: '',
    is_active: true,
    use_custom_permissions: false,
    custom_permissions: [],
  });

  const toggleCreatePermission = (permission) => {
    const current = normalizePermissions(newUser.custom_permissions);
    if (current.includes(permission)) {
      setNewUser((prev) => ({ ...prev, custom_permissions: current.filter((item) => item !== permission) }));
      return;
    }
    setNewUser((prev) => ({ ...prev, custom_permissions: [...current, permission] }));
  };

  const handleCreateUser = async () => {
    onError('');
    const username = String(newUser.username || '').trim();
    const password = String(newUser.password || '');
    const fullName = String(newUser.full_name || '').trim();
    const email = String(newUser.email || '').trim();
    const mailboxEmail = String(newUser.mailbox_email || '').trim();
    const mailboxLogin = String(newUser.mailbox_login || '').trim();
    const mailboxPassword = String(newUser.mailbox_password || '').trim();
    const telegramRaw = String(newUser.telegram_id || '').trim();
    const telegramId = telegramRaw ? Number(telegramRaw) : null;

    if (username.length < 3) {
      onError('Логин должен содержать минимум 3 символа.');
      return;
    }
    if (newUser.auth_source !== 'ldap' && password.length < 6) {
      onError('Пароль должен содержать минимум 6 символов.');
      return;
    }
    if (telegramRaw && !Number.isInteger(telegramId)) {
      onError('Telegram ID должен быть целым числом.');
      return;
    }

    try {
      await authAPI.createUser({
        username,
        password,
        full_name: fullName || null,
        email: email || null,
        mailbox_email: mailboxEmail || null,
        mailbox_login: mailboxLogin || null,
        mailbox_password: mailboxPassword || null,
        role: newUser.role || 'viewer',
        auth_source: newUser.auth_source || 'local',
        telegram_id: telegramId,
        assigned_database: newUser.assigned_database || null,
        is_active: Boolean(newUser.is_active),
        use_custom_permissions: Boolean(newUser.use_custom_permissions),
        custom_permissions: normalizePermissions(newUser.custom_permissions),
      });
      onMessage('Пользователь успешно создан.');
      setNewUser({
        username: '',
        password: '',
        full_name: '',
        email: '',
        mailbox_email: '',
        mailbox_login: '',
        mailbox_password: '',
        role: 'viewer',
        auth_source: 'local',
        telegram_id: '',
        assigned_database: '',
        is_active: true,
        use_custom_permissions: false,
        custom_permissions: [],
      });
      await onSuccess();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      onError(typeof detail === 'string' ? detail : Array.isArray(detail) ? JSON.stringify(detail) : 'Не удалось создать пользователя.');
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Создать пользователя</Typography>
      <Grid container spacing={1.5}>
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="Логин *" value={newUser.username} onChange={(e) => setNewUser((p) => ({ ...p, username: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <FormControl fullWidth size="small">
            <InputLabel>Источник</InputLabel>
            <Select label="Источник" value={newUser.auth_source || 'local'} onChange={(e) => setNewUser((p) => ({ ...p, auth_source: e.target.value }))}>
              <MenuItem value="local">Локальная БД</MenuItem>
              <MenuItem value="ldap">Active Directory</MenuItem>
            </Select>
          </FormControl>
        </Grid>
        {newUser.auth_source !== 'ldap' && (
          <Grid item xs={12} md={2}>
            <TextField fullWidth size="small" label="Пароль *" type="password" value={newUser.password} onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))} />
          </Grid>
        )}
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="ФИО" value={newUser.full_name} onChange={(e) => setNewUser((p) => ({ ...p, full_name: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="Email" value={newUser.email} onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="Почта Exchange" value={newUser.mailbox_email} onChange={(e) => setNewUser((p) => ({ ...p, mailbox_email: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="Логин Exchange" value={newUser.mailbox_login} onChange={(e) => setNewUser((p) => ({ ...p, mailbox_login: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="Пароль Exchange" type="password" value={newUser.mailbox_password} onChange={(e) => setNewUser((p) => ({ ...p, mailbox_password: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <TextField fullWidth size="small" label="Telegram ID" value={newUser.telegram_id} onChange={(e) => setNewUser((p) => ({ ...p, telegram_id: e.target.value }))} />
        </Grid>
        <Grid item xs={12} md={2}>
          <FormControl fullWidth size="small">
            <InputLabel>Назначенная БД</InputLabel>
            <Select label="Назначенная БД" value={newUser.assigned_database || ''} onChange={(e) => setNewUser((p) => ({ ...p, assigned_database: e.target.value }))}>
              <MenuItem value="">Не ограничивать</MenuItem>
              {dbOptions.map((db) => (
                <MenuItem key={db.id} value={db.id}>{db.name}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={2}>
          <FormControl fullWidth size="small">
            <InputLabel>Роль</InputLabel>
            <Select label="Роль" value={newUser.role} onChange={(e) => setNewUser((p) => ({ ...p, role: e.target.value }))}>
              {roleOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={3}>
          <FormControlLabel control={<Switch checked={newUser.is_active} onChange={(e) => setNewUser((p) => ({ ...p, is_active: e.target.checked }))} />} label="Активен" />
        </Grid>
        <Grid item xs={12} md={3}>
          <FormControlLabel
            control={(
              <Switch
                checked={Boolean(newUser.use_custom_permissions)}
                onChange={(e) => setNewUser((p) => ({ ...p, use_custom_permissions: e.target.checked }))}
              />
            )}
            label="Индивидуальные права"
          />
        </Grid>
        {Boolean(newUser.use_custom_permissions) && (
          <Grid item xs={12}>
            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1.5 }}>
                Выберите индивидуальные права:
              </Typography>
              <Grid container spacing={2}>
                {permissionGroups.map((group) => (
                  <Grid item xs={12} md={6} lg={4} key={group.group}>
                    <Box sx={{ mb: 1 }}>
                      <Typography variant="caption" sx={{ fontWeight: 'bold', color: 'primary.main', display: 'block', mb: 0.5, borderBottom: '1px solid', borderColor: 'divider', pb: 0.5, textTransform: 'uppercase' }}>
                        {group.group}
                      </Typography>
                      <FormGroup>
                        {group.permissions.map((permission) => {
                          const checked = normalizePermissions(newUser.custom_permissions).includes(permission.value);
                          return (
                            <FormControlLabel
                              key={permission.value}
                              control={(
                                <Checkbox
                                  size="small"
                                  checked={checked}
                                  onChange={() => toggleCreatePermission(permission.value)}
                                />
                              )}
                              label={permission.label}
                              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.875rem' } }}
                            />
                          );
                        })}
                      </FormGroup>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Paper>
          </Grid>
        )}
        <Grid item xs={12} md={3}>
          <Button
            variant="contained"
            onClick={handleCreateUser}
            disabled={String(newUser.username || '').trim().length < 3 || (newUser.auth_source !== 'ldap' && String(newUser.password || '').length < 6)}
          >
            Добавить пользователя
          </Button>
        </Grid>
      </Grid>
    </Paper>
  );
});

const ProfileTab = memo(({ user }) => (
  <Paper variant="outlined" sx={{ p: 2 }}>
    <Stack spacing={1}>
      <Typography><strong>Логин:</strong> {user?.username || '-'}</Typography>
      <Typography><strong>Роль:</strong> {user?.role || '-'}</Typography>
      <Typography><strong>Telegram ID:</strong> {user?.telegram_id || 'не указан'}</Typography>
      <Typography><strong>Назначенная БД:</strong> {user?.assigned_database || 'не ограничена'}</Typography>
    </Stack>
  </Paper>
));

const AppearanceTab = memo(({ themeMode, setThemeMode, fontFamily, setFontFamily, fontScale, setFontScale, handleSavePreferences, saving }) => (
  <Box>
    <Grid container spacing={2}>
      <Grid item xs={12} md={4}>
        <FormControl fullWidth size="small">
          <InputLabel>Тема</InputLabel>
          <Select value={themeMode} label="Тема" onChange={(e) => setThemeMode(e.target.value)}>
            <MenuItem value="light">Светлая</MenuItem>
            <MenuItem value="dark">Темная</MenuItem>
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={12} md={4}>
        <FormControl fullWidth size="small">
          <InputLabel>Шрифт</InputLabel>
          <Select value={fontFamily} label="Шрифт" onChange={(e) => setFontFamily(e.target.value)}>
            <MenuItem value="Inter">Inter</MenuItem>
            <MenuItem value="Roboto">Roboto</MenuItem>
            <MenuItem value="Segoe UI">Segoe UI</MenuItem>
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={12} md={4}>
        <Typography variant="body2" color="text.secondary">Масштаб шрифта: {fontScale.toFixed(2)}</Typography>
        <Slider min={0.9} max={1.2} step={0.05} value={fontScale} onChange={(_, v) => setFontScale(Array.isArray(v) ? v[0] : v)} />
      </Grid>
    </Grid>
    <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
      <Button variant="contained" onClick={handleSavePreferences} disabled={saving}>Сохранить</Button>
    </Box>
  </Box>
));

const DatabaseTab = memo(({ pinnedDatabase, setPinnedDatabase, dbLocked, dbOptions, handleSavePreferences, saving }) => (
  <Box>
    <Grid container spacing={2}>
      <Grid item xs={12} md={8}>
        <FormControl fullWidth size="small">
          <InputLabel>Закрепленная база</InputLabel>
          <Select label="Закрепленная база" value={pinnedDatabase} onChange={(e) => setPinnedDatabase(e.target.value)} disabled={dbLocked}>
            <MenuItem value="">Не закреплять</MenuItem>
            {dbOptions.map((db) => (
              <MenuItem key={db.id} value={db.id}>{db.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={12} md={4}>
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="body2">
            {dbLocked ? 'База закреплена для этой учетной записи' : 'Базу можно переключать'}
          </Typography>
        </Paper>
      </Grid>
    </Grid>
    <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
      <Button variant="contained" onClick={handleSavePreferences} disabled={saving}>Сохранить</Button>
    </Box>
  </Box>
));

const UsersTab = memo(({ dbOptions, roleOptions, permissionGroups, loadAdminData, setError, setMessage, usersTableRows, handleSyncAD, isSyncingAD }) => (
  <Box>
    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
      <Button
        variant="outlined"
        color="secondary"
        startIcon={isSyncingAD ? <CircularProgress size={20} color="inherit" /> : <SyncOutlinedIcon />}
        onClick={handleSyncAD}
        disabled={isSyncingAD}
      >
        {isSyncingAD ? 'Синхронизация...' : 'Синхронизировать с AD'}
      </Button>
    </Box>
    <CreateUserForm
      dbOptions={dbOptions}
      roleOptions={roleOptions}
      permissionGroups={permissionGroups}
      onSuccess={loadAdminData}
      onError={setError}
      onMessage={setMessage}
    />
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell>Логин</TableCell>
            <TableCell>ФИО</TableCell>
            <TableCell>Email</TableCell>
            <TableCell>Почта Exchange</TableCell>
            <TableCell>Telegram ID</TableCell>
            <TableCell>Источник</TableCell>
            <TableCell>Назначенная БД</TableCell>
            <TableCell>Роль</TableCell>
            <TableCell>Права</TableCell>
            <TableCell>Статус</TableCell>
            <TableCell>Действие</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {usersTableRows}
        </TableBody>
      </Table>
    </TableContainer>
  </Box>
));

const SessionsTab = memo(({ adminLoading, sessions, handleTerminateSession }) => (
  <Box>
    {adminLoading && <Typography variant="body2">Загрузка...</Typography>}
    {!adminLoading && (
      <Stack spacing={1}>
        {sessions.map((session) => (
          <Paper key={session.session_id} variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="body2">
              {session.username} • {session.role} • {session.ip_address || 'IP неизвестен'} • {session.last_seen_at}
            </Typography>
            <Box sx={{ mt: 1 }}>
              <Button size="small" color="error" variant="outlined" onClick={() => handleTerminateSession(session.session_id)}>
                Завершить
              </Button>
            </Box>
          </Paper>
        ))}
        {sessions.length === 0 && (
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">Активных сессий нет.</Typography>
          </Paper>
        )}
      </Stack>
    )}
  </Box>
));

function Settings() {
  const { user, hasPermission } = useAuth();
  const { preferences, savePreferences } = usePreferences();
  const canManageUsers = hasPermission('settings.users.manage');
  const canManageSessions = hasPermission('settings.sessions.manage');

  const [tab, setTab] = useState('profile');
  const [databases, setDatabases] = useState([]);
  const [dbLocked, setDbLocked] = useState(false);

  const [pinnedDatabase, setPinnedDatabase] = useState(preferences.pinned_database || '');
  const [themeMode, setThemeMode] = useState(preferences.theme_mode || 'light');
  const [fontFamily, setFontFamily] = useState(preferences.font_family || 'Inter');
  const [fontScale, setFontScale] = useState(Number(preferences.font_scale || 1));

  const [users, setUsers] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);

  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Состояние для подтверждения удаления пользователя
  const [userToDelete, setUserToDelete] = useState(null);
  const [isSyncingAD, setIsSyncingAD] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [isUserDrawerOpen, setIsUserDrawerOpen] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);

  useEffect(() => {
    setPinnedDatabase(preferences.pinned_database || '');
    setThemeMode(preferences.theme_mode || 'light');
    setFontFamily(preferences.font_family || 'Inter');
    setFontScale(Number(preferences.font_scale || 1));
  }, [preferences]);

  const loadDatabases = useCallback(async () => {
    try {
      const [dbListRes, currentRes] = await Promise.all([
        apiClient.get('/database/list'),
        apiClient.get('/database/current'),
      ]);
      setDatabases(Array.isArray(dbListRes?.data) ? dbListRes.data : []);
      setDbLocked(String(currentRes?.data?.locked || '') === 'true');
    } catch (err) {
      console.error(err);
      setError('Не удалось загрузить список баз данных.');
    }
  }, []);

  const loadAdminData = useCallback(async () => {
    if (!canManageUsers && !canManageSessions) return;
    setAdminLoading(true);
    try {
      const [usersData, sessionsData] = await Promise.all([
        authAPI.getUsers(),
        authAPI.getSessions(),
      ]);
      setUsers(
        (Array.isArray(usersData) ? usersData : []).map((item) => ({
          ...item,
          use_custom_permissions: Boolean(item?.use_custom_permissions),
          custom_permissions: normalizePermissions(item?.custom_permissions),
        }))
      );
      setSessions(Array.isArray(sessionsData) ? sessionsData : []);
    } catch (err) {
      console.error(err);
      setError('Не удалось загрузить данные администрирования.');
    } finally {
      setAdminLoading(false);
    }
  }, [canManageUsers, canManageSessions]);

  useEffect(() => {
    if (user) {
      loadDatabases();
    }
  }, [loadDatabases, user]);

  useEffect(() => {
    if ((tab === 'users' && canManageUsers) || (tab === 'sessions' && canManageSessions)) {
      loadAdminData();
    }
  }, [tab, loadAdminData, canManageUsers, canManageSessions]);

  const dbOptions = useMemo(
    () => databases.map((db) => ({ id: String(db.id), name: db.name })),
    [databases]
  );

  const handleSavePreferences = useCallback(async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      await savePreferences({
        pinned_database: pinnedDatabase || null,
        theme_mode: themeMode,
        font_family: fontFamily,
        font_scale: Number(fontScale),
      });
      if (pinnedDatabase) {
        await apiClient.post('/database/switch', { database_id: pinnedDatabase });
      }
      setMessage('Настройки успешно сохранены.');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Ошибка при сохранении настроек.');
    } finally {
      setSaving(false);
    }
  }, [pinnedDatabase, themeMode, fontFamily, fontScale, savePreferences]);

  const handleSaveUserRow = useCallback(async (row) => {
    setError('');
    setIsSavingUser(true);
    try {
      const email = String(row.email || '').trim();
      const mailboxEmail = String(row.mailbox_email || '').trim();
      const mailboxLogin = String(row.mailbox_login || '').trim();
      const updatePayload = {
        full_name: row.full_name || null,
        email: email || null,
        mailbox_email: mailboxEmail || null,
        mailbox_login: mailboxLogin || null,
        role: row.role,
        auth_source: row.auth_source || 'local',
        telegram_id: row.telegram_id ? Number(row.telegram_id) : null,
        assigned_database: row.assigned_database || null,
        is_active: row.is_active,
        use_custom_permissions: Boolean(row.use_custom_permissions),
        custom_permissions: normalizePermissions(row.custom_permissions),
      };
      const mailboxPassword = String(row.mailbox_password || '').trim();
      if (mailboxPassword) {
        updatePayload.mailbox_password = mailboxPassword;
      }
      await authAPI.updateUser(row.id, updatePayload);
      setMessage(`Пользователь ${row.username} обновлен.`);
      await loadAdminData();
      return true;
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? JSON.stringify(detail) : 'Не удалось обновить пользователя.');
      return false;
    } finally {
      setIsSavingUser(false);
    }
  }, [loadAdminData]);

  const handleOpenUserEditor = useCallback((userObj) => {
    setEditingUser(userObj);
    setIsUserDrawerOpen(true);
  }, []);

  const handleCloseUserEditor = useCallback(() => {
    if (isSavingUser) return;
    setIsUserDrawerOpen(false);
    setEditingUser(null);
  }, [isSavingUser]);

  const handleSaveUserFromDrawer = useCallback(async (row) => {
    const ok = await handleSaveUserRow(row);
    if (!ok) return;
    setIsUserDrawerOpen(false);
    setEditingUser(null);
  }, [handleSaveUserRow]);

  const handleDeleteClick = useCallback((userObj) => {
    if (Number(userObj.id) === 1) {
      setError('Нельзя удалить системного администратора (ID 1).');
      return;
    }
    if (Number(userObj.id) === Number(user?.id)) {
      setError('Нельзя удалить собственную активную учетную запись.');
      return;
    }
    setUserToDelete(userObj);
  }, [user?.id]);

  const confirmDeleteUser = async () => {
    if (!userToDelete) return;
    setError('');
    try {
      await authAPI.deleteUser(userToDelete.id);
      setMessage(`Пользователь ${userToDelete.username} удален.`);
      await loadAdminData();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? JSON.stringify(detail) : 'Не удалось удалить пользователя.');
    } finally {
      setUserToDelete(null);
    }
  };

  const handleTerminateSession = async (sessionId) => {
    setError('');
    try {
      await authAPI.terminateSession(sessionId);
      setMessage('Сессия завершена.');
      await loadAdminData();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Не удалось завершить сессию.');
    }
  };

  const handleSyncAD = useCallback(async () => {
    setSaving(true);
    setIsSyncingAD(true);
    setError('');
    setMessage('');
    try {
      const result = await authAPI.syncAD();
      if (result.status === 'success') {
        let added = 0;
        let updated = 0;
        Object.values(result.results || {}).forEach(res => {
          added += res.added || 0;
          updated += res.updated || 0;
        });
        setMessage(`Синхронизация профилей из AD завершена. Новых: ${added}, Обновлено: ${updated}`);
        await loadAdminData();
      } else {
        setError(result.message || 'Ошибка при синхронизации с AD.');
      }
    } catch (err) {
      console.error(err);
      setError(err?.response?.data?.detail || 'Не удалось выполнить синхронизацию с AD.');
    } finally {
      setIsSyncingAD(false);
      setSaving(false);
    }
  }, [loadAdminData]);

  const usersTableRows = useMemo(() => {
    return users.map((item) => (
      <UserRow
        key={item.id}
        item={item}
        dbOptions={dbOptions}
        roleOptions={roleOptions}
        onEdit={handleOpenUserEditor}
        onDelete={handleDeleteClick}
      />
    ));
  }, [users, dbOptions, handleOpenUserEditor, handleDeleteClick]);

  return (
    <MainLayout>
      <Box>
        <Typography variant="h4" gutterBottom>Настройки</Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {message && <Alert severity="success" sx={{ mb: 2 }}>{message}</Alert>}

        <Dialog open={Boolean(userToDelete)} onClose={() => setUserToDelete(null)}>
          <DialogTitle>Удаление пользователя</DialogTitle>
          <DialogContent>
            <DialogContentText>
              Вы уверены, что хотите удалить учетную запись <strong>{userToDelete?.username}</strong>?
              Это действие необратимо.
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setUserToDelete(null)}>Отмена</Button>
            <Button onClick={confirmDeleteUser} color="error" variant="contained">Удалить</Button>
          </DialogActions>
        </Dialog>
        <UserEditDrawer
          open={isUserDrawerOpen}
          item={editingUser}
          dbOptions={dbOptions}
          roleOptions={roleOptions}
          permissionGroups={permissionGroups}
          onClose={handleCloseUserEditor}
          onSave={handleSaveUserFromDrawer}
          saving={isSavingUser}
        />

        <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
          <Tabs
            value={tab}
            onChange={(_, value) => setTab(value)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{ borderBottom: 1, borderColor: 'divider' }}
          >
            <Tab value="profile" label="Профиль" icon={<PersonOutlineIcon />} iconPosition="start" />
            <Tab value="appearance" label="Внешний вид" icon={<PaletteOutlinedIcon />} iconPosition="start" />
            <Tab value="database" label="База данных" icon={<StorageOutlinedIcon />} iconPosition="start" />
            {canManageUsers && <Tab value="users" label="Пользователи" icon={<GroupOutlinedIcon />} iconPosition="start" />}
            {canManageSessions && <Tab value="sessions" label="Сессии" icon={<SecurityOutlinedIcon />} iconPosition="start" />}
          </Tabs>

          <Box sx={{ p: { xs: 2, md: 3 }, minHeight: 480 }}>
            <TabPanel value={tab} current="profile">
              <ProfileTab user={user} />
            </TabPanel>

            <TabPanel value={tab} current="appearance">
              <AppearanceTab
                themeMode={themeMode}
                setThemeMode={setThemeMode}
                fontFamily={fontFamily}
                setFontFamily={setFontFamily}
                fontScale={fontScale}
                setFontScale={setFontScale}
                handleSavePreferences={handleSavePreferences}
                saving={saving}
              />
            </TabPanel>

            <TabPanel value={tab} current="database">
              <DatabaseTab
                pinnedDatabase={pinnedDatabase}
                setPinnedDatabase={setPinnedDatabase}
                dbLocked={dbLocked}
                dbOptions={dbOptions}
                handleSavePreferences={handleSavePreferences}
                saving={saving}
              />
            </TabPanel>

            {canManageUsers && (
              <TabPanel value={tab} current="users">
                <UsersTab
                  dbOptions={dbOptions}
                  roleOptions={roleOptions}
                  permissionGroups={permissionGroups}
                  loadAdminData={loadAdminData}
                  setError={setError}
                  setMessage={setMessage}
                  usersTableRows={usersTableRows}
                  handleSyncAD={handleSyncAD}
                  isSyncingAD={isSyncingAD}
                />
              </TabPanel>
            )}

            {canManageSessions && (
              <TabPanel value={tab} current="sessions">
                <SessionsTab
                  adminLoading={adminLoading}
                  sessions={sessions}
                  handleTerminateSession={handleTerminateSession}
                />
              </TabPanel>
            )}
          </Box>
        </Paper>
      </Box>
    </MainLayout>
  );
}

export default Settings;

