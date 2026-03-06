import React from 'react';
import {
    Box,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    Typography,
} from '@mui/material';
import { FixedSizeList as List } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';

export default function AuditTab({ audit }) {
    if (!audit || audit.length === 0) {
        return (
            <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary">
                    История изменений пуста
                </Typography>
            </Paper>
        );
    }

    const ROW_HEIGHT = 45;

    const RenderRow = ({ index, style }) => {
        const item = audit[index];
        return (
            <TableRow
                component="div"
                sx={{
                    display: 'flex',
                    width: '100%',
                    borderBottom: '1px solid rgba(224, 224, 224, 1)',
                    boxSizing: 'border-box',
                    alignItems: 'center',
                    ...style,
                }}
            >
                <TableCell component="div" sx={{ width: '25%', py: 1, px: 2, display: 'flex', alignItems: 'center' }}>{item.created_at || '-'}</TableCell>
                <TableCell component="div" sx={{ width: '25%', py: 1, px: 2, display: 'flex', alignItems: 'center' }}>{item.entity_type || '-'}</TableCell>
                <TableCell component="div" sx={{ width: '25%', py: 1, px: 2, display: 'flex', alignItems: 'center' }}>{item.action || '-'}</TableCell>
                <TableCell component="div" sx={{ width: '25%', py: 1, px: 2, display: 'flex', alignItems: 'center' }}>{item.entity_id || '-'}</TableCell>
            </TableRow>
        );
    };

    return (
        <TableContainer component={Paper} variant="outlined" sx={{ height: 620, width: '100%' }}>
            <Table component="div" size="small" sx={{ width: '100%', display: 'flex', flexDirection: 'column', height: '100%' }}>
                <TableHead component="div" sx={{ display: 'flex', width: '100%' }}>
                    <TableRow component="div" sx={{ display: 'flex', width: '100%', pr: 1 }}>
                        <TableCell component="div" sx={{ width: '25%', px: 2 }}>Дата</TableCell>
                        <TableCell component="div" sx={{ width: '25%', px: 2 }}>Сущность</TableCell>
                        <TableCell component="div" sx={{ width: '25%', px: 2 }}>Действие</TableCell>
                        <TableCell component="div" sx={{ width: '25%', px: 2 }}>ID</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody component="div" sx={{ display: 'flex', flex: '1 1 auto', flexDirection: 'column' }}>
                    <Box sx={{ flex: 1, width: '100%', height: '100%' }}>
                        <AutoSizer>
                            {({ height, width }) => (
                                <List
                                    height={height || 500}
                                    itemCount={audit.length}
                                    itemSize={ROW_HEIGHT}
                                    width={width || '100%'}
                                    overscanCount={5}
                                    style={{ direction: 'inherit' }}
                                    itemData={audit}
                                >
                                    {RenderRow}
                                </List>
                            )}
                        </AutoSizer>
                    </Box>
                </TableBody>
            </Table>
        </TableContainer>
    );
}
