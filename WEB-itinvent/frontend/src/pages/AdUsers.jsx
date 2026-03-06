import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    Button,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    CircularProgress,
    Alert,
    Tooltip,
    Autocomplete,
    TextField,
    Collapse,
    useTheme,
    useMediaQuery,
} from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import MainLayout from '../components/layout/MainLayout';
import { adUsersAPI, equipmentAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const AdUsers = () => {
    const [users, setUsers] = useState([]);
    const [branches, setBranches] = useState([]);
    const [loading, setLoading] = useState(true);
    const [assigning, setAssigning] = useState({});
    const [error, setError] = useState('');
    const [expandedBranches, setExpandedBranches] = useState(new Set());

    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const { hasPermission } = useAuth();
    const canManageAdUsers = hasPermission('ad_users.manage');

    const fetchInitialData = async () => {
        setLoading(true);
        setError('');
        try {
            const [usersData, branchesData] = await Promise.all([
                adUsersAPI.getPasswordStatus(),
                equipmentAPI.getBranches().catch(() => [])
            ]);
            setUsers(usersData || []);
            setBranches(Array.isArray(branchesData) ? branchesData : (branchesData?.branches || []));
        } catch (err) {
            console.error('Failed to fetch data:', err);
            setError('Ошибка загрузки данных. Пожалуйста, попробуйте позже.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchInitialData();
    }, []);

    const handleAssignBranch = async (login, branch_name, branch_no) => {
        setAssigning(prev => ({ ...prev, [login]: true }));
        try {
            await adUsersAPI.assignBranch({ login, branch_no: branch_no || null });
            // Update local state without full reload
            setUsers(prevUsers => prevUsers.map(u =>
                u.login === login
                    ? { ...u, branch_no: branch_no || null, branch_name: branch_name || 'Неотсортированные' }
                    : u
            ));
            // Optional: Auto-expand the target branch so the user can see where it went
            setExpandedBranches(prev => {
                const next = new Set(prev);
                next.add(branch_name || 'Неотсортированные');
                return next;
            });
        } catch (err) {
            setError('Не удалось привязать филиал');
        } finally {
            setAssigning(prev => ({ ...prev, [login]: false }));
        }
    };

    const groupedUsers = users.reduce((acc, user) => {
        const branch = user.branch_name || 'Неотсортированные';
        if (!acc[branch]) acc[branch] = [];
        acc[branch].push(user);
        return acc;
    }, {});

    const sortedBranches = Object.keys(groupedUsers).sort((a, b) => {
        if (a === 'Неотсортированные') return -1;
        if (b === 'Неотсортированные') return 1;
        return a.localeCompare(b);
    });

    const toggleBranch = (branchName) => {
        setExpandedBranches(prev => {
            const next = new Set(prev);
            if (next.has(branchName)) {
                next.delete(branchName);
            } else {
                next.add(branchName);
            }
            return next;
        });
    };

    const openPasswordPortal = () => {
        window.open('https://tmn-srv-rgw-01/RDWeb/Pages/en-US/password.aspx', '_blank', 'noopener,noreferrer');
    };

    const getRowColor = (days) => {
        if (days <= 0) return 'error.light'; // Red for expired
        if (days <= 14) return 'warning.light'; // Orange for expiring soon
        return 'success.light'; // Green for ok
    };

    const getStatusText = (user) => {
        if (user.days_to_expire <= 0) return 'Пароль истек (или требуется смена)';
        return `Осталось дней: ${user.days_to_expire}`;
    };

    return (
        <MainLayout>
            <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                    <Typography variant="h4" component="h1" gutterBottom={false}>
                        Пользователи AD (Сроки паролей)
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 2 }}>
                        <Button
                            variant="outlined"
                            color="primary"
                            startIcon={<RefreshIcon />}
                            onClick={fetchInitialData}
                            disabled={loading}
                        >
                            Обновить
                        </Button>
                        <Button
                            variant="contained"
                            color="secondary"
                            startIcon={<OpenInNewIcon />}
                            onClick={openPasswordPortal}
                        >
                            Портал смены пароля
                        </Button>
                    </Box>
                </Box>

                <Alert severity="info" sx={{ mb: 3 }}>
                    Показаны активные пользователи из групп/OU <strong>Users standart</strong> и <strong>Users Objects</strong>.
                    Политика: смена пароля раз в 40 дней.
                </Alert>

                {error && (
                    <Alert severity="error" sx={{ mb: 3 }}>
                        {error}
                    </Alert>
                )}

                {loading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}>
                        <CircularProgress />
                    </Box>
                ) : (
                    <Box>
                        {sortedBranches.length === 0 ? (
                            <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
                                <Typography color="text.secondary">Пользователи не найдены.</Typography>
                            </Paper>
                        ) : (
                            sortedBranches.map(branchName => {
                                const isBranchExpanded = expandedBranches.has(branchName);
                                const branchUsers = groupedUsers[branchName];
                                const isUnsorted = branchName === 'Неотсортированные';

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
                                                backgroundColor: isUnsorted
                                                    ? (theme.palette.mode === 'dark' ? '#422006' : theme.palette.warning.light)
                                                    : (theme.palette.mode === 'dark' ? '#0f172a' : theme.palette.grey[100]),
                                                '&:hover': {
                                                    backgroundColor: isUnsorted
                                                        ? (theme.palette.mode === 'dark' ? '#78350f' : theme.palette.warning.main)
                                                        : (theme.palette.mode === 'dark' ? '#1e293b' : theme.palette.grey[200]),
                                                },
                                                color: isUnsorted
                                                    ? (theme.palette.mode === 'dark' ? '#fcd34d' : theme.palette.warning.contrastText)
                                                    : (theme.palette.mode === 'dark' ? '#ffffff' : 'inherit'),
                                            }}
                                        >
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                                {isBranchExpanded ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
                                                <Typography variant={isMobile ? 'subtitle1' : 'h6'} sx={{ fontSize: isMobile ? '0.85rem' : undefined, fontWeight: 'bold' }}>
                                                    {branchName}
                                                </Typography>
                                            </Box>
                                            <Typography variant="body2" color="inherit" sx={{ fontSize: isMobile ? '0.75rem' : undefined, opacity: 0.8 }}>
                                                ({branchUsers.length.toLocaleString()})
                                            </Typography>
                                        </Box>

                                        <Collapse in={isBranchExpanded} timeout="auto" unmountOnExit>
                                            <TableContainer component={Paper} elevation={0} sx={{ borderTop: '1px solid ' + theme.palette.divider, borderRadius: 0 }}>
                                                <Table size="small" aria-label="AD users table">
                                                    <TableHead>
                                                        <TableRow sx={{ backgroundColor: 'action.hover' }}>
                                                            <TableCell sx={{ fontWeight: 'bold' }}>ФИО</TableCell>
                                                            <TableCell sx={{ fontWeight: 'bold' }}>Логин</TableCell>
                                                            <TableCell sx={{ fontWeight: 'bold' }}>Отдел</TableCell>
                                                            <TableCell sx={{ fontWeight: 'bold' }}>Должность</TableCell>
                                                            <TableCell sx={{ fontWeight: 'bold' }}>Срок пароля</TableCell>
                                                            {canManageAdUsers && <TableCell sx={{ fontWeight: 'bold', width: 250 }}>Действие</TableCell>}
                                                        </TableRow>
                                                    </TableHead>
                                                    <TableBody>
                                                        {branchUsers.map((user, index) => (
                                                            <TableRow key={user.login || index} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                                                                <TableCell component="th" scope="row">
                                                                    {user.display_name}
                                                                </TableCell>
                                                                <TableCell>{user.login}</TableCell>
                                                                <TableCell>{user.department || '-'}</TableCell>
                                                                <TableCell>{user.title || '-'}</TableCell>
                                                                <TableCell>
                                                                    <Box sx={{
                                                                        bgcolor: getRowColor(user.days_to_expire),
                                                                        color: 'white',
                                                                        px: 1.5,
                                                                        py: 0.5,
                                                                        borderRadius: 1,
                                                                        display: 'inline-block',
                                                                        fontWeight: 'bold',
                                                                        fontSize: '0.875rem',
                                                                        whiteSpace: 'nowrap'
                                                                    }}
                                                                    >
                                                                        {getStatusText(user)}
                                                                    </Box>
                                                                </TableCell>
                                                                {canManageAdUsers && (
                                                                    <TableCell>
                                                                        <Autocomplete
                                                                            size="small"
                                                                            options={branches}
                                                                            getOptionLabel={(option) => option.BRANCH_NAME || option.branch_name || option.name || ''}
                                                                            value={(user.branch_name && user.branch_name !== 'Неотсортированные' && user.branch_no)
                                                                                ? (branches.find(b => (b.BRANCH_NO || b.branch_no || b.id) === user.branch_no) || null)
                                                                                : null}
                                                                            onChange={(e, newValue) => {
                                                                                if (newValue) {
                                                                                    handleAssignBranch(user.login, newValue.BRANCH_NAME || newValue.branch_name || newValue.name, newValue.BRANCH_NO || newValue.branch_no || newValue.id);
                                                                                } else {
                                                                                    handleAssignBranch(user.login, null, null);
                                                                                }
                                                                            }}
                                                                            disabled={assigning[user.login]}
                                                                            renderInput={(params) => (
                                                                                <TextField
                                                                                    {...params}
                                                                                    placeholder="Выбрать филиал"
                                                                                    InputProps={{
                                                                                        ...params.InputProps,
                                                                                        endAdornment: (
                                                                                            <React.Fragment>
                                                                                                {assigning[user.login] ? <CircularProgress color="inherit" size={20} /> : null}
                                                                                                {params.InputProps.endAdornment}
                                                                                            </React.Fragment>
                                                                                        ),
                                                                                    }}
                                                                                />
                                                                            )}
                                                                        />
                                                                    </TableCell>
                                                                )}
                                                            </TableRow>
                                                        ))}
                                                    </TableBody>
                                                </Table>
                                            </TableContainer>
                                        </Collapse>
                                    </Box>
                                );
                            })
                        )}
                    </Box>
                )}
            </Box>
        </MainLayout>
    );
};

export default AdUsers;
