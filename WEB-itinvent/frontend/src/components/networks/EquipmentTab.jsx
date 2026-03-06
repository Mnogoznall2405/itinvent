import React, { useCallback, useMemo } from 'react';
import {
    Box,
    Button,
    Chip,
    Divider,
    Drawer,
    Paper,
    Stack,
    TextField,
    Typography,
    Autocomplete,
    IconButton,
    Tooltip,
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CloseIcon from '@mui/icons-material/Close';
import AddIcon from '@mui/icons-material/Add';
import DownloadIcon from '@mui/icons-material/Download';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import WebAssetIcon from '@mui/icons-material/WebAsset';
import { VariableSizeList } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';

// Column layout
const COL = {
    asw: { w: 120, label: 'ASW' },
    port: { w: 90, label: 'PORT' },
    pp: { w: 90, label: 'PORT P/P' },
    location: { w: 160, label: 'LOCATION' },
    vlan: { w: 65, label: 'VLAN' },
    name: { w: 200, label: 'NAME' },
    ip: { w: 135, label: 'IP ADDRESS' },
    mac: { w: 160, label: 'MAC ADDRESS' },
    fio: { w: 200, label: 'ФИО' },
    actions: { w: 80, label: '' },
};

const TOTAL_W = Object.values(COL).reduce((s, c) => s + c.w, 0);

const LINE_H = 24;
const ROW_PAD = 20;
const MIN_ROW_H = 48;

// Approximate chars-per-line for each column (colWidth / avgCharWidth)
// Monospace ~7.5px/char at 0.78rem, proportional ~8px/char at 0.875rem
// Subtract cell padding (px: 1.5 = 12px each side = 24px total)
const CELL_PAD_X = 24;
const MONO_CHAR_W = 7.5;
const TEXT_CHAR_W = 8;

function splitValues(raw) {
    if (!raw) return [];
    return raw.split(/\n|(?:\s{2,})/).map(v => v.trim()).filter(Boolean);
}

/** Split by any whitespace - for IP/NAME/MAC where individual values never contain spaces */
function splitBySpace(raw) {
    if (!raw) return [];
    return raw.split(/\s+/).map(v => v.trim()).filter(Boolean);
}

/** Estimate visual line count for a list of values inside a column of given pixel width */
function estimateVisualLines(values, colW, charW) {
    if (!values || values.length === 0) return 1;
    const charsPerLine = Math.max(1, Math.floor((colW - CELL_PAD_X) / charW));
    let total = 0;
    for (const v of values) {
        total += Math.max(1, Math.ceil(v.length / charsPerLine));
    }
    return total;
}

function rowLines(p) {
    const ips = splitBySpace(p.endpoint_ip_raw);
    const macs = splitBySpace(p.endpoint_mac_raw);
    const names = splitBySpace(p.endpoint_name_raw);
    const fios = splitValues(p.fio);

    const ipLines = estimateVisualLines(ips, COL.ip.w, MONO_CHAR_W);
    const macLines = estimateVisualLines(macs, COL.mac.w, MONO_CHAR_W);
    const nameLines = estimateVisualLines(names, COL.name.w, TEXT_CHAR_W);
    const fioLines = estimateVisualLines(fios, COL.fio.w, TEXT_CHAR_W);

    return Math.max(1, ipLines, macLines, nameLines, fioLines);
}

function calcRowH(p) {
    return Math.max(MIN_ROW_H, rowLines(p) * LINE_H + ROW_PAD);
}

const cell = (w, extra = {}) => ({
    width: w,
    minWidth: w,
    flexShrink: 0,
    px: 1.5,
    py: 0.75,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    overflow: 'hidden',
    ...extra,
});

function MonoLine({ value }) {
    if (!value) return null;
    return (
        <Typography variant="body2" sx={{
            fontFamily: 'monospace', fontSize: '0.78rem',
            lineHeight: `${LINE_H}px`,
            wordBreak: 'break-all',
        }}>
            {value}
        </Typography>
    );
}

function TextLine({ value, bold, color }) {
    if (!value) return null;
    return (
        <Typography variant="body2" sx={{
            fontWeight: bold ? 600 : 400,
            fontSize: '0.875rem',
            lineHeight: `${LINE_H}px`,
            color: color,
            wordBreak: 'break-word',
        }}>
            {value}
        </Typography>
    );
}

export default function EquipmentTab({
    isMobile,
    canEdit,
    isBranchWidePortSearch,

    selectedBranch,
    devices,
    devicePortCounts,
    selectedDeviceId,
    selectedDevice,
    matchedDeviceIds,
    matchedDevicePortCount,

    portSearch,
    setPortSearch,
    displayedPorts,
    branchPortLoading,
    editingPortId,
    portDraft,
    portSaving,

    socketAutocompleteOpen,
    setSocketAutocompleteOpen,
    socketAutocompleteOptions,
    socketKey,

    openCreateDeviceDialog,
    openEditDeviceDialog,
    setSelectedDeviceId,
    setDeviceChipRef,
    handlePortRowClick,
    startEditPort,
    cancelEditPort,
    updatePortDraftField,
    savePortEdit,
    setSelectedSocketId,
}) {
    const handleExportCSV = useCallback(() => {
        if (!displayedPorts?.length) return;
        const headers = ['ASW', 'PORT', 'PORT P/P', 'LOCATION', 'VLAN', 'NAME', 'IP', 'MAC', 'ФИО'];
        const rows = displayedPorts.map(p => [
            p.device_code || selectedDevice?.device_code || '',
            p.port_name || '',
            p.patch_panel_port || '',
            p.location_code || '',
            p.vlan_raw || '',
            p.endpoint_name_raw || '',
            p.endpoint_ip_raw || '',
            p.endpoint_mac_raw || '',
            p.fio || '',
        ]);
        const csv = 'data:text/csv;charset=utf-8,\uFEFF' + [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n');
        const link = document.createElement('a');
        link.setAttribute('href', encodeURI(csv));
        link.setAttribute('download', `Порты_${new Date().toISOString().slice(0, 10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }, [displayedPorts, selectedDevice]);

    const heights = useMemo(() => displayedPorts.map(calcRowH), [displayedPorts]);
    const getItemSize = useCallback((idx) => heights[idx] ?? MIN_ROW_H, [heights]);

    const RenderRow = useCallback(({ index, style }) => {
        const port = displayedPorts[index];
        const isEditing = Number(editingPortId) === Number(port.id);

        const ips = splitBySpace(port.endpoint_ip_raw);
        const macs = splitBySpace(port.endpoint_mac_raw);
        const names = splitBySpace(port.endpoint_name_raw);
        const fios = splitValues(port.fio);

        return (
            <Box
                onClick={(e) => handlePortRowClick(port, e)}
                sx={{
                    ...style,
                    display: 'flex',
                    alignItems: 'stretch',
                    cursor: 'pointer',
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                    boxSizing: 'border-box',
                    transition: 'background 0.12s',
                    '&:hover': { bgcolor: 'action.hover' },
                    bgcolor: isEditing ? 'action.selected' : 'transparent',
                }}
            >
                {/* ASW */}
                <Box sx={cell(COL.asw.w)}>
                    <TextLine bold value={port.device_code || selectedDevice?.device_code || '-'} />
                </Box>

                {/* PORT */}
                <Box sx={cell(COL.port.w)}>
                    <MonoLine value={port.port_name || '-'} />
                </Box>

                {/* PORT P/P */}
                <Box sx={cell(COL.pp.w)}>
                    <TextLine color="primary.main" bold value={port.patch_panel_port || '-'} />
                </Box>

                {/* LOCATION */}
                <Box sx={cell(COL.location.w)}>
                    <TextLine value={port.location_code || '-'} />
                </Box>

                {/* VLAN */}
                <Box sx={cell(COL.vlan.w)}>
                    <TextLine color={port.vlan_raw ? 'text.secondary' : undefined} value={port.vlan_raw || '-'} />
                </Box>

                {/* NAME - multi */}
                <Box sx={cell(COL.name.w)}>
                    {names.length > 0
                        ? names.map((n, i) => <TextLine key={i} value={n} />)
                        : <TextLine value="-" />
                    }
                </Box>

                {/* IP - multi */}
                <Box sx={cell(COL.ip.w)}>
                    {ips.length > 0
                        ? ips.map((ip, i) => <MonoLine key={i} value={ip} />)
                        : <MonoLine value="-" />
                    }
                </Box>

                {/* MAC - multi */}
                <Box sx={cell(COL.mac.w)}>
                    {macs.length > 0
                        ? macs.map((mac, i) => <MonoLine key={i} value={mac} />)
                        : <MonoLine value="-" />
                    }
                </Box>

                {/* ФИО - multi */}
                <Box sx={cell(COL.fio.w)}>
                    {fios.length > 0
                        ? fios.map((f, i) => <TextLine key={i} value={f} />)
                        : <TextLine value="-" />
                    }
                </Box>

                {/* ACTIONS */}
                {canEdit && (
                    <Box sx={{ ...cell(COL.actions.w), justifyContent: 'center', alignItems: 'center', flexDirection: 'row' }}>
                        <IconButton size="small" color="primary" onClick={e => { e.stopPropagation(); startEditPort(port, e); }}>
                            <EditIcon sx={{ fontSize: 18 }} />
                        </IconButton>
                    </Box>
                )}
            </Box>
        );
    }, [displayedPorts, editingPortId, canEdit, selectedDevice,
        startEditPort, handlePortRowClick]);

    const HeaderRow = () => (
        <Box sx={{
            display: 'flex',
            alignItems: 'center',
            borderBottom: '2px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
            position: 'sticky',
            top: 0,
            zIndex: 1,
        }}>
            {Object.entries(COL).map(([key, col]) => {
                if (key === 'actions' && !canEdit) return null;
                return (
                    <Box key={key} sx={{ width: col.w, minWidth: col.w, flexShrink: 0, px: 1.5, py: 1 }}>
                        <Typography variant="caption" sx={{
                            fontWeight: 700, letterSpacing: '0.05em',
                            textTransform: 'uppercase', color: 'text.secondary', fontSize: '0.68rem',
                        }}>
                            {col.label}
                        </Typography>
                    </Box>
                );
            })}
        </Box>
    );

    return (
        <>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>
                {/* Devices Panel */}
                <Paper variant="outlined" sx={{ width: '100%', flexShrink: 0, p: 1.5, display: 'flex', flexDirection: 'column' }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1.5}>
                        <Typography variant="subtitle2">Оборудование ({devices.length})</Typography>
                        {canEdit && (
                            <Button variant="outlined" size="small" onClick={openCreateDeviceDialog} startIcon={<AddIcon />}>
                                Добавить
                            </Button>
                        )}
                    </Stack>
                    <Box>
                        {devices.length === 0 ? (
                            <Typography variant="body2" color="text.secondary">Нет устройств.</Typography>
                        ) : (
                            <Box sx={{ display: 'flex', overflowX: 'auto', gap: 0.8, pb: 0.5 }}>
                                <Chip
                                    label="Все устройства"
                                    variant={selectedDeviceId === null ? 'filled' : 'outlined'}
                                    color={selectedDeviceId === null ? 'primary' : 'default'}
                                    onClick={() => setSelectedDeviceId(null)}
                                    sx={{ borderRadius: 1 }}
                                />
                                {devices.map((device) => {
                                    const isSelected = selectedDeviceId === device.id;
                                    const portCount = devicePortCounts.get(device.id) || 0;
                                    const label = `${device.device_code} (${portCount})`;
                                    const isMatched = isBranchWidePortSearch && matchedDeviceIds.has(device.id);
                                    const matchCount = matchedDevicePortCount.get(device.id) || 0;

                                    let chipColor = 'default';
                                    if (isSelected) chipColor = 'primary';
                                    else if (isMatched) chipColor = 'warning';

                                    return (
                                        <Chip
                                            key={device.id}
                                            label={isMatched && !isSelected ? `${label} [найдено: ${matchCount}]` : label}
                                            variant={isSelected ? 'filled' : 'outlined'}
                                            color={chipColor}
                                            onClick={() => setSelectedDeviceId(device.id)}
                                            ref={(el) => {
                                                if (el) {
                                                    const map = new Map();
                                                    map.set(device.id, el);
                                                    setDeviceChipRef?.(device.id, el);
                                                }
                                            }}
                                            sx={{ borderRadius: 1 }}
                                        />
                                    );
                                })}
                            </Box>
                        )}
                    </Box>
                </Paper>

                {/* Ports Panel */}
                <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                    <Paper variant="outlined" sx={{ p: 1.2, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="subtitle2" sx={{ whiteSpace: 'nowrap', minWidth: 100 }}>
                            {selectedDeviceId === null ? 'Все порты' : `Порты: ${selectedDevice?.device_code || ''}`}
                        </Typography>
                        <TextField
                            size="small"
                            fullWidth
                            placeholder="Поиск: ASW / PORT / розетка / IP / MAC / Имя / ФИО"
                            value={portSearch}
                            onChange={e => setPortSearch(e.target.value)}
                            sx={{ bgcolor: 'background.paper' }}
                        />
                        <Button
                            variant="outlined"
                            size="small"
                            startIcon={<DownloadIcon />}
                            onClick={handleExportCSV}
                            sx={{ whiteSpace: 'nowrap' }}
                            disabled={!displayedPorts?.length}
                        >
                            CSV ({displayedPorts?.length || 0})
                        </Button>
                        {canEdit && selectedDeviceId !== null && (
                            <Button variant="outlined" size="small" onClick={() => openEditDeviceDialog(selectedDevice)} startIcon={<EditIcon />}>
                                Изменить
                            </Button>
                        )}
                    </Paper>

                    <Paper variant="outlined" sx={{ flexGrow: 1, mb: 1, pb: 1, minHeight: 400, display: 'flex', flexDirection: 'column' }}>
                        <Box sx={{ overflowX: 'auto', flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
                            <Box sx={{ minWidth: canEdit ? TOTAL_W : TOTAL_W - COL.actions.w, display: 'flex', flexDirection: 'column', height: '100%' }}>
                                <HeaderRow />
                                {branchPortLoading ? (
                                    <Box sx={{ p: 2, display: 'flex', justifyContent: 'center' }}>
                                        <Typography variant="body2" color="text.secondary">Загрузка портов...</Typography>
                                    </Box>
                                ) : displayedPorts.length === 0 ? (
                                    <Box sx={{ p: 2 }}>
                                        <Typography variant="body2" color="text.secondary">Порты не найдены.</Typography>
                                    </Box>
                                ) : (
                                    <Box sx={{ flex: 1, minHeight: 0 }}>
                                        <AutoSizer disableWidth>
                                            {({ height }) => (
                                                <VariableSizeList
                                                    height={height}
                                                    itemCount={displayedPorts.length}
                                                    itemSize={getItemSize}
                                                    width="100%"
                                                    overscanCount={6}
                                                    estimatedItemSize={MIN_ROW_H}
                                                    style={{ overflowX: 'hidden' }}
                                                >
                                                    {RenderRow}
                                                </VariableSizeList>
                                            )}
                                        </AutoSizer>
                                    </Box>
                                )}
                            </Box>
                        </Box>
                    </Paper>
                </Box>
            </Box>

            {/* Edit Drawer */}
            <Drawer
                anchor="right"
                open={!!editingPortId && !!portDraft}
                onClose={cancelEditPort}
                PaperProps={{
                    sx: {
                        width: { xs: '100%', sm: 420 },
                        bgcolor: 'background.default',
                        p: 0,
                    },
                }}
            >
                {portDraft && (() => {
                    const editPort = displayedPorts.find(p => Number(p.id) === Number(editingPortId));
                    if (!editPort) return null;
                    return (
                        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                            {/* Header */}
                            <Box sx={{ px: 3, py: 2, bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}>
                                <Stack direction="row" alignItems="center" justifyContent="space-between">
                                    <Box>
                                        <Typography variant="h6" fontWeight={700}>Редактирование порта</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            {editPort.device_code || selectedDevice?.device_code || '-'} · {editPort.port_name || '-'}
                                        </Typography>
                                    </Box>
                                    <IconButton onClick={cancelEditPort}>
                                        <CloseIcon />
                                    </IconButton>
                                </Stack>
                            </Box>

                            {/* Form */}
                            <Box sx={{ flex: 1, overflowY: 'auto', px: 3, py: 2.5, display: 'flex', flexDirection: 'column', gap: 2.5 }}>
                                {/* Розетка (PORT P/P) */}
                                <Box>
                                    <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Розетка (PORT P/P)
                                    </Typography>
                                    <Autocomplete
                                        size="small"
                                        fullWidth
                                        freeSolo
                                        open={socketAutocompleteOpen}
                                        onOpen={() => setSocketAutocompleteOpen(true)}
                                        onClose={() => setSocketAutocompleteOpen(false)}
                                        options={socketAutocompleteOptions}
                                        getOptionLabel={(o) => String(o?.socket_code || o || '')}
                                        groupBy={(option) => String(option?.location_code || 'Без помещения')}
                                        value={
                                            socketAutocompleteOptions.find(o =>
                                                socketKey(o.socket_code) === socketKey(portDraft?.patch_panel_port || '')
                                            ) || portDraft?.patch_panel_port || ''
                                        }
                                        onChange={(_, v) => {
                                            updatePortDraftField('patch_panel_port', String(v?.socket_code || v || ''));
                                            setSelectedSocketId(v?.id || null);
                                        }}
                                        renderInput={(params) => (
                                            <TextField {...params} placeholder="Например: 6/46" />
                                        )}
                                        renderOption={(props, option) => {
                                            const { key, ...otherProps } = props;
                                            const isPlaced = Number(option.map_id || 0) > 0;
                                            return (
                                                <Box key={key} component="li" {...otherProps} sx={{ display: 'flex', alignItems: 'center', py: 1, gap: 1.5, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { borderBottom: 'none' } }}>
                                                    <Chip
                                                        label={option.socket_code}
                                                        size="small"
                                                        color="primary"
                                                        variant="outlined"
                                                        sx={{ fontWeight: 700, minWidth: 60, fontFamily: 'monospace' }}
                                                    />
                                                    <Box sx={{ flex: 1, minWidth: 0 }}>
                                                        <Typography variant="body2" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 0.5 }} noWrap>
                                                            <LocationOnIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                                                            {option.location_code || 'Без помещения'}
                                                        </Typography>
                                                        {(option.endpoint_name_raw || option.fio) && (
                                                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
                                                                {option.fio ? `ФИО: ${option.fio}` : option.endpoint_name_raw}
                                                            </Typography>
                                                        )}
                                                    </Box>
                                                    {isPlaced && (
                                                        <Tooltip title="Размещена на карте">
                                                            <WebAssetIcon sx={{ fontSize: 16, color: 'success.main', opacity: 0.8 }} />
                                                        </Tooltip>
                                                    )}
                                                </Box>
                                            );
                                        }}
                                        renderGroup={(params) => (
                                            <li key={params.key}>
                                                <Typography variant="overline" sx={{ px: 2, pt: 1, pb: 0.5, display: 'block', bgcolor: 'action.hover', fontWeight: 700, lineHeight: 1.2 }}>
                                                    {params.group}
                                                </Typography>
                                                <ul>{params.children}</ul>
                                            </li>
                                        )}
                                        ListboxProps={{ sx: { maxHeight: 320, p: 0 } }}
                                    />
                                </Box>

                                {/* Location */}
                                <Box>
                                    <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Location
                                    </Typography>
                                    <TextField
                                        size="small"
                                        fullWidth
                                        value={portDraft?.location_code || ''}
                                        onChange={e => updatePortDraftField('location_code', e.target.value)}
                                        placeholder="Номер помещения"
                                    />
                                </Box>

                                {/* VLAN */}
                                <Box>
                                    <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        VLAN
                                    </Typography>
                                    <TextField
                                        size="small"
                                        fullWidth
                                        value={portDraft?.vlan_raw || ''}
                                        onChange={e => updatePortDraftField('vlan_raw', e.target.value)}
                                        placeholder="Номер VLAN"
                                    />
                                </Box>

                                <Divider />

                                {/* NAME - multiline */}
                                <Box>
                                    <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Name (каждое имя с новой строки)
                                    </Typography>
                                    <TextField
                                        fullWidth
                                        multiline
                                        minRows={2}
                                        maxRows={6}
                                        value={portDraft?.endpoint_name_raw || ''}
                                        onChange={e => updatePortDraftField('endpoint_name_raw', e.target.value)}
                                        placeholder={'TMN-FIN-0029\nTMN-FIN-0024'}
                                        sx={{ '& .MuiInputBase-root': { fontFamily: 'monospace', fontSize: '0.85rem' } }}
                                    />
                                </Box>

                                {/* IP - multiline */}
                                <Box>
                                    <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        IP Address (каждый IP с новой строки)
                                    </Typography>
                                    <TextField
                                        fullWidth
                                        multiline
                                        minRows={2}
                                        maxRows={6}
                                        value={portDraft?.endpoint_ip_raw || ''}
                                        onChange={e => updatePortDraftField('endpoint_ip_raw', e.target.value)}
                                        placeholder={'10.105.1.75\n10.105.1.74'}
                                        sx={{ '& .MuiInputBase-root': { fontFamily: 'monospace', fontSize: '0.85rem' } }}
                                    />
                                </Box>

                                {/* MAC - multiline */}
                                <Box>
                                    <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ mb: 0.5, display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        MAC Address (каждый MAC с новой строки)
                                    </Typography>
                                    <TextField
                                        fullWidth
                                        multiline
                                        minRows={2}
                                        maxRows={6}
                                        value={portDraft?.endpoint_mac_raw || ''}
                                        onChange={e => updatePortDraftField('endpoint_mac_raw', e.target.value)}
                                        placeholder={'AA:BB:CC:DD:EE:FF\nAA-BB-CC-DD-EE-FF'}
                                        helperText="По одному MAC на строку. Допустимы ':' и '-'."
                                        sx={{ '& .MuiInputBase-root': { fontFamily: 'monospace', fontSize: '0.85rem' } }}
                                    />
                                </Box>

                                <Divider />

                            </Box>

                            {/* Footer buttons */}
                            <Box sx={{ px: 3, py: 2, borderTop: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
                                <Stack direction="row" spacing={1.5}>
                                    <Button
                                        variant="contained"
                                        fullWidth
                                        size="large"
                                        disabled={portSaving}
                                        onClick={(e) => savePortEdit(editPort, e)}
                                        startIcon={<SaveIcon />}
                                    >
                                        {portSaving ? 'Сохранение...' : 'Сохранить'}
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        fullWidth
                                        size="large"
                                        onClick={cancelEditPort}
                                        startIcon={<CloseIcon />}
                                    >
                                        Отмена
                                    </Button>
                                </Stack>
                            </Box>
                        </Box>
                    );
                })()}
            </Drawer>
        </>
    );
}
