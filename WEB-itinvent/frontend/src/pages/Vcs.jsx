import React, { useEffect, useState } from 'react';
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Card,
    CardActions,
    CardContent,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Grid,
    IconButton,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TextField,
    Tooltip,
    Typography,
    useTheme
} from '@mui/material';
import {
    Add as AddIcon,
    Computer as ComputerIcon,
    Delete as DeleteIcon,
    Dns as IpIcon,
    Download as DownloadIcon,
    Edit as EditIcon,
    ExpandMore as ExpandMoreIcon,
    LocationOn as LocationIcon,
    Monitor as VncIcon
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import MainLayout from '../components/layout/MainLayout';
import { vcsAPI } from '../api/vcs';

const Vcs = () => {
    const theme = useTheme();
    const { hasPermission } = useAuth();

    const canReadVcs = hasPermission('vcs.read');
    const canManageVcs = hasPermission('vcs.manage');

    const [computers, setComputers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [openDialog, setOpenDialog] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        ip_address: '',
        location: ''
    });
    const [submitting, setSubmitting] = useState(false);

    // Global Config State
    const [configDialogOpen, setConfigDialogOpen] = useState(false);
    const [configData, setConfigData] = useState({ password_hex: '' });
    const [savingConfig, setSavingConfig] = useState(false);

    // Info Block State
    const [infoContent, setInfoContent] = useState('');
    const [infoDialogOpen, setInfoDialogOpen] = useState(false);
    const [editTableData, setEditTableData] = useState([]);
    const [savingInfo, setSavingInfo] = useState(false);

    useEffect(() => {
        if (canReadVcs) {
            fetchComputers();
            fetchInfo();
        } else {
            setLoading(false);
        }
    }, [canReadVcs]);

    const normalizeEndpoint = (rawValue) => {
        let value = String(rawValue || '').trim();
        if (!value) {
            return '';
        }

        const hostFieldMatch = value.match(/(?:^|[\s\r\n])host\s*=\s*([^\s\r\n]+)/i);
        if (hostFieldMatch?.[1]) {
            value = hostFieldMatch[1].trim();
        }

        const ipv4Match = value.match(/\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b/);
        if (ipv4Match?.[0]) {
            return ipv4Match[0];
        }

        let cleaned = value
            .replace(/^(vnc:\/\/|http:\/\/|https:\/\/)/i, '')
            .replace(/^\/+/, '')
            .split(/[/?#\s\r\n]/)[0]
            .trim();

        if (cleaned.endsWith(':')) {
            cleaned = cleaned.slice(0, -1);
        }

        const hostMatch = cleaned.match(/^[a-zA-Z0-9][a-zA-Z0-9.-]*(?::\d+)?$/);
        return hostMatch ? cleaned : '';
    };

    const buildVncUri = (ipAddress, globalPasswordHex = '') => {
        const host = normalizeEndpoint(ipAddress);
        if (!host) return null;

        const params = new URLSearchParams();
        const hexPassword = String(globalPasswordHex || '').trim();

        if (hexPassword) {
            params.set('password_hex', hexPassword);
        }

        const query = params.toString();
        return query ? `vnc://${host}?${query}` : `vnc://${host}`;
    };

    const fetchComputers = async () => {
        setLoading(true);
        try {
            const data = await vcsAPI.getComputers();
            setComputers(Array.isArray(data) ? data : []);
            setError('');
        } catch (err) {
            console.error('Failed to load VCS computers:', err);
            setError('Не удалось загрузить список терминалов ВКС.');
        } finally {
            setLoading(false);
        }
    };

    const fetchInfo = async () => {
        try {
            const data = await vcsAPI.getInfo();
            setInfoContent(data.content || '');
        } catch (err) {
            console.error('Failed to load VCS info:', err);
        }
    };

    const handleOpenConfigDialog = async () => {
        setConfigDialogOpen(true);
        try {
            const data = await vcsAPI.getConfig();
            setConfigData({ password_hex: data.password_hex || '' });
        } catch (err) {
            console.error('Failed to fetch config', err);
            setError('Ошибка загрузки настроек VNC');
        }
    };

    const handleSaveConfig = async (e) => {
        e.preventDefault();
        setSavingConfig(true);
        try {
            await vcsAPI.updateConfig(configData);
            setConfigDialogOpen(false);
            setError('');
        } catch (err) {
            console.error('Failed to save config', err);
            setError('Ошибка сохранения настроек VNC');
        } finally {
            setSavingConfig(false);
        }
    };

    const handleOpenInfoDialog = () => {
        let parsed = [];
        try {
            parsed = JSON.parse(infoContent || '[]');
            if (!Array.isArray(parsed)) parsed = [];
        } catch (e) {
            parsed = [];
        }
        setEditTableData(parsed);
        setInfoDialogOpen(true);
    };

    const handleSaveInfo = async (e) => {
        e.preventDefault();
        setSavingInfo(true);
        try {
            const jsonContent = JSON.stringify(editTableData);
            await vcsAPI.updateInfo({ content: jsonContent });
            setInfoContent(jsonContent);
            setInfoDialogOpen(false);
            setError('');
        } catch (err) {
            console.error('Failed to save info', err);
            setError('Ошибка сохранения справочника');
        } finally {
            setSavingInfo(false);
        }
    };

    const handleTableEdit = (index, field, value) => {
        const newData = [...editTableData];
        newData[index][field] = value;
        setEditTableData(newData);
    };

    const handleTableAddRow = () => {
        setEditTableData([...editTableData, { agent: '', server: '', login: '', password: '', contact1: '', contact2: '' }]);
    };

    const handleTableDeleteRow = (index) => {
        const newData = [...editTableData];
        newData.splice(index, 1);
        setEditTableData(newData);
    };

    const renderCellText = (text) => {
        if (!text) return '';

        const combinedRegex = /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+|(?:\+7|8)[\s-]*\(?[0-9]{3}\)?[\s-]?[0-9]{3}[\s-]?[0-9]{2}[\s-]?[0-9]{2})/g;

        return (text || '').split('\n').map((line, i) => {
            const parts = line.split(combinedRegex);
            return (
                <React.Fragment key={i}>
                    {parts.map((part, j) => {
                        if (!part) return null;
                        if (part.match(/^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+$/)) {
                            return <a key={j} href={`mailto:${part}`} style={{ color: theme.palette.primary.main, textDecoration: 'none', fontWeight: 500 }}>{part}</a>;
                        } else if (part.match(/^(?:\+7|8)[\s-]*\(?[0-9]{3}\)?[\s-]?[0-9]{3}[\s-]?[0-9]{2}[\s-]?[0-9]{2}$/)) {
                            const tel = part.replace(/[^\d+]/g, '');
                            return <a key={j} href={`tel:${tel}`} style={{ color: theme.palette.primary.main, textDecoration: 'none', fontWeight: 500 }}>{part}</a>;
                        }
                        return part;
                    })}
                    <br />
                </React.Fragment>
            );
        });
    };

    const handleConnectClick = async (comp) => {
        try {
            const config = await vcsAPI.getConfig();
            const uri = buildVncUri(comp.ip_address, config.password_hex);
            if (!uri) return;

            let f = document.getElementById('vnc-frame');
            if (!f) {
                f = document.createElement('iframe');
                f.id = 'vnc-frame';
                f.style.display = 'none';
                document.body.appendChild(f);
            }
            f.src = uri;
        } catch (err) {
            console.error("Connect error", err);
            setError('Ошибка получения VNC конфигурации');
        }
    };

    const handleDownloadClick = async (comp) => {
        try {
            const config = await vcsAPI.getConfig();
            vcsAPI.downloadVncFile(comp.ip_address, comp.name, config.password_hex);
        } catch (err) {
            console.error("Download error", err);
            setError('Ошибка получения VNC конфигурации');
        }
    };

    const handleOpenDialog = (comp = null) => {
        if (comp) {
            setEditingId(comp.id);
            setFormData({
                name: comp.name || '',
                ip_address: comp.ip_address || '',
                location: comp.location || ''
            });
        } else {
            setEditingId(null);
            setFormData({
                name: '',
                ip_address: '',
                location: ''
            });
        }
        setOpenDialog(true);
    };

    const handleCloseDialog = () => {
        setOpenDialog(false);
        setEditingId(null);
    };

    const handleChange = (e) => {
        setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSubmitting(true);

        const preparedData = {
            ...formData,
            ip_address: normalizeEndpoint(formData.ip_address),
        };

        if (!preparedData.ip_address) {
            alert('Некорректный IP-адрес или имя хоста.');
            setSubmitting(false);
            return;
        }

        try {
            if (editingId) {
                await vcsAPI.updateComputer(editingId, preparedData);
            } else {
                await vcsAPI.createComputer(preparedData);
            }
            await fetchComputers();
            handleCloseDialog();
        } catch (err) {
            console.error('Failed to save computer:', err);
            alert('Ошибка при сохранении терминала. Проверьте правильность заполнения.');
        } finally {
            setSubmitting(false);
        }
    };

    const handleDelete = async (id, name) => {
        if (window.confirm(`Удалить терминал ВКС "${name}"?`)) {
            try {
                await vcsAPI.deleteComputer(id);
                setComputers((prev) => prev.filter((c) => c.id !== id));
            } catch (err) {
                console.error('Failed to delete computer:', err);
                alert('Не удалось удалить терминал.');
            }
        }
    };

    const glassCardStyle = {
        background: theme.palette.mode === 'dark'
            ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9))'
            : 'linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(240, 244, 248, 0.7))',
        backdropFilter: 'blur(10px)',
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 3,
        boxShadow: theme.palette.mode === 'dark'
            ? '0 8px 32px 0 rgba(0, 0, 0, 0.3)'
            : '0 8px 32px 0 rgba(31, 38, 135, 0.05)',
        transition: 'transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out',
        '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: theme.palette.mode === 'dark'
                ? '0 12px 40px 0 rgba(0, 0, 0, 0.5)'
                : '0 12px 40px 0 rgba(31, 38, 135, 0.1)',
        }
    };

    if (!canReadVcs) {
        return (
            <MainLayout title="ВКС терминалы">
                <Box p={3}>
                    <Alert severity="error">У вас нет прав для просмотра терминалов ВКС.</Alert>
                </Box>
            </MainLayout>
        );
    }

    return (
        <MainLayout title="ВКС терминалы">
            <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1400, mx: 'auto', flexGrow: 1 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
                    <Box>
                        <Typography
                            variant="h4"
                            component="h1"
                            gutterBottom
                            fontWeight="700"
                            sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}
                        >
                            <VncIcon fontSize="large" color="primary" />
                            Терминалы ВКС
                        </Typography>
                        <Typography variant="body1" color="text.secondary">
                            Управление компьютерами видеоконференцсвязи и прямое подключение по VNC
                        </Typography>
                    </Box>

                    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                        <Button
                            variant="outlined"
                            color="info"
                            startIcon={<DownloadIcon />}
                            onClick={() => vcsAPI.downloadVncRegFile()}
                            sx={{
                                borderRadius: 2,
                                px: 2,
                                py: 1,
                                textTransform: 'none',
                                fontWeight: 600,
                            }}
                        >
                            Установить VNC протокол
                        </Button>
                        {canManageVcs && (
                            <Button
                                variant="outlined"
                                color="secondary"
                                onClick={handleOpenConfigDialog}
                                sx={{
                                    borderRadius: 2,
                                    px: 2,
                                    py: 1,
                                    textTransform: 'none',
                                    fontWeight: 600,
                                }}
                            >
                                Настройки VNC
                            </Button>
                        )}
                        {canManageVcs && (
                            <Button
                                variant="outlined"
                                onClick={handleOpenInfoDialog}
                                startIcon={<EditIcon />}
                                sx={{
                                    borderRadius: 2,
                                    px: 2,
                                    py: 1,
                                    textTransform: 'none',
                                    fontWeight: 600,
                                }}
                            >
                                Ред. справочник
                            </Button>
                        )}
                        {canManageVcs && (
                            <Button
                                variant="contained"
                                color="primary"
                                startIcon={<AddIcon />}
                                onClick={() => handleOpenDialog()}
                                sx={{
                                    borderRadius: 2,
                                    px: 2,
                                    py: 1,
                                    textTransform: 'none',
                                    fontWeight: 600,
                                    boxShadow: theme.palette.mode === 'dark'
                                        ? '0 4px 14px 0 rgba(0, 0, 0, 0.4)'
                                        : '0 4px 14px 0 rgba(25, 118, 210, 0.3)',
                                }}
                            >
                                Добавить терминал
                            </Button>
                        )}
                    </Box>
                </Box>

                {error && (
                    <Alert severity="error" sx={{ mb: 4, borderRadius: 2 }}>{error}</Alert>
                )}

                {infoContent && (() => {
                    let tableRows = [];
                    try {
                        tableRows = JSON.parse(infoContent);
                    } catch (e) { }
                    if (!Array.isArray(tableRows) || tableRows.length === 0) return null;

                    return (
                        <Accordion sx={{ ...glassCardStyle, mb: 4, '&:before': { display: 'none' } }} defaultExpanded={false}>
                            <AccordionSummary
                                expandIcon={<ExpandMoreIcon />}
                                aria-controls="info-content"
                                id="info-header"
                            >
                                <Typography variant="h6" color="primary">Информационный справочник (Контакты и пароли)</Typography>
                            </AccordionSummary>
                            <AccordionDetails sx={{ pt: 0, overflowX: 'auto' }}>
                                <TableContainer component={Paper} elevation={0} sx={{ bgcolor: 'transparent', mt: 1 }}>
                                    <Table size="small">
                                        <TableHead>
                                            <TableRow>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Контрагент</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Адрес сервера</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Логин</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold' }}>Пароль</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold', minWidth: 200 }}>Контакт 1</TableCell>
                                                <TableCell sx={{ fontWeight: 'bold', minWidth: 200 }}>Контакт 2</TableCell>
                                            </TableRow>
                                        </TableHead>
                                        <TableBody>
                                            {tableRows.map((row, i) => (
                                                <TableRow key={i} sx={{ '& td, & th': { borderBottom: `1px solid ${theme.palette.divider}` }, '&:last-child td, &:last-child th': { border: 0 } }}>
                                                    <TableCell><b>{row.agent}</b></TableCell>
                                                    <TableCell sx={{ fontFamily: 'monospace' }}>{row.server}</TableCell>
                                                    <TableCell sx={{ fontFamily: 'monospace' }}>{row.login}</TableCell>
                                                    <TableCell sx={{ fontFamily: 'monospace' }}>{row.password}</TableCell>
                                                    <TableCell>{renderCellText(row.contact1)}</TableCell>
                                                    <TableCell>{renderCellText(row.contact2)}</TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </TableContainer>
                            </AccordionDetails>
                        </Accordion>
                    );
                })()}

                {loading ? (
                    <Box display="flex" justifyContent="center" p={5}>
                        <CircularProgress />
                    </Box>
                ) : computers.length === 0 ? (
                    <Box
                        textAlign="center"
                        py={10}
                        sx={{
                            borderRadius: 3,
                            bgcolor: 'background.paper',
                            opacity: 0.8
                        }}
                    >
                        <ComputerIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2, opacity: 0.5 }} />
                        <Typography variant="h6" color="text.secondary">Терминалы не найдены</Typography>
                        <Typography variant="body2" color="text.secondary" mb={3}>
                            Добавьте первый терминал ВКС для быстрого подключения
                        </Typography>
                    </Box>
                ) : (
                    <Grid container spacing={3}>
                        {computers.map((comp) => (
                            <Grid item xs={12} sm={6} md={4} lg={3} key={comp.id}>
                                <Card sx={glassCardStyle}>
                                    <CardContent>
                                        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
                                            <Typography
                                                variant="h6"
                                                component="h2"
                                                fontWeight="600"
                                                sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                            >
                                                {comp.name}
                                            </Typography>
                                            <ComputerIcon color="primary" />
                                        </Box>

                                        <Box display="flex" alignItems="center" mb={1} gap={1} color="text.secondary">
                                            <IpIcon fontSize="small" />
                                            <Typography variant="body2" fontWeight="500" sx={{ fontFamily: 'monospace' }}>
                                                {comp.ip_address}
                                            </Typography>
                                        </Box>

                                        <Box display="flex" alignItems="center" gap={1} color="text.secondary">
                                            <LocationIcon fontSize="small" />
                                            <Typography
                                                variant="body2"
                                                sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                            >
                                                {comp.location || 'Местоположение не указано'}
                                            </Typography>
                                        </Box>
                                    </CardContent>

                                    <CardActions sx={{ px: 2, pb: 2, pt: 0, flexDirection: 'column', alignItems: 'stretch' }}>
                                        <Box sx={{ display: 'flex', gap: 1, mb: canManageVcs ? 1 : 0 }}>
                                            <Button
                                                variant="contained"
                                                color="success"
                                                size="small"
                                                onClick={() => handleConnectClick(comp)}
                                                startIcon={<VncIcon />}
                                                sx={{
                                                    borderRadius: 1.5,
                                                    textTransform: 'none',
                                                    flexGrow: 1,
                                                    boxShadow: theme.palette.mode === 'dark'
                                                        ? '0 4px 14px 0 rgba(76, 175, 80, 0.4)'
                                                        : '0 4px 14px 0 rgba(76, 175, 80, 0.3)'
                                                }}
                                            >
                                                Подключиться
                                            </Button>

                                            <Tooltip title="Скачать файл .vnc">
                                                <IconButton
                                                    size="small"
                                                    color="primary"
                                                    onClick={() => handleDownloadClick(comp)}
                                                    sx={{ bgcolor: 'action.hover', borderRadius: 1.5 }}
                                                >
                                                    <DownloadIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                        </Box>

                                        {canManageVcs && (
                                            <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5 }}>
                                                <IconButton size="small" onClick={() => handleOpenDialog(comp)} color="info">
                                                    <EditIcon fontSize="small" />
                                                </IconButton>
                                                <IconButton size="small" onClick={() => handleDelete(comp.id, comp.name)} color="error">
                                                    <DeleteIcon fontSize="small" />
                                                </IconButton>
                                            </Box>
                                        )}
                                    </CardActions>
                                </Card>
                            </Grid>
                        ))}
                    </Grid>
                )}

                {canManageVcs && (
                    <Dialog
                        open={openDialog}
                        onClose={handleCloseDialog}
                        maxWidth="sm"
                        fullWidth
                        PaperProps={{
                            sx: {
                                borderRadius: 3,
                                backgroundImage: 'none',
                                bgcolor: 'background.paper',
                                boxShadow: theme.palette.mode === 'dark'
                                    ? '0 24px 48px rgba(0,0,0,0.5)'
                                    : '0 24px 48px rgba(0,0,0,0.1)'
                            }
                        }}
                    >
                        <DialogTitle sx={{ fontWeight: 600 }}>
                            {editingId ? 'Редактировать терминал' : 'Добавить терминал ВКС'}
                        </DialogTitle>
                        <form onSubmit={handleSubmit}>
                            <DialogContent>
                                <Box display="flex" flexDirection="column" gap={2} pt={1}>
                                    <TextField
                                        label="Наименование (переговорка/кабинет)"
                                        name="name"
                                        value={formData.name}
                                        onChange={handleChange}
                                        required
                                        fullWidth
                                        variant="outlined"
                                        placeholder="Например: Переговорная 1"
                                    />
                                    <TextField
                                        label="IP-адрес / Имя хоста"
                                        name="ip_address"
                                        value={formData.ip_address}
                                        onChange={handleChange}
                                        required
                                        fullWidth
                                        variant="outlined"
                                        placeholder="Например: 192.168.1.50"
                                    />
                                    <TextField
                                        label="Расположение (Филиал/Этаж)"
                                        name="location"
                                        value={formData.location}
                                        onChange={handleChange}
                                        fullWidth
                                        variant="outlined"
                                    />
                                </Box>
                            </DialogContent>
                            <DialogActions sx={{ p: 3, pt: 1 }}>
                                <Button onClick={handleCloseDialog} color="inherit" sx={{ borderRadius: 2 }}>
                                    Отмена
                                </Button>
                                <Button
                                    type="submit"
                                    variant="contained"
                                    color="primary"
                                    disabled={submitting}
                                    sx={{ borderRadius: 2, px: 3 }}
                                >
                                    {submitting ? <CircularProgress size={24} color="inherit" /> : 'Сохранить'}
                                </Button>
                            </DialogActions>
                        </form>
                    </Dialog>
                )}

                {canManageVcs && (
                    <Dialog open={configDialogOpen} onClose={() => setConfigDialogOpen(false)} maxWidth="sm" fullWidth>
                        <DialogTitle>Настройки интеграции VNC</DialogTitle>
                        <form onSubmit={handleSaveConfig}>
                            <DialogContent>
                                <Typography variant="body2" color="text.secondary" mb={3}>
                                    Этот HEX-пароль будет использоваться для автоматического подключения ко всем терминалам.
                                    Обычные пользователи не смогут его увидеть, но сервер будет подставлять его в ссылку подключения прозрачно для них.
                                </Typography>
                                <TextField
                                    label="Глобальный Password HEX"
                                    name="password_hex"
                                    value={configData.password_hex}
                                    onChange={(e) => setConfigData({ password_hex: e.target.value })}
                                    fullWidth
                                    variant="outlined"
                                    placeholder="Например: 6e4114ad4dc9c9d7"
                                    helperText="16 символов, шестнадцатеричный код"
                                />
                            </DialogContent>
                            <DialogActions sx={{ p: 3 }}>
                                <Button onClick={() => setConfigDialogOpen(false)} color="inherit">Отмена</Button>
                                <Button type="submit" variant="contained" color="secondary" disabled={savingConfig}>
                                    {savingConfig ? <CircularProgress size={24} /> : 'Сохранить настройки'}
                                </Button>
                            </DialogActions>
                        </form>
                    </Dialog>
                )}

                {canManageVcs && (
                    <Dialog open={infoDialogOpen} onClose={() => setInfoDialogOpen(false)} maxWidth="xl" fullWidth>
                        <DialogTitle>Редактировать справочник ВКС</DialogTitle>
                        <DialogContent>
                            <Typography variant="body2" color="text.secondary" mb={2} mt={1}>
                                Заполните таблицу справочника. Каждая строка — один контрагент или сервер. Контакты можно вводить в несколько строк.
                            </Typography>
                            <TableContainer component={Paper} variant="outlined" sx={{ mt: 2 }}>
                                <Table size="small">
                                    <TableHead>
                                        <TableRow sx={{ bgcolor: 'action.hover' }}>
                                            <TableCell>Контрагент</TableCell>
                                            <TableCell>Адрес сервера</TableCell>
                                            <TableCell>Логин</TableCell>
                                            <TableCell>Пароль</TableCell>
                                            <TableCell sx={{ minWidth: 200 }}>Контакт 1</TableCell>
                                            <TableCell sx={{ minWidth: 200 }}>Контакт 2</TableCell>
                                            <TableCell align="right" width={60}></TableCell>
                                        </TableRow>
                                    </TableHead>
                                    <TableBody>
                                        {editTableData.map((row, index) => (
                                            <TableRow key={index} hover>
                                                <TableCell sx={{ p: 1 }}><TextField fullWidth size="small" value={row.agent || ''} onChange={(e) => handleTableEdit(index, 'agent', e.target.value)} /></TableCell>
                                                <TableCell sx={{ p: 1 }}><TextField fullWidth size="small" value={row.server || ''} onChange={(e) => handleTableEdit(index, 'server', e.target.value)} /></TableCell>
                                                <TableCell sx={{ p: 1 }}><TextField fullWidth size="small" value={row.login || ''} onChange={(e) => handleTableEdit(index, 'login', e.target.value)} /></TableCell>
                                                <TableCell sx={{ p: 1 }}><TextField fullWidth size="small" value={row.password || ''} onChange={(e) => handleTableEdit(index, 'password', e.target.value)} /></TableCell>
                                                <TableCell sx={{ p: 1 }}><TextField fullWidth size="small" multiline rows={2} value={row.contact1 || ''} onChange={(e) => handleTableEdit(index, 'contact1', e.target.value)} /></TableCell>
                                                <TableCell sx={{ p: 1 }}><TextField fullWidth size="small" multiline rows={2} value={row.contact2 || ''} onChange={(e) => handleTableEdit(index, 'contact2', e.target.value)} /></TableCell>
                                                <TableCell align="right" sx={{ p: 1 }}>
                                                    <IconButton color="error" size="small" onClick={() => handleTableDeleteRow(index)}>
                                                        <DeleteIcon fontSize="small" />
                                                    </IconButton>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                        {editTableData.length === 0 && (
                                            <TableRow>
                                                <TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                                                    Справочник пуст. Нажмите «Добавить строку».
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </TableBody>
                                </Table>
                            </TableContainer>
                            <Box mt={2} mb={1}>
                                <Button startIcon={<AddIcon />} variant="outlined" size="small" onClick={handleTableAddRow}>
                                    Добавить строку
                                </Button>
                            </Box>
                        </DialogContent>
                        <DialogActions sx={{ p: 3 }}>
                            <Button onClick={() => setInfoDialogOpen(false)} color="inherit">Отмена</Button>
                            <Button onClick={handleSaveInfo} variant="contained" color="primary" disabled={savingInfo}>
                                {savingInfo ? <CircularProgress size={24} /> : 'Сохранить таблицу'}
                            </Button>
                        </DialogActions>
                    </Dialog>
                )}
            </Box>
        </MainLayout>
    );
};

export default Vcs;
