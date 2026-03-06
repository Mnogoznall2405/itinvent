import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  Grid,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import CleaningServicesIcon from '@mui/icons-material/CleaningServices';
import PrintIcon from '@mui/icons-material/Print';
import BatteryChargingFullIcon from '@mui/icons-material/BatteryChargingFull';
import MemoryIcon from '@mui/icons-material/Memory';
import MainLayout from '../components/layout/MainLayout';
import { jsonAPI } from '../api/json_client';

const PERIOD_OPTIONS = [
  { value: 30, label: '30 дней' },
  { value: 90, label: '90 дней' },
  { value: 180, label: '180 дней' },
  { value: 365, label: '365 дней' },
];

const EMPTY_PC_STATS = {
  totals: {
    total_pc: 0,
    cleaned_pc: 0,
    remaining_pc: 0,
    coverage_percent: 0,
    cleanings_total: 0,
    cleanings_period: 0,
  },
  branches: [],
  start_date: '',
  end_date: '',
};

const EMPTY_MFU_STATS = {
  totals: { total_operations: 0, unique_branches: 0, unique_locations: 0 },
  by_type_period: {},
  by_item_period: {},
  by_branch_period: {},
  by_model_period: [],
  by_location_period: [],
  recent_replacements: [],
  start_date: '',
  end_date: '',
};

const EMPTY_BATTERY_STATS = {
  totals: { total_operations: 0, unique_branches: 0, unique_locations: 0 },
  by_branch_period: {},
  by_model_period: [],
  by_manufacturer_period: {},
  by_item_period: {},
  by_location_period: [],
  recent_replacements: [],
  start_date: '',
  end_date: '',
};

const EMPTY_PC_COMPONENTS_STATS = {
  totals: { total_operations: 0, unique_branches: 0, unique_locations: 0 },
  by_component_period: {},
  by_item_period: {},
  by_branch_period: {},
  by_model_period: [],
  by_location_period: [],
  recent_replacements: [],
  start_date: '',
  end_date: '',
};

const formatDateTime = (value) => {
  if (!value) return '-';
  
  // Handle ISO date strings
  if (typeof value === 'string') {
    // Try to parse ISO date
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      // If date is in the past, show relative time
      const now = new Date();
      const diffMs = now - date;
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      
      if (diffDays === 0) {
        // Today - show time only
        return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
      } else if (diffDays === 1) {
        return 'Вчера';
      } else if (diffDays < 7) {
        return `${diffDays} дн. назад`;
      } else if (diffDays < 30) {
        const weeks = Math.floor(diffDays / 7);
        return `${weeks} нед. назад`;
      } else {
        // Old date - show full date
        return date.toLocaleDateString('ru-RU');
      }
    }
    return value;
  }
  
  return String(value);
};

const formatFullDateTime = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU');
};

// Convert array of {key, value} objects to plain object
const arrayToObject = (array, keyField, valueField) => {
  if (!Array.isArray(array)) return {};
  const obj = {};
  array.forEach(item => {
    const key = String(item[keyField] || 'Не указано');
    const value = Number(item[valueField] || 0);
    obj[key] = value;
  });
  return obj;
};

const parseFilename = (contentDisposition) => {
  if (!contentDisposition) return null;
  const matched = /filename="?([^"]+)"?/i.exec(contentDisposition);
  return matched?.[1] || null;
};

const getCoverageColor = (value) => {
  if (value >= 80) return 'success';
  if (value >= 50) return 'warning';
  return 'error';
};

function MetricCard({ title, value, color }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="body2" color="text.secondary">{title}</Typography>
        <Typography variant="h4" color={color || 'inherit'}>{value}</Typography>
      </CardContent>
    </Card>
  );
}

function DistributionChips({ title, data, limit = 8 }) {
  const entries = Object.entries(data || {}).slice(0, limit);
  if (entries.length === 0) return null;
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>{title}</Typography>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {entries.map(([label, count]) => (
            <Chip
              key={label}
              size="small"
              variant="outlined"
              label={`${label}: ${count}`}
              sx={{
                bgcolor: (theme) => (theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.08)' : 'background.paper'),
                borderColor: (theme) => (theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.24)' : undefined),
                color: 'text.primary',
              }}
            />
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

function Statistics() {
  const [tab, setTab] = useState('pc');
  const [periodDays, setPeriodDays] = useState(90);
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  const [pcStats, setPcStats] = useState(EMPTY_PC_STATS);
  const [mfuStats, setMfuStats] = useState(EMPTY_MFU_STATS);
  const [batteryStats, setBatteryStats] = useState(EMPTY_BATTERY_STATS);
  const [pcComponentsStats, setPcComponentsStats] = useState(EMPTY_PC_COMPONENTS_STATS);

  const loadPcStats = useCallback(async () => {
    const response = await jsonAPI.getPcCleaningStatistics({ period_days: periodDays });
    setPcStats(response?.data || EMPTY_PC_STATS);
  }, [periodDays]);

  const loadMfuStats = useCallback(async () => {
    const response = await jsonAPI.getMfuStatistics({ period_days: periodDays });
    setMfuStats(response?.data || EMPTY_MFU_STATS);
  }, [periodDays]);

  const loadBatteryStats = useCallback(async () => {
    const response = await jsonAPI.getBatteryStatistics({ period_days: periodDays });
    setBatteryStats(response?.data || EMPTY_BATTERY_STATS);
  }, [periodDays]);

  const loadPcComponentsStats = useCallback(async () => {
    const response = await jsonAPI.getPcComponentsStatistics({ period_days: periodDays });
    setPcComponentsStats(response?.data || EMPTY_PC_COMPONENTS_STATS);
  }, [periodDays]);

  const loadActiveStats = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      if (tab === 'pc') await loadPcStats();
      if (tab === 'mfu') await loadMfuStats();
      if (tab === 'battery') await loadBatteryStats();
      if (tab === 'pc_components') await loadPcComponentsStats();
    } catch (requestError) {
      console.error('Error loading statistics:', requestError);
      const errors = {
        pc: 'Не удалось загрузить статистику чистки ПК',
        mfu: 'Не удалось загрузить статистику МФУ',
        battery: 'Не удалось загрузить статистику батарей',
        pc_components: 'Не удалось загрузить статистику комплектующих ПК',
      };
      setError(errors[tab] || 'Не удалось загрузить статистику');
    } finally {
      setLoading(false);
    }
  }, [tab, loadPcStats, loadMfuStats, loadBatteryStats, loadPcComponentsStats]);

  useEffect(() => {
    loadActiveStats();
  }, [loadActiveStats]);

  const handleExportExcel = async () => {
    try {
      setExporting(true);
      setError('');
      const response = await jsonAPI.exportStatisticsExcel(tab, periodDays);
      const contentDisposition = response?.headers?.['content-disposition'];
      const filename = parseFilename(contentDisposition) || `statistics_${tab}_${periodDays}d.xlsx`;
      const blob = new Blob(
        [response.data],
        { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      console.error('Error exporting statistics:', exportError);
      setError('Не удалось экспортировать отчет в Excel');
    } finally {
      setExporting(false);
    }
  };

  const currentStats =
    tab === 'pc' ? pcStats : tab === 'mfu' ? mfuStats : tab === 'battery' ? batteryStats : pcComponentsStats;

  const query = String(searchText || '').trim().toLowerCase();

  const filteredPcBranches = useMemo(() => {
    if (!query) return pcStats.branches || [];
    return (pcStats.branches || []).filter((row) =>
      String(row.branch || '').toLowerCase().includes(query)
    );
  }, [pcStats.branches, query]);

  const filteredMfuLocations = useMemo(() => {
    if (!query) return mfuStats.by_location_period || [];
    return (mfuStats.by_location_period || []).filter((row) => {
      const branch = String(row.branch || '').toLowerCase();
      const location = String(row.location || '').toLowerCase();
      return branch.includes(query) || location.includes(query);
    });
  }, [mfuStats.by_location_period, query]);

  // Normalize MFU by_model_period from array to object
  const mfuByModelObject = useMemo(() => {
    return arrayToObject(mfuStats.by_model_period, 'model', 'count');
  }, [mfuStats.by_model_period]);

  const filteredBatteryLocations = useMemo(() => {
    if (!query) return batteryStats.by_location_period || [];
    return (batteryStats.by_location_period || []).filter((row) => {
      const branch = String(row.branch || '').toLowerCase();
      const location = String(row.location || '').toLowerCase();
      return branch.includes(query) || location.includes(query);
    });
  }, [batteryStats.by_location_period, query]);

  // Normalize Battery by_model_period from array to object
  const batteryByModelObject = useMemo(() => {
    return arrayToObject(batteryStats.by_model_period, 'model', 'count');
  }, [batteryStats.by_model_period]);

  const filteredPcComponentsLocations = useMemo(() => {
    if (!query) return pcComponentsStats.by_location_period || [];
    return (pcComponentsStats.by_location_period || []).filter((row) => {
      const branch = String(row.branch || '').toLowerCase();
      const location = String(row.location || '').toLowerCase();
      return branch.includes(query) || location.includes(query);
    });
  }, [pcComponentsStats.by_location_period, query]);

  // Normalize PC Components by_model_period from array to object
  const pcComponentsByModelObject = useMemo(() => {
    return arrayToObject(pcComponentsStats.by_model_period, 'model', 'count');
  }, [pcComponentsStats.by_model_period]);

  const titleText =
    tab === 'pc'
      ? 'Статистика чистки ПК'
      : tab === 'mfu'
        ? 'Статистика обслуживания МФУ'
        : tab === 'battery'
          ? 'Статистика замены батарей ИБП'
          : 'Статистика комплектующих ПК';

  return (
    <MainLayout>
      <Box>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          justifyContent="space-between"
          alignItems={{ xs: 'stretch', md: 'center' }}
          sx={{ mb: 2 }}
        >
          <Box>
            <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {tab === 'pc' && <CleaningServicesIcon fontSize="large" />}
              {tab === 'mfu' && <PrintIcon fontSize="large" />}
              {tab === 'battery' && <BatteryChargingFullIcon fontSize="large" />}
              {tab === 'pc_components' && <MemoryIcon fontSize="large" />}
              {titleText}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Период: {currentStats.start_date || '-'} - {currentStats.end_date || '-'}
            </Typography>
          </Box>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <FormControl size="small" sx={{ minWidth: 170 }}>
              <InputLabel id="stats-period-label">Период</InputLabel>
              <Select
                labelId="stats-period-label"
                label="Период"
                value={periodDays}
                onChange={(event) => setPeriodDays(Number(event.target.value))}
              >
                {PERIOD_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              size="small"
              label={tab === 'pc' ? 'Фильтр по филиалу' : 'Фильтр по филиалу/локации'}
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />

            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              onClick={handleExportExcel}
              disabled={loading || exporting}
            >
              {exporting ? 'Экспорт...' : 'Экспорт Excel'}
            </Button>
          </Stack>
        </Stack>

        <Tabs value={tab} onChange={(_, nextValue) => setTab(nextValue)} sx={{ mb: 2 }}>
          <Tab value="pc" label="Чистка ПК" />
          <Tab value="mfu" label="МФУ" />
          <Tab value="battery" label="Батареи" />
          <Tab value="pc_components" label="Комплектующие ПК" />
        </Tabs>

        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {tab === 'pc' && (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={4} lg={2}><MetricCard title="ПК всего" value={pcStats.totals?.total_pc ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4} lg={2}><MetricCard title="Почищено" value={pcStats.totals?.cleaned_pc ?? 0} color="success.main" /></Grid>
              <Grid item xs={12} sm={6} md={4} lg={2}><MetricCard title="Осталось" value={pcStats.totals?.remaining_pc ?? 0} color="error.main" /></Grid>
              <Grid item xs={12} sm={6} md={4} lg={2}><MetricCard title="Покрытие" value={`${pcStats.totals?.coverage_percent ?? 0}%`} /></Grid>
              <Grid item xs={12} sm={6} md={4} lg={2}><MetricCard title="Чисток за период" value={pcStats.totals?.cleanings_period ?? 0} /></Grid>
            </Grid>

            <TableContainer component={Card}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Филиал</TableCell>
                    <TableCell align="right">ПК всего</TableCell>
                    <TableCell align="right">Почищено</TableCell>
                    <TableCell align="right">Осталось</TableCell>
                    <TableCell align="right">Чисток за период</TableCell>
                    <TableCell align="right">Покрытие</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredPcBranches.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} align="center">
                        <Typography variant="body2" color="text.secondary">Нет данных по выбранному фильтру</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                  {filteredPcBranches.map((row) => (
                    <TableRow key={row.branch} hover>
                      <TableCell>{row.branch}</TableCell>
                      <TableCell align="right">{row.total_pc}</TableCell>
                      <TableCell align="right">{row.cleaned_pc}</TableCell>
                      <TableCell align="right">{row.remaining_pc}</TableCell>
                      <TableCell align="right">{row.cleanings_period}</TableCell>
                      <TableCell align="right">
                        <Chip size="small" color={getCoverageColor(row.coverage_percent)} label={`${row.coverage_percent}%`} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}

        {tab === 'mfu' && (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Операций за период" value={mfuStats.totals?.total_operations ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Филиалов" value={mfuStats.totals?.unique_branches ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Локаций" value={mfuStats.totals?.unique_locations ?? 0} /></Grid>
            </Grid>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}><DistributionChips title="Сколько чего использовано (типы)" data={mfuStats.by_type_period} /></Grid>
              <Grid item xs={12} md={4}><DistributionChips title="Сколько чего использовано (позиции)" data={mfuStats.by_item_period} /></Grid>
              <Grid item xs={12} md={4}><DistributionChips title="По филиалам" data={mfuStats.by_branch_period} /></Grid>
            </Grid>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={6}><DistributionChips title="По моделям МФУ" data={mfuByModelObject} limit={15} /></Grid>
            </Grid>

            <Typography variant="h6" sx={{ mb: 1 }}>Где меняли</Typography>
            <TableContainer component={Card} sx={{ mb: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Филиал</TableCell>
                    <TableCell>Локация</TableCell>
                    <TableCell align="right">Операций</TableCell>
                    <TableCell>Топ позиций</TableCell>
                    <TableCell>Последняя замена</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredMfuLocations.length === 0 && (
                    <TableRow><TableCell colSpan={5} align="center"><Typography variant="body2" color="text.secondary">Нет данных по выбранному фильтру</Typography></TableCell></TableRow>
                  )}
                  {filteredMfuLocations.map((row, index) => (
                    <TableRow 
                      key={`${row.branch}|${row.location}|${index}`} 
                      hover
                      sx={{
                        '&:last-child td, &:last-child th': { border: 0 },
                      }}
                    >
                      <TableCell sx={{ fontWeight: 500 }}>{row.branch}</TableCell>
                      <TableCell>{row.location}</TableCell>
                      <TableCell align="right">
                        <Chip size="small" label={row.operations} color="primary" variant="outlined" />
                      </TableCell>
                      <TableCell>
                        {row.top_items && Array.isArray(row.top_items) && row.top_items.length > 0 ? (
                          <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                            {row.top_items.slice(0, 3).map((item, itemIndex) => (
                              <Chip
                                key={itemIndex}
                                size="small"
                                label={`${item.name || '-'} (${item.count || 0})`}
                                sx={{ fontSize: '0.75rem' }}
                              />
                            ))}
                          </Stack>
                        ) : (
                          <Typography variant="body2" color="text.secondary">-</Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                          {formatDateTime(row.last_timestamp)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <Typography variant="h6" sx={{ mb: 1 }}>Что и где поменяно (последние записи)</Typography>
            <TableContainer component={Card}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Дата</TableCell>
                    <TableCell>Филиал</TableCell>
                    <TableCell>Локация</TableCell>
                    <TableCell>Модель</TableCell>
                    <TableCell>Тип</TableCell>
                    <TableCell>Позиция</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(mfuStats.recent_replacements || []).length === 0 && (
                    <TableRow><TableCell colSpan={6} align="center"><Typography variant="body2" color="text.secondary">За выбранный период записей нет</Typography></TableCell></TableRow>
                  )}
                  {(mfuStats.recent_replacements || []).map((row, index) => (
                    <TableRow 
                      key={`${row.timestamp}-${row.serial_no || row.inv_no || index}`} 
                      hover
                      sx={{
                        '&:last-child td, &:last-child th': { border: 0 },
                      }}
                    >
                      <TableCell>
                        <Typography variant="body2" sx={{ fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                          {formatFullDateTime(row.timestamp)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ fontWeight: 500 }}>{row.branch}</TableCell>
                      <TableCell>{row.location}</TableCell>
                      <TableCell>{row.printer_model || '-'}</TableCell>
                      <TableCell>
                        <Chip 
                          size="small" 
                          label={row.component_type || '-'} 
                          sx={{ fontSize: '0.75rem' }}
                        />
                      </TableCell>
                      <TableCell>{row.replacement_item || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}

        {tab === 'battery' && (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Замен за период" value={batteryStats.totals?.total_operations ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Филиалов" value={batteryStats.totals?.unique_branches ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Локаций" value={batteryStats.totals?.unique_locations ?? 0} /></Grid>
            </Grid>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}><DistributionChips title="Сколько батарей использовано" data={batteryStats.by_item_period} /></Grid>
              <Grid item xs={12} md={4}><DistributionChips title="По производителям ИБП" data={batteryStats.by_manufacturer_period} /></Grid>
              <Grid item xs={12} md={4}><DistributionChips title="По филиалам" data={batteryStats.by_branch_period} /></Grid>
            </Grid>

            <Typography variant="h6" sx={{ mb: 1 }}>Где меняли батареи</Typography>
            <TableContainer component={Card} sx={{ mb: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Филиал</TableCell>
                    <TableCell>Локация</TableCell>
                    <TableCell align="right">Замен</TableCell>
                    <TableCell>Топ позиций</TableCell>
                    <TableCell>Последняя замена</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredBatteryLocations.length === 0 && (
                    <TableRow><TableCell colSpan={5} align="center"><Typography variant="body2" color="text.secondary">Нет данных по выбранному фильтру</Typography></TableCell></TableRow>
                  )}
                  {filteredBatteryLocations.map((row, index) => (
                    <TableRow 
                      key={`${row.branch}|${row.location}|${index}`} 
                      hover
                      sx={{
                        '&:last-child td, &:last-child th': { border: 0 },
                      }}
                    >
                      <TableCell sx={{ fontWeight: 500 }}>{row.branch}</TableCell>
                      <TableCell>{row.location}</TableCell>
                      <TableCell align="right">
                        <Chip size="small" label={row.operations} color="primary" variant="outlined" />
                      </TableCell>
                      <TableCell>
                        {row.top_items && Array.isArray(row.top_items) && row.top_items.length > 0 ? (
                          <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                            {row.top_items.slice(0, 3).map((item, itemIndex) => (
                              <Chip
                                key={itemIndex}
                                size="small"
                                label={`${item.name || '-'} (${item.count || 0})`}
                                sx={{ fontSize: '0.75rem' }}
                              />
                            ))}
                          </Stack>
                        ) : (
                          <Typography variant="body2" color="text.secondary">-</Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                          {formatDateTime(row.last_timestamp)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <Typography variant="h6" sx={{ mb: 1 }}>Последние замены батарей</Typography>
            <TableContainer component={Card}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Дата</TableCell>
                    <TableCell>Филиал</TableCell>
                    <TableCell>Локация</TableCell>
                    <TableCell>Модель ИБП</TableCell>
                    <TableCell>Производитель</TableCell>
                    <TableCell>Позиция</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(batteryStats.recent_replacements || []).length === 0 && (
                    <TableRow><TableCell colSpan={6} align="center"><Typography variant="body2" color="text.secondary">За выбранный период записей нет</Typography></TableCell></TableRow>
                  )}
                  {(batteryStats.recent_replacements || []).map((row, index) => (
                    <TableRow 
                      key={`${row.timestamp}-${row.serial_no || row.inv_no || index}`} 
                      hover
                      sx={{
                        '&:last-child td, &:last-child th': { border: 0 },
                      }}
                    >
                      <TableCell>
                        <Typography variant="body2" sx={{ fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                          {formatFullDateTime(row.timestamp)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ fontWeight: 500 }}>{row.branch}</TableCell>
                      <TableCell>{row.location}</TableCell>
                      <TableCell>{row.model_name || '-'}</TableCell>
                      <TableCell>
                        <Chip 
                          size="small" 
                          label={row.manufacturer || '-'} 
                          sx={{ fontSize: '0.75rem' }}
                        />
                      </TableCell>
                      <TableCell>{row.replacement_item || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}

        {tab === 'pc_components' && (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Операций за период" value={pcComponentsStats.totals?.total_operations ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Филиалов" value={pcComponentsStats.totals?.unique_branches ?? 0} /></Grid>
              <Grid item xs={12} sm={6} md={4}><MetricCard title="Локаций" value={pcComponentsStats.totals?.unique_locations ?? 0} /></Grid>
            </Grid>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}><DistributionChips title="По компонентам" data={pcComponentsStats.by_component_period} /></Grid>
              <Grid item xs={12} md={4}><DistributionChips title="По позициям" data={pcComponentsStats.by_item_period} /></Grid>
              <Grid item xs={12} md={4}><DistributionChips title="По филиалам" data={pcComponentsStats.by_branch_period} /></Grid>
            </Grid>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={6}><DistributionChips title="По моделям ПК" data={pcComponentsByModelObject} limit={15} /></Grid>
            </Grid>

            <Typography variant="h6" sx={{ mb: 1 }}>Где меняли комплектующие ПК</Typography>
            <TableContainer component={Card} sx={{ mb: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Филиал</TableCell>
                    <TableCell>Локация</TableCell>
                    <TableCell align="right">Операций</TableCell>
                    <TableCell>Топ позиций</TableCell>
                    <TableCell>Последняя замена</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredPcComponentsLocations.length === 0 && (
                    <TableRow><TableCell colSpan={5} align="center"><Typography variant="body2" color="text.secondary">Нет данных по выбранному фильтру</Typography></TableCell></TableRow>
                  )}
                  {filteredPcComponentsLocations.map((row, index) => (
                    <TableRow 
                      key={`${row.branch}|${row.location}|${index}`} 
                      hover
                      sx={{
                        '&:last-child td, &:last-child th': { border: 0 },
                      }}
                    >
                      <TableCell sx={{ fontWeight: 500 }}>{row.branch}</TableCell>
                      <TableCell>{row.location}</TableCell>
                      <TableCell align="right">
                        <Chip size="small" label={row.operations} color="primary" variant="outlined" />
                      </TableCell>
                      <TableCell>
                        {row.top_items && Array.isArray(row.top_items) && row.top_items.length > 0 ? (
                          <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                            {row.top_items.slice(0, 3).map((item, itemIndex) => (
                              <Chip
                                key={itemIndex}
                                size="small"
                                label={`${item.name || '-'} (${item.count || 0})`}
                                sx={{ fontSize: '0.75rem' }}
                              />
                            ))}
                          </Stack>
                        ) : (
                          <Typography variant="body2" color="text.secondary">-</Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                          {formatDateTime(row.last_timestamp)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <Typography variant="h6" sx={{ mb: 1 }}>Последние замены комплектующих ПК</Typography>
            <TableContainer component={Card}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Дата</TableCell>
                    <TableCell>Филиал</TableCell>
                    <TableCell>Локация</TableCell>
                    <TableCell>Модель ПК</TableCell>
                    <TableCell>Компонент</TableCell>
                    <TableCell>Позиция</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(pcComponentsStats.recent_replacements || []).length === 0 && (
                    <TableRow><TableCell colSpan={6} align="center"><Typography variant="body2" color="text.secondary">За выбранный период записей нет</Typography></TableCell></TableRow>
                  )}
                  {(pcComponentsStats.recent_replacements || []).map((row, index) => (
                    <TableRow 
                      key={`${row.timestamp}-${row.serial_no || row.inv_no || index}`} 
                      hover
                      sx={{
                        '&:last-child td, &:last-child th': { border: 0 },
                      }}
                    >
                      <TableCell>
                        <Typography variant="body2" sx={{ fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                          {formatFullDateTime(row.timestamp)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ fontWeight: 500 }}>{row.branch}</TableCell>
                      <TableCell>{row.location}</TableCell>
                      <TableCell>{row.model_name || '-'}</TableCell>
                      <TableCell>
                        <Chip 
                          size="small" 
                          label={row.component_name || '-'} 
                          sx={{ fontSize: '0.75rem' }}
                        />
                      </TableCell>
                      <TableCell>{row.replacement_item || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </Box>
    </MainLayout>
  );
}

export default Statistics;
