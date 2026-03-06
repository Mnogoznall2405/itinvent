import React, { useRef } from 'react';
import {
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Stack,
    TextField,
    Typography,
    Box,
} from '@mui/material';

export default function ImportDialog({
    open,
    onClose,
    importBranchCode,
    setImportBranchCode,
    importBranchName,
    setImportBranchName,
    importExcel,
    setImportExcel,
    importMaps,
    setImportMaps,
    onImport,
    notifyError,
}) {
    const excelInputRef = useRef(null);
    const mapsInputRef = useRef(null);

    const handleExcelChange = (event) => {
        const file = event.target.files?.[0] || null;
        if (file) {
            if (file.size > 50 * 1024 * 1024) {
                notifyError('Файл слишком большой (макс. 50MB)');
                event.target.value = '';
                return;
            }
            setImportExcel(file);
        }
        // Reset input so the same file can be re-selected
        event.target.value = '';
    };

    const handleMapsChange = (event) => {
        const files = Array.from(event.target.files || []);
        if (files.length > 0) {
            const totalSize = files.reduce((sum, f) => sum + f.size, 0);
            if (totalSize > 100 * 1024 * 1024) {
                notifyError('Файлы слишком большие (макс. 100MB)');
                event.target.value = '';
                return;
            }
            setImportMaps(files);
        }
        event.target.value = '';
    };

    return (
        <Dialog
            open={open}
            onClose={onClose}
            maxWidth="sm"
            fullWidth
        >
            <DialogTitle>Импорт сетевых данных</DialogTitle>
            <DialogContent>
                <Stack spacing={1.2} sx={{ mt: 0.5 }}>
                    <TextField
                        label="Код филиала"
                        value={importBranchCode}
                        onChange={(event) => setImportBranchCode(event.target.value)}
                        helperText="Например: tmn-p19-21"
                    />
                    <TextField
                        label="Название филиала"
                        value={importBranchName}
                        onChange={(event) => setImportBranchName(event.target.value)}
                        helperText="Например: Первомайская 19/21"
                    />

                    <Box>
                        {/* Hidden real input, не привязан к кнопке через label */}
                        <input
                            ref={excelInputRef}
                            hidden
                            type="file"
                            accept=".xlsx,.xlsm"
                            onChange={handleExcelChange}
                        />
                        <Button
                            variant="outlined"
                            fullWidth
                            sx={{ mb: 1 }}
                            onClick={() => setTimeout(() => excelInputRef.current?.click(), 0)}
                        >
                            Excel файл *
                        </Button>
                        {importExcel && (
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                Выбран: {importExcel.name} ({(importExcel.size / 1024 / 1024).toFixed(2)} MB)
                            </Typography>
                        )}
                    </Box>

                    <Box>
                        {/* Hidden real input, не привязан к кнопке через label */}
                        <input
                            ref={mapsInputRef}
                            hidden
                            type="file"
                            multiple
                            accept=".pdf,.PDF,.jpg,.jpeg,.png"
                            onChange={handleMapsChange}
                        />
                        <Button
                            variant="outlined"
                            fullWidth
                            sx={{ mb: 1 }}
                            onClick={() => setTimeout(() => mapsInputRef.current?.click(), 0)}
                        >
                            Карты (опционально)
                        </Button>
                        {importMaps.length > 0 && (
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                Выбрано файлов: {importMaps.length} (
                                {(importMaps.reduce((sum, f) => sum + f.size, 0) / 1024 / 1024).toFixed(2)} MB)
                            </Typography>
                        )}
                    </Box>
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Отмена</Button>
                <Button variant="contained" onClick={() => void onImport()} disabled={!importExcel}>
                    Импортировать
                </Button>
            </DialogActions>
        </Dialog>
    );
}
