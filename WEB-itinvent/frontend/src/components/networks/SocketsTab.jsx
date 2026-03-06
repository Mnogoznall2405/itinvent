import React, { useCallback, useMemo } from 'react';
import {
  Box,
  Button,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { VariableSizeList as List } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';

const COL = {
  socket: { w: 90, label: 'Розетка' },
  asw: { w: 100, label: 'ASW' },
  port: { w: 110, label: 'PORT' },
  location: { w: 155, label: 'Location' },
  vlan: { w: 60, label: 'VLAN' },
  ip: { w: 145, label: 'IP' },
  mac: { w: 165, label: 'MAC' },
  name: { w: 175, label: 'Имя' },
  fio: { w: 200, label: 'ФИО' },
  actions: { w: 64, label: '' },
};
const TOTAL_W = Object.values(COL).reduce((sum, item) => sum + item.w, 0);

const LINE_H = 24;
const ROW_PAD = 20;
const MIN_ROW_H = 48;
const CELL_PAD_X = 24;
const MONO_CHAR_W = 7.5;
const TEXT_CHAR_W = 8;

function splitValues(raw) {
  if (!raw) return [];
  return raw.split(/\n|(?:\s{2,})/).map((value) => value.trim()).filter(Boolean);
}

function splitBySpace(raw) {
  if (!raw) return [];
  return raw.split(/\s+/).map((value) => value.trim()).filter(Boolean);
}

function estimateVisualLines(values, colW, charW) {
  if (!values || values.length === 0) return 1;
  const charsPerLine = Math.max(1, Math.floor((colW - CELL_PAD_X) / charW));
  let total = 0;
  for (const value of values) {
    total += Math.max(1, Math.ceil(value.length / charsPerLine));
  }
  return total;
}

function rowLines(socket) {
  const ips = splitBySpace(socket.endpoint_ip_raw);
  const macs = splitBySpace(socket.mac_address || socket.endpoint_mac_raw);
  const names = splitBySpace(socket.endpoint_name_raw);
  const fios = splitValues(socket.fio);

  const ipLines = estimateVisualLines(ips, COL.ip.w, MONO_CHAR_W);
  const macLines = estimateVisualLines(macs, COL.mac.w, MONO_CHAR_W);
  const nameLines = estimateVisualLines(names, COL.name.w, TEXT_CHAR_W);
  const fioLines = estimateVisualLines(fios, COL.fio.w, TEXT_CHAR_W);
  return Math.max(1, ipLines, macLines, nameLines, fioLines);
}

function calcRowH(socket) {
  return Math.max(MIN_ROW_H, rowLines(socket) * LINE_H + ROW_PAD);
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
    <Typography
      variant="body2"
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.78rem',
        lineHeight: `${LINE_H}px`,
        wordBreak: 'break-all',
      }}
    >
      {value}
    </Typography>
  );
}

function TextLine({ value, bold, color }) {
  if (!value) return null;
  return (
    <Typography
      variant="body2"
      sx={{
        fontWeight: bold ? 600 : 400,
        fontSize: '0.875rem',
        lineHeight: `${LINE_H}px`,
        color,
        wordBreak: 'break-word',
      }}
    >
      {value}
    </Typography>
  );
}

export default function SocketsTab({
  canEdit,
  socketSearch,
  setSocketSearch,
  filteredSockets,
  handleSocketRowClick,
  onCreateSocket,
  onDeleteSocket,
  deletingSocketId,
}) {
  const heights = useMemo(() => filteredSockets.map(calcRowH), [filteredSockets]);
  const getItemSize = useCallback((idx) => heights[idx] ?? MIN_ROW_H, [heights]);

  const RenderRow = useCallback(({ index, style }) => {
    const socket = filteredSockets[index];
    const isDeleting = Number(deletingSocketId || 0) === Number(socket.id);

    const ips = splitBySpace(socket.endpoint_ip_raw);
    const macs = splitBySpace(socket.mac_address || socket.endpoint_mac_raw);
    const names = splitBySpace(socket.endpoint_name_raw);

    return (
      <Box
        onClick={(event) => handleSocketRowClick(socket, event)}
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
          bgcolor: 'transparent',
        }}
      >
        <Box sx={cell(COL.socket.w, { justifyContent: 'center' })}>
          <Typography
            variant="body2"
            noWrap
            sx={{ fontWeight: 700, color: 'primary.main', fontSize: '0.875rem' }}
          >
            {socket.socket_code || '-'}
          </Typography>
        </Box>

        <Box sx={cell(COL.asw.w, { justifyContent: 'center' })}>
          <TextLine value={socket.device_code || '-'} />
        </Box>

        <Box sx={cell(COL.port.w, { justifyContent: 'center' })}>
          <MonoLine value={socket.port_name || '-'} />
        </Box>

        <Box sx={cell(COL.location.w, { justifyContent: 'center' })}>
          <TextLine value={socket.location_code || '-'} />
        </Box>

        <Box sx={cell(COL.vlan.w, { justifyContent: 'center' })}>
          <Typography
            variant="body2"
            noWrap
            sx={{ fontSize: '0.875rem', color: 'text.secondary', lineHeight: `${LINE_H}px` }}
          >
            {socket.vlan_raw || '-'}
          </Typography>
        </Box>

        <Box sx={cell(COL.ip.w)}>
          {ips.length > 0 ? ips.map((ip) => <MonoLine key={ip} value={ip} />) : <MonoLine value="-" />}
        </Box>

        <Box sx={cell(COL.mac.w)}>
          {macs.length > 0 ? macs.map((mac) => <MonoLine key={mac} value={mac} />) : <MonoLine value="-" />}
        </Box>

        <Box sx={cell(COL.name.w)}>
          {names.length > 0 ? names.map((name) => <TextLine key={name} value={name} />) : <TextLine value="-" />}
        </Box>

        <Box sx={cell(COL.fio.w, { justifyContent: 'center' })}>
          {socket.fio ? (
            <TextLine value={socket.fio} />
          ) : (
            <Typography variant="body2" sx={{ color: 'text.disabled', fontSize: '0.8rem' }}>
              -
            </Typography>
          )}
        </Box>

        {canEdit ? (
          <Box sx={cell(COL.actions.w, { justifyContent: 'center', alignItems: 'center', flexDirection: 'row' })}>
            <Tooltip title="Удалить розетку">
              <span>
                <IconButton
                  size="small"
                  color="error"
                  disabled={isDeleting}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteSocket?.(socket, event);
                  }}
                >
                  <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
        ) : null}
      </Box>
    );
  }, [
    filteredSockets,
    canEdit,
    deletingSocketId,
    handleSocketRowClick,
    onDeleteSocket,
  ]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 400 }}>
      <Paper variant="outlined" sx={{ p: 1.2, mb: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="subtitle2" sx={{ whiteSpace: 'nowrap', minWidth: 110 }}>
            Розетки ({filteredSockets.length})
          </Typography>
          <TextField
            fullWidth
            size="small"
            placeholder="Поиск: розетка / ASW / PORT / IP / MAC / ФИО"
            value={socketSearch}
            onChange={(event) => setSocketSearch(event.target.value)}
          />
          {canEdit ? (
            <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={() => onCreateSocket?.()}>
              Добавить
            </Button>
          ) : null}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ flexGrow: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ overflowX: 'auto', flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          <Box sx={{ minWidth: canEdit ? TOTAL_W : TOTAL_W - COL.actions.w, display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                borderBottom: '2px solid',
                borderColor: 'divider',
                bgcolor: 'background.paper',
              }}
            >
              {Object.entries(COL).map(([key, col]) => {
                if (key === 'actions' && !canEdit) return null;
                return (
                  <Box key={key} sx={{ width: col.w, minWidth: col.w, flexShrink: 0, px: 1.5, py: 0.75 }}>
                    <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 700,
                        letterSpacing: '0.05em',
                        textTransform: 'uppercase',
                        color: 'text.secondary',
                        fontSize: '0.68rem',
                      }}
                    >
                      {col.label}
                    </Typography>
                  </Box>
                );
              })}
            </Box>

            {filteredSockets.length === 0 ? (
              <Box sx={{ px: 2, py: 3 }}>
                <Typography variant="body2" color="text.secondary">
                  Розетки не найдены.
                </Typography>
              </Box>
            ) : (
              <Box sx={{ flex: 1, minHeight: 0 }}>
                <AutoSizer disableWidth>
                  {({ height }) => (
                    <List
                      height={height}
                      itemCount={filteredSockets.length}
                      itemSize={getItemSize}
                      width="100%"
                      overscanCount={6}
                      estimatedItemSize={MIN_ROW_H}
                    >
                      {RenderRow}
                    </List>
                  )}
                </AutoSizer>
              </Box>
            )}
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
