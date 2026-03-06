/**
 * Search page - find equipment by serial number or employee.
 */
import { useState } from 'react';
import {
  Box,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  TextField,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  Chip,
} from '@mui/material';
import MainLayout from '../components/layout/MainLayout';
import { equipmentAPI } from '../api/client';

function TabPanel({ children, value, index }) {
  return (
    <div role="tabpanel" hidden={value !== index}>
      {value === index && <Box sx={{ mt: 3 }}>{children}</Box>}
    </div>
  );
}

function Search() {
  const [tabValue, setTabValue] = useState(0);
  const [serialSearch, setSerialSearch] = useState('');
  const [employeeSearch, setEmployeeSearch] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Search by serial number
  const handleSerialSearch = async () => {
    if (!serialSearch.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const data = await equipmentAPI.searchBySerial(serialSearch);
      setResults({ type: 'serial', data });
      setLoading(false);
    } catch (err) {
      setError('Ошибка поиска: ' + (err.response?.data?.detail || err.message));
      setLoading(false);
    }
  };

  // Search by employee
  const handleEmployeeSearch = async (page = 1) => {
    if (!employeeSearch.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const data = await equipmentAPI.searchByEmployee(employeeSearch, page, 20);
      setResults({ type: 'employee', data });
      setLoading(false);
    } catch (err) {
      setError('Ошибка поиска: ' + (err.response?.data?.detail || err.message));
      setLoading(false);
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    setResults(null);
    setError(null);
  };

  return (
    <MainLayout>
      <Box>
        <Typography variant="h4" gutterBottom>
          Поиск оборудования
        </Typography>

        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange}>
            <Tab label="Поиск по серийнику" />
            <Tab label="Поиск по сотруднику" />
            <Tab label="Результаты" disabled={!results} />
          </Tabs>
        </Box>

        {/* Serial Search Tab */}
        <TabPanel value={tabValue} index={0}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                <TextField
                  fullWidth
                  label="Серийный номер / Инвентарный номер"
                  value={serialSearch}
                  onChange={(e) => setSerialSearch(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSerialSearch()}
                  disabled={loading}
                />
                <Button
                  variant="contained"
                  onClick={handleSerialSearch}
                  disabled={loading || !serialSearch.trim()}
                >
                  Найти
                </Button>
              </Box>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Employee Search Tab */}
        <TabPanel value={tabValue} index={1}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                <TextField
                  fullWidth
                  label="Имя сотрудника или отдел"
                  value={employeeSearch}
                  onChange={(e) => setEmployeeSearch(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleEmployeeSearch()}
                  disabled={loading}
                />
                <Button
                  variant="contained"
                  onClick={() => handleEmployeeSearch()}
                  disabled={loading || !employeeSearch.trim()}
                >
                  Найти
                </Button>
              </Box>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Results Tab */}
        <TabPanel value={tabValue} index={2}>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
          )}

          {results?.type === 'serial' && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Результаты поиска по запросу "{serialSearch}"
              </Typography>
              {results.data.found ? (
                <TableContainer component={Paper}>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Инв. номер</TableCell>
                        <TableCell>Серийный номер</TableCell>
                        <TableCell>Тип</TableCell>
                        <TableCell>Модель</TableCell>
                        <TableCell>Сотрудник</TableCell>
                        <TableCell>Филиал</TableCell>
                        <TableCell>Локация</TableCell>
                        <TableCell>Статус</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {results.data.equipment.map((item) => (
                        <TableRow key={item.inv_no} hover>
                          <TableCell>{item.inv_no}</TableCell>
                          <TableCell>{item.serial_no || item.hw_serial_no || '-'}</TableCell>
                          <TableCell>{item.type_name || '-'}</TableCell>
                          <TableCell>{item.model_name || '-'}</TableCell>
                          <TableCell>{item.employee_name || '-'}</TableCell>
                          <TableCell>{item.branch_name || '-'}</TableCell>
                          <TableCell>{item.location_name || '-'}</TableCell>
                          <TableCell>
                            <Chip
                              label={item.status_name || 'Неизвестно'}
                              size="small"
                              color={item.status_name === 'Работает' ? 'success' : 'default'}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">Оборудование не найдено</Alert>
              )}
            </Box>
          )}

          {results?.type === 'employee' && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Найдено сотрудников: {results.data.total}
              </Typography>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>ФИО</TableCell>
                      <TableCell>Отдел</TableCell>
                      <TableCell>Email</TableCell>
                      <TableCell align="right">Кол-во оборудования</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {results.data.employees.map((emp) => (
                      <TableRow key={emp.owner_no} hover>
                        <TableCell>{emp.name}</TableCell>
                        <TableCell>{emp.department || '-'}</TableCell>
                        <TableCell>{emp.email || '-'}</TableCell>
                        <TableCell align="right">
                          <Chip label={emp.equipment_count} color="primary" />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </TabPanel>
      </Box>
    </MainLayout>
  );
}

export default Search;
